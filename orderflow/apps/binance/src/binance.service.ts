import { Injectable, Logger } from '@nestjs/common';
import { Cron, CronExpression } from '@nestjs/schedule';
import { USDMClient, WsMessageAggTradeRaw } from 'binance';
import { BinanceWebSocketService } from './binance.websocket.service';
import { DatabaseService } from '@database';
import { RabbitMQService } from '@rabbitmq';
import { aggregationIntervalMap } from '@orderflow/constants/aggregation';
import { findAllEffectedHTFIntervalsOnCandleClose } from '@orderflow/utils/candleBuildHelper';
import { CandleQueue } from '@orderflow/utils/candleQueue';
import { OrderFlowAggregator } from '@orderflow/utils/orderFlowAggregator';
import { mergeFootPrintCandles } from '@orderflow/utils/orderFlowUtil';
import { INTERVALS } from '@shared/utils/intervals';
import { KlineIntervalMs } from '@shared/constants/intervals';
import { Exchange } from '@shared/constants/exchange';
import { IFootPrintClosedCandle } from '@orderflow/dto/orderflow.dto';

@Injectable()
export class BinanceService {
  private logger: Logger = new Logger(BinanceService.name);
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

  private binanceRest = new USDMClient({});

  private expectedConnections: Map<string, Date> = new Map();
  private openConnections: Map<string, Date> = new Map();
  private wsKeyContextStore: Record<string, { symbol: string }> = {};
  private didFinishConnectingWS: boolean = false;

  private aggregators: { [symbol: string]: OrderFlowAggregator } = {};
  private candleQueue: CandleQueue;

  constructor(
    private readonly databaseService: DatabaseService,
    private readonly binanceWsService: BinanceWebSocketService,
    private readonly rabbitmqService: RabbitMQService
  ) {
    this.candleQueue = new CandleQueue(Exchange.BINANCE, this.databaseService, this.rabbitmqService);
  }

  async onModuleInit() {
    this.logger.log(`Starting Binance Orderflow service for Live candle building`);
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
    const exchangeInfo = await this.binanceRest.getExchangeInfo();
    const symbols = this.selectedSymbols.length > 0 ? this.selectedSymbols : exchangeInfo.symbols.map(({ symbol }) => symbol);

    this.binanceWsService.initWebSocket(exchangeInfo);

    for (let i = 0; i < symbols.length; i++) {
      const response = this.binanceWsService.subscribeToTrades(symbols[i], 'usdm');

      const wsKey = response.wsKey;

      if (wsKey) {
        this.wsKeyContextStore[wsKey] = { symbol: symbols[i] };
        this.expectedConnections.set(wsKey, new Date());
      } else {
        this.logger.error('no wskey? ' + { symbol: symbols[i], wsKey });
      }
    }

    this.binanceWsService.connected.subscribe((wsKey) => {
      this.openConnections.set(wsKey, new Date());

      const totalExpected = this.expectedConnections.size;
      const totalConnected = this.openConnections.size;
      this.logger.log(`Total ${totalConnected}/${totalExpected} ws connections open | (${wsKey} connected)`);

      if (totalConnected === totalExpected) {
        this.logger.log(`All WS connections are now open`);
        this.didFinishConnectingWS = true;
      }
    });

    this.binanceWsService.tradeUpdates.subscribe((trade: WsMessageAggTradeRaw) => {
      this.processNewTrades(trade.s, trade.m, trade.q as string, trade.p as string);
    });
  }

  private getOrderFlowAggregator(symbol: string, interval: string): OrderFlowAggregator {
    if (!this.aggregators[symbol]) {
      const intervalSizeMs: number = KlineIntervalMs[interval];
      if (!intervalSizeMs) {
        throw new Error(`Unknown ms per interval "${interval}"`);
      }

      this.aggregators[symbol] = new OrderFlowAggregator('binance', symbol, interval, intervalSizeMs, {});
    }

    return this.aggregators[symbol];
  }

  async buildHTFCandle(symbol: string, targetInterval: INTERVALS, openTimeMs: number, closeTimeMs: number): Promise<IFootPrintClosedCandle | null> {
    const { baseInterval, count } = aggregationIntervalMap[targetInterval];

    this.logger.log(`Building a new HTF candle for ${symbol} ${targetInterval}. Will attempt to find and use ${count} ${baseInterval} candles`);

    const baseIntervalMs = KlineIntervalMs[baseInterval];
    const aggregationStart = closeTimeMs - baseIntervalMs * count;
    const aggregationEnd = closeTimeMs;

    const candles = await this.databaseService.getCandles(Exchange.BINANCE, symbol, baseInterval, aggregationStart, aggregationEnd);

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

  private processNewTrades(symbol: string, isBuyerMaker: boolean, positionSize: string, price: string) {
    if (!this.didFinishConnectingWS) {
      return;
    }

    const aggr = this.getOrderFlowAggregator(symbol, this.BASE_INTERVAL);
    aggr.processNewTrades(isBuyerMaker, Number(positionSize), Number(price));
  }
}
