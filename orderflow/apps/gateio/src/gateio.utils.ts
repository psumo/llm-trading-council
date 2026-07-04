import { getLowestUnit, roundToTickSize } from '@shared/utils/math';
import { FuturesContract } from 'gateio-api';

export function getRoundedAssetPrice(symbol: string, assetPrice: number, futuresContracts: FuturesContract[]): number {
  const contract = futuresContracts.find((contract) => contract.name === symbol);
  const tickSize = contract?.order_price_round || getLowestUnit(assetPrice);

  return roundToTickSize(assetPrice, tickSize);
}

export function normaliseSymbolName(symbol: string): string {
  return symbol.replace(/_/g, '');
}
