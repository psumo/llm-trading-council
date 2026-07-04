import { intervalToMinutesMap } from '@orderflow/constants/aggregation';
import { INTERVALS } from '@shared/utils/intervals';

export function calculateCandlesNeeded(baseIntervalDurationMs: number, targetIntervalDurationMs: number): number {
  return targetIntervalDurationMs / baseIntervalDurationMs;
}

export function findAllEffectedHTFIntervalsOnCandleClose(date: Date, aggregationIntervals: INTERVALS[]): INTERVALS[] {
  const intervals: INTERVALS[] = [];
  const minute = date.getMinutes();
  const hour = date.getHours();
  const totalMinutes = hour * 60 + minute;
  const day = date.getDay(); // Sunday - Saturday : 0 - 6
  const dateOfMonth = date.getDate(); // 1 - 31

  aggregationIntervals.forEach((interval) => {
    if (interval === INTERVALS.ONE_WEEK && day === 1 && hour === 0 && minute === 0) {
      // Check for Monday
      intervals.push(interval);
    } else if (interval === INTERVALS.ONE_MONTH && dateOfMonth === 1 && hour === 0 && minute === 0) {
      intervals.push(interval);
    } else {
      const intervalDuration = intervalToMinutesMap[interval];
      if (intervalDuration && totalMinutes % intervalDuration === 0) {
        intervals.push(interval);
      }
    }
  });

  return intervals;
}
