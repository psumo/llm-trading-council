export interface TradeResponse {
  topic: string;
  type: string;
  ts: number;
  data: TradeData[];
}

export interface TradeData {
  T: number; // timestamp
  s: string; // symbol
  S: string; // side (Buy/Sell)
  v: string; // volume
  p: number; // price
  L: string; // tick direction
  i: string; // trade id
  BT: boolean; // breakout trade
}
