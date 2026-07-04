export interface IFootPrintCandle {
  uuid?: string;
  openTime: string;
  openTimeMs: number;
  closeTime: string;
  closeTimeMs: number;
  exchange: string;
  interval: string;
  symbol: string;
  aggressiveBid: number;
  aggressiveAsk: number;
  volumeDelta: number;
  volume: number;
  high: number;
  low: number;
  close: number;
  /** bid/ask volume grouped by levels (to pricePrecisionDp) */
  priceLevels: { [price: number]: IPriceLevel };
  isClosed: boolean;
}

export type IPriceLevelsClosed = { [price: number]: IPriceLevel };

export type IFootPrintClosedCandle = IFootPrintCandle & {
  priceLevels: IPriceLevelsClosed;
  isClosed: true;
  didPersistToStore: boolean;
};

export interface IPriceLevel {
  volSumBid: number;
  volSumAsk: number;
}
