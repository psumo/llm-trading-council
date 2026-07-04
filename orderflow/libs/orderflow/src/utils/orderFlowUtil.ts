import { v4 } from 'uuid';
import { descendingOrder, mergeDedupeArrays } from './array';
import { getNewestDate, getOldestDate } from './date';
import { doMathOnProp } from './math';
import { IFootPrintClosedCandle, IPriceLevelsClosed } from '../dto/orderflow.dto';

export function mergeFootPrintCandles(candles: IFootPrintClosedCandle[], interval: string): IFootPrintClosedCandle {
  if (!candles.length) {
    throw new Error('no candles!');
  }

  const [baseCandle, ...otherCandles] = candles;

  if (otherCandles.length === 0) {
    return baseCandle;
  }

  const aggrCandle: IFootPrintClosedCandle = structuredClone(baseCandle);

  for (const candle of otherCandles) aggregateCandleProperties(aggrCandle, candle);

  return {
    ...aggrCandle,
    uuid: v4(),
    interval,
    openTime: aggrCandle.openTime,
    closeTime: aggrCandle.closeTime,
    isClosed: true,
    didPersistToStore: false
  };
}

function aggregateCandleProperties(aggrCandle: IFootPrintClosedCandle, candle: IFootPrintClosedCandle): void {
  const openDts = [new Date(aggrCandle.openTime), new Date(candle.openTime)];
  const closeDts = [new Date(aggrCandle.closeTime), new Date(candle.closeTime)];

  aggrCandle.openTime = getOldestDate(openDts).toISOString();
  aggrCandle.closeTime = getNewestDate(closeDts).toISOString();

  aggrCandle.volumeDelta = doMathOnProp(aggrCandle, candle, 'volumeDelta', '+');
  aggrCandle.volume = doMathOnProp(aggrCandle, candle, 'volume', '+');

  aggrCandle.aggressiveBid = doMathOnProp(aggrCandle, candle, 'aggressiveBid', '+');
  aggrCandle.aggressiveAsk = doMathOnProp(aggrCandle, candle, 'aggressiveAsk', '+');

  aggrCandle.high = doMathOnProp(aggrCandle, candle, 'high', 'max');
  aggrCandle.low = doMathOnProp(aggrCandle, candle, 'low', 'min');
  aggrCandle.close = candle.close;

  aggrCandle.priceLevels = mergePriceLevels(aggrCandle.priceLevels, candle.priceLevels);
}

/**
 * Merge two price levels into one
 */
function mergePriceLevels(levels1: IPriceLevelsClosed, levels2: IPriceLevelsClosed): IPriceLevelsClosed {
  const levelPrices1 = Object.keys(levels1).map((v) => Number(v));
  const levelPrices2 = Object.keys(levels2).map((v) => Number(v));

  const allLevels = mergeDedupeArrays(levelPrices1, levelPrices2).sort(descendingOrder);

  const mergedLevels: IPriceLevelsClosed = {};
  for (const price of allLevels) {
    const level1 = levels1[price];
    const level2 = levels2[price];

    // When both have a value, merge
    if (level1 && level2) {
      const volSumAsk = level1.volSumAsk + level2.volSumAsk;
      const volSumBid = level1.volSumBid + level2.volSumBid;

      mergedLevels[price] = {
        volSumAsk: volSumAsk,
        volSumBid: volSumBid
      };
      continue;
    }

    // else, only one has a value
    mergedLevels[price] = level1 || level2;
  }

  return mergedLevels;
}
