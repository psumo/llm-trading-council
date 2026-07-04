export enum TIME_PERIODS {
  HOUR = 'hour',
  DAY = 'day',
  WEEK = 'week',
  MONTH = 'month'
}

export enum INTERVALS {
  ONE_MINUTE = '1m',
  THREE_MINUTES = '3m',
  FIVE_MINUTES = '5m',
  FIFTEEN_MINUTES = '15m',
  THIRTY_MINUTES = '30m',
  ONE_HOUR = '1h',
  TWO_HOURS = '2h',
  THREE_HOURS = '3h',
  FOUR_HOURS = '4h',
  SIX_HOURS = '6h',
  EIGHT_HOURS = '8h',
  TWELVE_HOURS = '12h',
  ONE_DAY = '1d',
  THREE_DAYS = '3d',
  ONE_WEEK = '1w',
  ONE_MONTH = '1M',
  THREE_MONTHS = '3M',
  SIX_MONTHS = '6M',
  ONE_YEAR = '1y',
  TWO_YEARS = '2y'
}

export enum KlineIntervals {
  ONE_MIN = '1m',
  FIVE_MINS = '5m',
  FIFTHTEEN_MINS = '15m',
  THIRTY_MINS = '30m',
  ONE_HOUR = '1h',
  TWO_HOURS = '2h',
  FOUR_HOURS = '4h',
  SIX_HOURS = '6h',
  TWELVE_HOURS = '12h',
  ONE_DAY = '1d',
  ONE_WEEK = '1w',
  ONE_MONTH = '1M'
}

export enum OpenInterestIntervals {
  FIVE_MINS = '5m',
  FIFTHTEEN_MINS = '15m',
  THIRTY_MINS = '30m',
  ONE_HOUR = '1h',
  TWO_HOURS = '2h',
  FOUR_HOURS = '4h',
  SIX_HOURS = '6h',
  TWELVE_HOURS = '12h',
  ONE_DAY = '1d'
}

export enum FundingRateIntervals {
  EIGHT_HOURS = '8h'
}

export const KlineIntervalTimes: Record<
  KlineIntervals,
  {
    duration: any;
    amount: any;
  }
> = {
  [KlineIntervals.ONE_MIN]: { duration: 'minutes', amount: 1 },
  [KlineIntervals.FIVE_MINS]: { duration: 'minutes', amount: 5 },
  [KlineIntervals.FIFTHTEEN_MINS]: { duration: 'minutes', amount: 15 },
  [KlineIntervals.THIRTY_MINS]: { duration: 'minutes', amount: 30 },
  [KlineIntervals.ONE_HOUR]: { duration: 'h', amount: 1 },
  [KlineIntervals.TWO_HOURS]: { duration: 'h', amount: 2 },
  [KlineIntervals.FOUR_HOURS]: { duration: 'h', amount: 4 },
  [KlineIntervals.SIX_HOURS]: { duration: 'h', amount: 6 },
  [KlineIntervals.TWELVE_HOURS]: { duration: 'h', amount: 12 },
  [KlineIntervals.ONE_DAY]: { duration: 'd', amount: 1 },
  [KlineIntervals.ONE_WEEK]: { duration: 'week', amount: 1 },
  [KlineIntervals.ONE_MONTH]: { duration: 'month', amount: 1 }
};

export const ONE_MINUTE_MS = 60 * 1000;
export const ONE_HOUR_MS = ONE_MINUTE_MS * 60;

export const KlineIntervalMs: Record<KlineIntervals, number> = {
  [KlineIntervals.ONE_MIN]: ONE_MINUTE_MS,
  [KlineIntervals.FIVE_MINS]: ONE_MINUTE_MS * 5,
  [KlineIntervals.FIFTHTEEN_MINS]: ONE_MINUTE_MS * 15,
  [KlineIntervals.THIRTY_MINS]: ONE_MINUTE_MS * 30,
  [KlineIntervals.ONE_HOUR]: ONE_HOUR_MS,
  [KlineIntervals.TWO_HOURS]: ONE_HOUR_MS * 2,
  [KlineIntervals.FOUR_HOURS]: ONE_HOUR_MS * 4,
  [KlineIntervals.SIX_HOURS]: ONE_HOUR_MS * 6,
  [KlineIntervals.TWELVE_HOURS]: ONE_HOUR_MS * 12,
  [KlineIntervals.ONE_DAY]: ONE_HOUR_MS * 24,
  [KlineIntervals.ONE_WEEK]: ONE_HOUR_MS * 24 * 7,
  [KlineIntervals.ONE_MONTH]: 2591999999 + 1 // 1 month interval size used by binance 1569887999999 - 1567296000000
};
