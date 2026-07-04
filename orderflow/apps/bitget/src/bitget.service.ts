import { Injectable, Logger } from '@nestjs/common';
import { Cron, CronExpression } from '@nestjs/schedule';
import { RestClientV2, WsTopicSubscribePublicArgsV2 } from 'bitget-api';
import { DatabaseService } from '@database';
import { RabbitMQService } from '@rabbitmq';
import { BitgetWebSocketService } from './bitget.websocket.service';
import { IFootPrintClosedCandle } from '@orderflow/dto/orderflow.dto';
import { CandleQueue } from '@orderflow/utils/candleQueue';
import { OrderFlowAggregator } from '@orderflow/utils/orderFlowAggregator';
import { INTERVALS, KlineIntervalMs } from '@shared/utils/intervals';
import { aggregationIntervalMap } from '@orderflow/constants/aggregation';
import { findAllEffectedHTFIntervalsOnCandleClose } from '@orderflow/utils/candleBuildHelper';
import { mergeFootPrintCandles } from '@orderflow/utils/orderFlowUtil';
import { Exchange } from '@shared/constants/exchange';
import { ITrade } from './bitget.types';

@Injectable()
export class BitgetService {
  private logger: Logger = new Logger(BitgetService.name);
  private selectedSymbols: string[] = process.env.SYMBOLS?.split(',') ?? [];
  private readonly BASE_INTERVAL = INTERVALS.ONE_MINUTE;
  private readonly HTF_INTERVALS = [
    INTERVALS.FIVE_MINUTES,
    INTERVALS.FIFTEEN_MINUTES,
    INTERVALS.THIRTY_MINUTES,
    INTERVALS.ONE_HOUR,
    INTERVALS.TWO_HOURS,
    INTERVALS.FOUR_HOURS,
    INTERVALS.EIGHT_HOURS,
    INTERVALS.TWELVE_HOURS,
    INTERVALS.ONE_DAY,
    INTERVALS.ONE_WEEK,
    INTERVALS.ONE_MONTH
  ];

  private didFinishConnectingWS: boolean = false;

  private bitgetRest = new RestClientV2();

  private aggregators: { [symbol: string]: OrderFlowAggregator } = {};
  private candleQueue: CandleQueue;

  constructor(
    private readonly databaseService: DatabaseService,
    private readonly bitgetWsService: BitgetWebSocketService,
    private readonly rabbitmqService: RabbitMQService
  ) {
    this.candleQueue = new CandleQueue(Exchange.BITGET, this.databaseService, this.rabbitmqService);
  }

  async onModuleInit() {
    this.logger.log(`Starting Bitget Orderflow service for Live candle building`);
    await this.subscribeToWS();
  }

  @Cron(CronExpression.EVERY_HOUR)
  async handlePrune() {
    await this.databaseService.pruneOldData();
  }

  @Cron(CronExpression.EVERY_MINUTE)
  async processMinuteCandleClose() {
    if (!this.didFinishConnectingWS) {
      return;
    }

    const closed1mCandles: { [symbol: string]: IFootPrintClosedCandle } = {};
    const triggeredIntervalsPerSymbol: { [symbol: string]: INTERVALS[] } = {};

    // Process 1m candles and determine triggered intervals
    for (const symbol in this.aggregators) {
      const aggr = this.getOrderFlowAggregator(symbol, this.BASE_INTERVAL);
      const closed1mCandle = aggr.processCandleClosed();

      if (closed1mCandle) {
        this.candleQueue.enqueCandle(closed1mCandle);
        closed1mCandles[symbol] = closed1mCandle;

        const nextOpenTimeMS = 1 + closed1mCandle.closeTimeMs;
        const nextOpenTime = new Date(nextOpenTimeMS);
        triggeredIntervalsPerSymbol[symbol] = findAllEffectedHTFIntervalsOnCandleClose(nextOpenTime, this.HTF_INTERVALS);
      }
    }

    // Persist 1m candles
    await this.candleQueue.persistCandlesToStorage({ clearQueue: true });

    // Process HTF candles
    for (const interval of this.HTF_INTERVALS) {
      for (const symbol in closed1mCandles) {
        if (triggeredIntervalsPerSymbol[symbol].includes(interval)) {
          const closed1mCandle = closed1mCandles[symbol];
          const htfCandle = await this.buildHTFCandle(symbol, interval, closed1mCandle.openTimeMs, closed1mCandle.closeTimeMs);
          if (htfCandle) {
            this.candleQueue.enqueCandle(htfCandle);
          }
        }
      }
      await this.candleQueue.persistCandlesToStorage({ clearQueue: true });
    }
  }

