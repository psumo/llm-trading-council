const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

export const createFormattedDate = (date: Date): string => {
  const dayOfMonth = date.getDate();
  const month = months[date.getMonth()];
  const year = date.getFullYear();
  const hours = date.getHours().toString().padStart(2, '0');
  const minutes = date.getMinutes().toString().padStart(2, '0');
  const seconds = date.getSeconds().toString().padStart(2, '0');

  return `${dayOfMonth} ${month} ${year} ${hours}:${minutes}:${seconds}`;
};

export const getStartOfMinute = (): Date => {
  const now = new Date();
  now.setSeconds(0, 0);
  return now;
};

/**
 * Get the oldest date in an array of dates
 */
export function getOldestDate(arrayOfDates: Date[]): Date {
  return arrayOfDates.reduce((c, n) => (n < c ? n : c));
}

/**
 * Get the most recent data in an array of dates
 */
export function getNewestDate(arrayOfDates: Date[]): Date {
  return arrayOfDates.reduce((c, n) => (n > c ? n : c));
}

export function getTimestampStartOfDay(startAt: string) {
  const timestamp = Number(startAt);

  const dayInMilliseconds = 24 * 60 * 60 * 1000; // Number of milliseconds in a day

  // Calculate the start of the day in UTC
  // Subtract the remainder when dividing the timestamp by the number of milliseconds in a day
  // This aligns the time to 00:00:00 UTC on the same day
  const startOfDayTimestamp = timestamp - (timestamp % dayInMilliseconds);

  return startOfDayTimestamp;
}

export function adjustBackfillStartDate(processedTimestamps: { [interval: string]: { first: number; last: number } }, originalStartDate: number) {
  const timestamps = Object.values(processedTimestamps)
    .map((ts) => ts.last)
    .filter((t) => t != null);

  // Find the latest timestamp or use the original start date in milliseconds
  let latestLast = Math.max(...timestamps, originalStartDate);

  // Subtract one day in milliseconds
  latestLast -= 24 * 60 * 60 * 1000;

  // Adjust to start of the day in UTC
  latestLast -= latestLast % (24 * 60 * 60 * 1000);

  // No need to convert back to Date, latestLast is the adjusted timestamp
  return latestLast;
}

export function adjustBackfillEndDate(processedTimestamps: { [interval: string]: { first: number; last: number } }, originalEndDate: number) {
  const timestamps: number[] = Object.values(processedTimestamps)
    .map((ts) => ts.first)
    .filter((t) => t != null);

  // Use Math.max to find the latest timestamp or the originalEndDate as milliseconds
  const earliestFirst: number = Math.max(...timestamps, originalEndDate);

  // Align to the start of the day in UTC
  const dayInMilliseconds = 24 * 60 * 60 * 1000; // Number of milliseconds in a day
  const adjustedEndDate = earliestFirst - (earliestFirst % dayInMilliseconds);

  // Return the adjusted Unix timestamp for the start of the day
  return adjustedEndDate;
}
