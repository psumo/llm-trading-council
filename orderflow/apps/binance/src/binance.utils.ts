import { FuturesExchangeInfo, SymbolPriceFilter } from 'binance';
import { roundToTickSize } from '@shared/utils/math';

export function getRoundedAssetPrice(symbol: string, assetPrice: number, exchangeInfo: FuturesExchangeInfo): number {
  const priceFilter = getPriceFilter(exchangeInfo, symbol);
  const tickSize = priceFilter?.tickSize ?? 2; // default to 2 if not found

  return roundToTickSize(assetPrice, String(tickSize));
}

export function getPriceFilter(exchangeInfo: FuturesExchangeInfo, symbol: string): SymbolPriceFilter | null {
  const specs = exchangeInfo.symbols.find((sym) => sym.symbol === symbol);
  if (!specs) {
    return null;
  }

  const priceFilter = specs.filters.find((filter) => filter.filterType === 'PRICE_FILTER') as SymbolPriceFilter;

  if (!priceFilter) {
    return null;
  }
  return priceFilter;
}
