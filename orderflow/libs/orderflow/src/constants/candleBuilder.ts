import { INTERVALS } from '@shared/utils/intervals';

export const CANDLE_BUILDER_RULES = Object.freeze({
  [INTERVALS.ONE_MINUTE]: [
    {
      target: INTERVALS.FIVE_MINUTES,
      condition: (timestamp: number) => [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55].includes(new Date(timestamp).getUTCMinutes())
    },
    { target: INTERVALS.FIFTEEN_MINUTES, condition: (timestamp: number) => [0, 15, 30, 45].includes(new Date(timestamp).getUTCMinutes()) },
    { target: INTERVALS.THIRTY_MINUTES, condition: (timestamp: number) => [0, 30].includes(new Date(timestamp).getUTCMinutes()) },
    { target: INTERVALS.ONE_HOUR, condition: (timestamp: number) => new Date(timestamp).getUTCMinutes() === 0 }
  ],
  [INTERVALS.FIVE_MINUTES]: [
    { target: INTERVALS.FIFTEEN_MINUTES, condition: (timestamp: number) => [0, 15, 30, 45].includes(new Date(timestamp).getUTCMinutes()) },
    { target: INTERVALS.THIRTY_MINUTES, condition: (timestamp: number) => [0, 30].includes(new Date(timestamp).getUTCMinutes()) },
    { target: INTERVALS.ONE_HOUR, condition: (timestamp: number) => new Date(timestamp).getUTCMinutes() === 0 },
    {
      target: INTERVALS.TWO_HOURS,
      condition: (timestamp: number) =>
        new Date(timestamp).getUTCMinutes() === 0 && [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22].includes(new Date(timestamp).getUTCHours())
    }
  ],
  [INTERVALS.FIFTEEN_MINUTES]: [
    { target: INTERVALS.THIRTY_MINUTES, condition: (timestamp: number) => [0, 30].includes(new Date(timestamp).getUTCMinutes()) },
    { target: INTERVALS.ONE_HOUR, condition: (timestamp: number) => new Date(timestamp).getUTCMinutes() === 0 },
    {
      target: INTERVALS.TWO_HOURS,
      condition: (timestamp: number) =>
        new Date(timestamp).getUTCMinutes() === 0 && [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22].includes(new Date(timestamp).getUTCHours())
    },
    {
      target: INTERVALS.FOUR_HOURS,
      condition: (timestamp: number) => new Date(timestamp).getUTCMinutes() === 0 && [0, 4, 8, 12, 16, 20].includes(new Date(timestamp).getUTCHours())
    }
  ],
  [INTERVALS.THIRTY_MINUTES]: [
    { target: INTERVALS.ONE_HOUR, condition: (timestamp: number) => new Date(timestamp).getUTCMinutes() === 0 },
    {
      target: INTERVALS.TWO_HOURS,
      condition: (timestamp: number) =>
        new Date(timestamp).getUTCMinutes() === 0 && [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22].includes(new Date(timestamp).getUTCHours())
    },
    {
      target: INTERVALS.FOUR_HOURS,
      condition: (timestamp: number) => new Date(timestamp).getUTCMinutes() === 0 && [0, 4, 8, 12, 16, 20].includes(new Date(timestamp).getUTCHours())
    }
  ],
  [INTERVALS.ONE_HOUR]: [
    {
      target: INTERVALS.TWO_HOURS,
      condition: (timestamp: number) =>
        new Date(timestamp).getUTCMinutes() === 0 && [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22].includes(new Date(timestamp).getUTCHours())
    },
    {
      target: INTERVALS.FOUR_HOURS,
      condition: (timestamp: number) => new Date(timestamp).getUTCMinutes() === 0 && [0, 4, 8, 12, 16, 20].includes(new Date(timestamp).getUTCHours())
    },
    {
      target: INTERVALS.EIGHT_HOURS,
      condition: (timestamp: number) => new Date(timestamp).getUTCMinutes() === 0 && [0, 8, 16].includes(new Date(timestamp).getUTCHours())
    }
  ],
  [INTERVALS.TWO_HOURS]: [
    {
      target: INTERVALS.FOUR_HOURS,
      condition: (timestamp: number) => new Date(timestamp).getUTCMinutes() === 0 && [0, 4, 8, 12, 16, 20].includes(new Date(timestamp).getUTCHours())
    },
    {
      target: INTERVALS.SIX_HOURS,
      condition: (timestamp: number) => new Date(timestamp).getUTCMinutes() === 0 && [0, 6, 12, 18].includes(new Date(timestamp).getUTCHours())
    },
    {
      target: INTERVALS.EIGHT_HOURS,
      condition: (timestamp: number) => new Date(timestamp).getUTCMinutes() === 0 && [0, 8, 16].includes(new Date(timestamp).getUTCHours())
    }
  ],
  [INTERVALS.FOUR_HOURS]: [
    {
      target: INTERVALS.TWELVE_HOURS,
      condition: (timestamp: number) => new Date(timestamp).getUTCMinutes() === 0 && [0, 12].includes(new Date(timestamp).getUTCHours())
    },
    { target: INTERVALS.ONE_DAY, condition: (timestamp: number) => new Date(timestamp).getUTCMinutes() === 0 && new Date(timestamp).getUTCHours() === 0 }
  ],
  [INTERVALS.SIX_HOURS]: [
    {
      target: INTERVALS.TWELVE_HOURS,
      condition: (timestamp: number) => new Date(timestamp).getUTCMinutes() === 0 && [0, 12].includes(new Date(timestamp).getUTCHours())
    },
    { target: INTERVALS.ONE_DAY, condition: (timestamp: number) => new Date(timestamp).getUTCMinutes() === 0 && new Date(timestamp).getUTCHours() === 0 }
  ],
  [INTERVALS.TWELVE_HOURS]: [
    { target: INTERVALS.ONE_DAY, condition: (timestamp: number) => new Date(timestamp).getUTCMinutes() === 0 && new Date(timestamp).getUTCHours() === 0 }
  ],
  [INTERVALS.ONE_DAY]: [
    {
      target: INTERVALS.ONE_WEEK,
      condition: (timestamp: number) =>
        new Date(timestamp).getUTCMinutes() === 0 && new Date(timestamp).getUTCHours() === 0 && new Date(timestamp).getUTCDay() === 0
    }
  ],
  [INTERVALS.ONE_WEEK]: [
    {
      target: INTERVALS.ONE_MONTH,
      condition: (timestamp: number) => {
        const date = new Date(timestamp);
        return date.getUTCMinutes() + date.getUTCHours() + (date.getUTCDate() - 1) === 0;
      }
    }
  ],
  [INTERVALS.ONE_MONTH]: []
});
