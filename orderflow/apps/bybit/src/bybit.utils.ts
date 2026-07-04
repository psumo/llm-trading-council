import { APIResponseV3WithTime, InstrumentInfoResponseV5 } from 'bybit-api';
import { roundToTickSize } from '@shared/utils/math';

export function getRoundedAssetPrice(symbol: string, assetPrice: number, instrumentInfo: APIResponseV3WithTime<InstrumentInfoResponseV5<'linear'>>): number {
  const priceFilter = getPriceFilter(instrumentInfo, symbol);
  const tickSize = priceFilter?.tickSize ?? 2; // default to 2 if not found

  return roundToTickSize(assetPrice, String(tickSize));
}

export function getPriceFilter(instrumentInfo: APIResponseV3WithTime<InstrumentInfoResponseV5<'linear'>>, symbol: string) {
  const specs = instrumentInfo.result.list.find((sym) => sym.symbol === symbol);
  if (!specs) {
    return null;
  }

  const priceFilter = specs.priceFilter;

  if (!priceFilter) {
    return null;
  }
  return priceFilter;
}
