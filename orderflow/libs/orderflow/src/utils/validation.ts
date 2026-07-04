import { Logger } from '@nestjs/common';

export function validateEnvironment() {
  const backfillStartAtStr: string | undefined = process.env.BACKFILL_START_AT;
  const backfillEndAtStr: string | undefined = process.env.BACKFILL_END_AT;
  const pairsString: string | undefined = process.env.SYMBOLS;
  let pairs: string[] = [];

  // Convert environment variables to numbers for timestamp validation
  const backfillStartAt = Number(backfillStartAtStr);
  const backfillEndAt = Number(backfillEndAtStr);
  const now = new Date().getTime();
  const fourYearsAgo = new Date(new Date().setFullYear(new Date().getFullYear() - 4)).getTime();
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);

  if (isNaN(backfillStartAt)) {
    Logger.error(`BACKFILL_START_AT is not a valid timestamp. Current value: '${backfillStartAtStr}'`, 'EnvironmentValidation');
    return false;
  } else if (backfillStartAt <= fourYearsAgo) {
    Logger.error(
      `BACKFILL_START_AT must be a timestamp from the last four years and before today. Expected after ${new Date(fourYearsAgo).toISOString().split('T')[0]}`,
      'EnvironmentValidation'
    );
    return false;
  } else if (backfillStartAt >= now) {
    Logger.error(`BACKFILL_START_AT must be before today. Current value: ${new Date(backfillStartAt).toISOString().split('T')[0]}`, 'EnvironmentValidation');
    return false;
  }

  if (isNaN(backfillEndAt)) {
    Logger.error(`BACKFILL_END_AT is not a valid timestamp. Current value: '${backfillEndAtStr}'`, 'EnvironmentValidation');
    return false;
  } else if (backfillEndAt <= backfillStartAt) {
    Logger.error(
      `BACKFILL_END_AT must be greater than BACKFILL_START_AT. Current value: ${new Date(backfillEndAt).toISOString().split('T')[0]}`,
      'EnvironmentValidation'
    );
    return false;
  } else if (backfillEndAt > yesterday.getTime()) {
    Logger.error(
      // eslint-disable-next-line max-len
      `BACKFILL_END_AT must be less than or equal to yesterday to align with the last available data file in aggTrades (e.g., BTCUSDT-aggTrades-2024-03-01.zip for yesterday's data). Current value: ${
        new Date(backfillEndAt).toISOString().split('T')[0]
      }`,
      'EnvironmentValidation'
    );
    return false;
  }

  // Check if SYMBOLS is a non-empty string
  if (typeof pairsString !== 'string' || pairsString.trim() === '') {
    Logger.error(`SYMBOLS must be a non-empty comma-separated string. Current value: '${pairsString}'`, 'EnvironmentValidation');
    return false;
  }

  // Convert SYMBOLS string to an array and validate it
  pairs = pairsString.split(',');
  if (pairs.length === 0) {
    Logger.error(`SYMBOLS string could not be converted to a valid array. Current value: '${pairsString}'`, 'EnvironmentValidation');
    return false;
  }

  // Check if each pair ends with 'USDT'
  for (const pair of pairs) {
    if (!pair.endsWith('USDT')) {
      Logger.error(`Each pair in SYMBOLS must end with 'USDT'. Invalid pair: '${pair}'`, 'EnvironmentValidation');
      return false;
    }
  }

  return true;
}
