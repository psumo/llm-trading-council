import { Instrument } from 'okx-api';
import { roundToTickSize } from '@shared/utils/math';

export function getRoundedAssetPrice(symbol: string, assetPrice: number, instruments: Instrument[]): number {
  const instrument = instruments.find((sym) => sym.instId === symbol);
  const tickSize = instrument?.tickSz || 1;

  return roundToTickSize(assetPrice, String(tickSize));
}

export function normaliseSymbolName(instrumentId: string): string {
  return instrumentId.replace(/-SWAP$/, '').replace(/-/g, '');
}
