import { v4 } from 'uuid';
import { getStartOfMinute } from '@orderflow/utils/date';
import { IFootPrintCandle, IFootPrintClosedCandle, IPriceLevel } from '@orderflow/dto/orderflow.dto';

export interface OrderFlowAggregatorConfig {
  // Define per-level price precision used to group trades by level
  // (ideally don't use this, instead round to tick size before it reaches the aggregator)
  pricePrecisionDp?: number | null;
}

export class OrderFlowAggregator {
  exchange: string;
  symbol: string;
  interval: string;
  intervalSizeMs: number;

  config: OrderFlowAggregatorConfig;

  /** Candle currently building (still open) */
  private activeCandle: IFootPrintCandle | null = null;

  /** Used for backtesting in replace of getStartOfMinute()  */
  public simulationMinute: number | null = null;

  constructor(exchange: string, symbol: string, interval: string, intervalSizeMs: number, config?: Partial<OrderFlowAggregatorConfig>) {
    this.exchange = exchange;
    this.symbol = symbol;
    this.interval = interval;
    this.intervalSizeMs = intervalSizeMs;

    this.config = {
      ...config
    };
  }

  public retireActiveCandle(): IFootPrintClosedCandle | undefined {
    const candle = this.activeCandle;

    if (!candle) {
      return;
    }

    const closedPriceLevels: { [price: number]: IPriceLevel } = {};

    const sortedLevels: string[] = Object.keys(candle.priceLevels).sort(
      (a, b) => Number(b) - Number(a) // descending price
    );
    for (const levelPrice of sortedLevels) {
      const level = candle.priceLevels[levelPrice];

      const closedLevel: IPriceLevel = { ...level };

      closedPriceLevels[levelPrice] = closedLevel;
    }

    const closedCandle: IFootPrintClosedCandle = {
      ...candle,
      priceLevels: closedPriceLevels,
      isClosed: true,
      didPersistToStore: false
    };

    this.activeCandle = null;

    return closedCandle;
  }

  public createNewCandle() {
    const startDate: Date = this.simulationMinute ? new Date(this.simulationMinute) : getStartOfMinute();
    const openTimeMs = startDate.getTime();
    const closeTimeMs = startDate.getTime() + this.intervalSizeMs - 1;
    const openTime = startDate.toISOString();
    const closeTime = new Date(closeTimeMs).toISOString();

    const candle: IFootPrintCandle = {
      uuid: v4(),
      openTime,
      openTimeMs,
      closeTime,
      closeTimeMs,
      symbol: this.symbol,
      exchange: this.exchange,
      interval: this.interval,
      aggressiveBid: 0,
      aggressiveAsk: 0,
      volume: 0,
      volumeDelta: 0,
      high: 0,
      low: Number.MAX_SAFE_INTEGER,
      close: 0,
      priceLevels: {},
      isClosed: false
    };

    this.activeCandle = candle;
  }

  public processCandleClosed(): IFootPrintClosedCandle | undefined {
    const candle = this.retireActiveCandle();
    this.createNewCandle();

    return candle;
  }

  public processNewTrades(isSellOrder: boolean, assetQty: number, price: number) {
    if (!this.activeCandle) {
      this.createNewCandle();
      return this.processNewTrades(isSellOrder, assetQty, price);
    }

    const tradeQty = assetQty;

    this.activeCandle.volume += tradeQty;

    // Determine which side (bid/ask) and delta direction based on whether it's an aggressive or passive bid
    const tradeQtyDelta = isSellOrder ? -tradeQty : tradeQty;

    // Update delta
    this.activeCandle.volumeDelta += tradeQtyDelta;

    const precisionTrimmedPrice = this.config.pricePrecisionDp ? +price.toFixed(this.config.pricePrecisionDp) : price;

    // Initialise the price level, if it doesn't exist yet
    if (!this.activeCandle.priceLevels[precisionTrimmedPrice]) {
      this.activeCandle.priceLevels[precisionTrimmedPrice] = {
        volSumAsk: 0,
        volSumBid: 0
      };
    }

    /**
     * A market sell order executes against a passive bid (limit buy order).
     * The highest bid price gets filled.
     */
    if (isSellOrder) {
      this.activeCandle.aggressiveAsk += tradeQty;
      this.activeCandle.priceLevels[precisionTrimmedPrice].volSumBid += tradeQty;
    } else {
      /**
       * A market buy order executes against a passive ask (limit sell order).
       * The lowest ask price gets filled.
       */
      this.activeCandle.aggressiveBid += tradeQty;
      this.activeCandle.priceLevels[precisionTrimmedPrice].volSumAsk += tradeQty;
    }

    // Update high and low
    const lastHigh = this.activeCandle.high ?? price;
    const lastLow = this.activeCandle.low === 0 ? price : this.activeCandle.low;

    this.activeCandle.high = Math.max(lastHigh, price);
    this.activeCandle.low = Math.min(lastLow, price);
    this.activeCandle.close = price;
  }
}
