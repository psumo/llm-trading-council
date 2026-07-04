import { Injectable, Logger } from '@nestjs/common';
import { Cron, CronExpression } from '@nestjs/schedule';
import { FuturesContract, FuturesTrade, RestClient } from 'gateio-api';
import { DatabaseService } from '@database';
import { RabbitMQService } from '@rabbitmq';
import { GateioWebSocketService } from './gateio.websocket.service';
import { IFootPrintClosedCandle } from '@orderflow/dto/orderflow.dto';
import { CandleQueue } from '@orderflow/utils/candleQueue';
import { OrderFlowAggregator } from '@orderflow/utils/orderFlowAggregator';
import { INTERVALS, KlineIntervalMs } from '@shared/utils/intervals';
import { aggregationIntervalMap } from '@orderflow/constants/aggregation';
import { findAllEffectedHTFIntervalsOnCandleClose } from '@orderflow/utils/candleBuildHelper';
import { mergeFootPrintCandles } from '@orderflow/utils/orderFlowUtil';
import { Exchange } from '@shared/constants/exchange';
import { normaliseSymbolName } from './gateio.utils';

@Injectable()
export class GateioService {
  private logger: Logger = new Logger(GateioService.name);
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

  private gateioRest = new RestClient();

  private aggregators: { [symbol: string]: OrderFlowAggregator } = {};
  private candleQueue: CandleQueue;

  constructor(
    private readonly databaseService: DatabaseService,
    private readonly gateioWsService: GateioWebSocketService,
    private readonly rabbitmqService: RabbitMQService
  ) {
    this.candleQueue = new CandleQueue(Exchange.GATEIO, this.databaseService, this.rabbitmqService);
  }

  async onModuleInit() {
    this.logger.log(`Starting Gateio Orderflow service for Live candle building`);
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
    const futuresContracts: FuturesContract[] = await this.gateioRest.getFuturesContracts({ settle: 'usdt' });
    const filteredFuturesContracts = futuresContracts.filter((contract: FuturesContract) => {
      if (!this.selectedSymbols.length) {
        return true;
      }

      const normalisedSymbol = normaliseSymbolName(contract?.name as string);

      return this.selectedSymbols.includes(normalisedSymbol);
    });

    this.gateioWsService.initWebSocket(filteredFuturesContracts);

    await this.gateioWsService.subscribeToTopics(filteredFuturesContracts, 'perpFuturesUSDTV4');

    this.didFinishConnectingWS = true;

    this.gateioWsService.tradeUpdates.subscribe((trades: FuturesTrade[]) => {
      for (const trade of trades) {
        const isPassiveBid: boolean = trade.size > 0; // Positive size means market sell and limit buy.
        this.processNewTrades(trade.contract, isPassiveBid, Math.abs(trade.size), Number(trade.price)); // Use absolute size
      }
    });
  }

  private getOrderFlowAggregator(symbol: string, interval: string): OrderFlowAggregator {
    if (!this.aggregators[symbol]) {
      const intervalSizeMs: number = KlineIntervalMs[interval];
      if (!intervalSizeMs) {
        throw new Error(`Unknown ms per interval "${interval}"`);
      }

      this.aggregators[symbol] = new OrderFlowAggregator(Exchange.GATEIO, symbol, interval, intervalSizeMs, {});
    }

    return this.aggregators[symbol];
  }

  async buildHTFCandle(symbol: string, targetInterval: INTERVALS, openTimeMs: number, closeTimeMs: number): Promise<IFootPrintClosedCandle | null> {
    const { baseInterval, count } = aggregationIntervalMap[targetInterval];

    this.logger.log(`Building a new HTF candle for ${symbol} ${targetInterval}. Will attempt to find and use ${count} ${baseInterval} candles`);

    const baseIntervalMs = KlineIntervalMs[baseInterval];
    const aggregationStart = closeTimeMs - baseIntervalMs * count;
    const aggregationEnd = closeTimeMs;

    const candles = await this.databaseService.getCandles(Exchange.GATEIO, symbol, baseInterval, aggregationStart, aggregationEnd);

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

  private processNewTrades(symbol: string, isPassiveBid: boolean, positionSize: number, price: number) {
    if (!this.didFinishConnectingWS) {
      return;
    }

    const normalisedSymbol = normaliseSymbolName(symbol);
    const aggr = this.getOrderFlowAggregator(normalisedSymbol, this.BASE_INTERVAL);
    aggr.processNewTrades(isPassiveBid, positionSize, price);
  }
}
