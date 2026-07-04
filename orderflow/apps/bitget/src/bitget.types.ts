export interface IWsTrade {
  ts: string;
  price: string;
  size: string;
  side: 'buy' | 'sell';
  tradeId: string;
}

export interface ITrade {
  ts: string;
  symbol: string;
  price: string;
  roundedPrice: number;
  size: string;
  side: 'buy' | 'sell';
  tradeId: string;
}
