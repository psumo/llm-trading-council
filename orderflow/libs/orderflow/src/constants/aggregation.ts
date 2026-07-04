import { INTERVALS } from '@shared/utils/intervals';

export const intervalToMinutesMap = Object.freeze({
  '5m': 5,
  '15m': 15,
  '30m': 30,
  '1h': 60,
  '2h': 120,
  '3h': 180,
  '4h': 240,
  '6h': 360,
  '8h': 480,
  '12h': 720,
  '1d': 1440
});

export const aggregationIntervalMap = Object.freeze({
  [INTERVALS.FIVE_MINUTES]: { baseInterval: INTERVALS.ONE_MINUTE, count: 5 },
  [INTERVALS.FIFTEEN_MINUTES]: { baseInterval: INTERVALS.FIVE_MINUTES, count: 3 },
  [INTERVALS.THIRTY_MINUTES]: { baseInterval: INTERVALS.FIFTEEN_MINUTES, count: 2 },
  [INTERVALS.ONE_HOUR]: { baseInterval: INTERVALS.THIRTY_MINUTES, count: 2 },
  [INTERVALS.TWO_HOURS]: { baseInterval: INTERVALS.ONE_HOUR, count: 2 },
  [INTERVALS.FOUR_HOURS]: { baseInterval: INTERVALS.ONE_HOUR, count: 4 },
  [INTERVALS.EIGHT_HOURS]: { baseInterval: INTERVALS.ONE_HOUR, count: 8 },
  [INTERVALS.TWELVE_HOURS]: { baseInterval: INTERVALS.ONE_HOUR, count: 12 },
  [INTERVALS.ONE_DAY]: { baseInterval: INTERVALS.ONE_HOUR, count: 2 },
  [INTERVALS.ONE_WEEK]: { baseInterval: INTERVALS.ONE_DAY, count: 7 },
  [INTERVALS.ONE_MONTH]: { baseInterval: INTERVALS.ONE_WEEK, count: 4 }
});
