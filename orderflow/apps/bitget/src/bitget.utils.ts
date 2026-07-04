import { FuturesSymbolRule } from 'bitget-api';
import { roundToTickSize } from '@shared/utils/math';

export function getRoundedAssetPrice(symbol: string, assetPrice: number, symbols: FuturesSymbolRule[]): number {
  const instrument = symbols.find((sym) => sym.symbol === symbol);

  if (!instrument) {
    return 1;
  }

  const tickSize =
    instrument.priceEndStep !== '1'
      ? instrument.priceEndStep
      : instrument.pricePlace
        ? (1 / Math.pow(10, parseInt(instrument.pricePlace))).toString()
        : '1';

  return roundToTickSize(assetPrice, tickSize);
}