  private async subscribeToWS(): Promise<void> {
    const futuresContractResponse = await this.bitgetRest.getFuturesContractConfig({ productType: 'usdt-futures' });
    const symbolInfo = futuresContractResponse?.data;

    const symbols = this.selectedSymbols.length > 0 ? this.selectedSymbols : symbolInfo.map(({ symbol }) => symbol);
    const wsArgs: WsTopicSubscribePublicArgsV2[] = symbols.map((symbol: string) => {
      return {
        instType: 'USDT-FUTURES',
        channel: 'trade',
        instId: symbol
      };
    });

    this.bitgetWsService.initWebSocket(symbolInfo);

    await this.bitgetWsService.subscribeToTopics(wsArgs);

    this.didFinishConnectingWS = true;

    this.bitgetWsService.tradeUpdates.subscribe((trades: ITrade[]) => {
      for (let i = 0; i < trades.length; i++) {
        const isPassiveBid: boolean = trades[i].side === 'sell'; // The aggressive side is selling
        this.processNewTrades(trades[i].symbol, isPassiveBid, trades[i].size, trades[i].roundedPrice);
      }
    });
  }

  private getOrderFlowAggregator(symbol: string, interval: string): OrderFlowAggregator {
    if (!this.aggregators[symbol]) {
      const intervalSizeMs: number = KlineIntervalMs[interval];
      if (!intervalSizeMs) {
        throw new Error(`Unknown ms per interval "${interval}"`);
      }

      this.aggregators[symbol] = new OrderFlowAggregator(Exchange.BITGET, symbol, interval, intervalSizeMs, {});
    }

    return this.aggregators[symbol];
  }

  async buildHTFCandle(symbol: string, targetInterval: INTERVALS, openTimeMs: number, closeTimeMs: number): Promise<IFootPrintClosedCandle | null> {
    const { baseInterval, count } = aggregationIntervalMap[targetInterval];

    this.logger.log(`Building a new HTF candle for ${symbol} ${targetInterval}. Will attempt to find and use ${count} ${baseInterval} candles`);

    const baseIntervalMs = KlineIntervalMs[baseInterval];
    const aggregationStart = closeTimeMs - baseIntervalMs * count;
    const aggregationEnd = closeTimeMs;

    const candles = await this.databaseService.getCandles(Exchange.BITGET, symbol, baseInterval, aggregationStart, aggregationEnd);

    if (candles?.length === count) {
      const aggregatedCandle = mergeFootPrintCandles(candles, targetInterval);
      if (aggregatedCandle) {
        return aggregatedCandle;
      }
    } else {
      this.logger.warn(
        `Target candle count ${count} was not met to create a new candle for ${symbol}, ${targetInterval}. Candle closed at ${new Date(closeTimeMs)}`
      );
    }

    return null;
  }

  private processNewTrades(symbol: string, isPassiveBid: boolean, positionSize: string, price: number) {
    if (!this.didFinishConnectingWS) {
      return;
    }

    const aggr = this.getOrderFlowAggregator(symbol, this.BASE_INTERVAL);
    aggr.processNewTrades(isPassiveBid, Number(positionSize), price);
  }
}
