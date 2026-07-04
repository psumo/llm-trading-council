import { Injectable, Logger } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { FindManyOptions, LessThanOrEqual, MoreThanOrEqual, Repository } from 'typeorm';
import { CandleUniqueColumns, FootPrintCandle } from '@database/entity/footprint_candle.entity';
import { IFootPrintClosedCandle } from '@orderflow/dto/orderflow.dto';
import { CACHE_LIMIT } from '@shared/constants/exchange';

@Injectable()
export class DatabaseService {
  private logger: Logger = new Logger(DatabaseService.name);

  constructor(
    @InjectRepository(FootPrintCandle)
    private footprintCandleRepository: Repository<FootPrintCandle>
  ) {}

  async batchSaveFootPrintCandles(candles: IFootPrintClosedCandle[]): Promise<string[]> {
    const saved: string[] = [];
    const totalCandles = candles.length;
    try {
      for (let index = 0; index < totalCandles; index++) {
        const candle = candles[index];
        this.logger.log(`Processing candle ${index + 1}/${totalCandles}, ${candle.interval} ${candle.openTime}`);
        const cleanedCandle = { ...candle };
        delete cleanedCandle.uuid;

        await this.footprintCandleRepository.upsert(cleanedCandle, {
          conflictPaths: CandleUniqueColumns,
          upsertType: 'on-conflict-do-update',
          skipUpdateIfNoValuesChanged: true
        });

        if (candle?.uuid) saved.push(candle.uuid);
      }
    } catch (error) {
      console.error('Error bulk inserting FootPrintCandles:', error);
    }
    return saved;
  }

  async getCandles(exchange: string, symbol: string, interval: string, start?: number, end?: number): Promise<IFootPrintClosedCandle[]> {
    try {
      const whereConditions: any = {
        exchange,
        symbol,
        interval
      };

      if (start) {
        whereConditions['openTimeMs'] = MoreThanOrEqual(start);
      }

      if (end) {
        whereConditions['closeTimeMs'] = LessThanOrEqual(end);
      }

      const queryOptions: FindManyOptions<FootPrintCandle> = {
        where: whereConditions,
        order: { openTime: 'ASC' as const }
      };

      const rows = await this.footprintCandleRepository.find(queryOptions);

      const candles: IFootPrintClosedCandle[] = rows.map(
        (row) =>
          ({
            ...row,
            didPersistToStore: true,
            isClosed: true,
            openTime: new Date(row.openTime).toISOString(),
            closeTime: new Date(row.closeTime).toISOString()
          } as IFootPrintClosedCandle)
      );

      return candles;
    } catch (error) {
      console.error('Error fetching aggregated candles:', error);
      throw error;
    }
  }

  async pruneOldData(): Promise<void> {
    try {
      await this.footprintCandleRepository.query(`
        WITH ranked_rows AS (
          SELECT id, ROW_NUMBER() OVER (
            PARTITION BY exchange, symbol, interval ORDER BY "openTime" DESC
          ) row_number
          FROM footprint_candle
        )
        DELETE FROM footprint_candle
        WHERE id IN (
          SELECT id FROM ranked_rows WHERE row_number > ${CACHE_LIMIT}
        )
      `);
    } catch (err) {
      this.logger.error('Failed to prune old data:', err);
    }
  }

  /** Fetch the last and first stored timestamp data to understand the range of stored data. Timestamp is the openTime for kLines */
  async getTimestampRange(
    exchange: string,
    symbol?: string
  ): Promise<{
    [symbol: string]: {
      [interval: string]: {
        first: number;
        last: number;
      };
    };
  }> {
    try {
      const params = symbol ? [exchange, symbol] : [exchange];
      const query = `
      SELECT symbol, interval, MAX("openTime") as max_timestamp, MIN("openTime") as min_timestamp
      FROM footprint_candle
      WHERE exchange = $1${symbol ? ' AND symbol = $2' : ''}
      GROUP BY symbol, interval
    `;

      const result = await this.footprintCandleRepository.query(query, params);
      const resultMap: {
        [symbol: string]: {
          [interval: string]: {
            first: number;
            last: number;
          };
        };
      } = {};

      result.forEach((row) => {
        if (!resultMap[row.symbol]) {
          resultMap[row.symbol] = {};
        }
        resultMap[row.symbol][row.interval] = {
          last: row.max_timestamp ? new Date(row.max_timestamp).getTime() : 0,
          first: row.min_timestamp ? new Date(row.min_timestamp).getTime() : 0
        };
      });

      return resultMap;
    } catch (err) {
      this.logger.error('Failed to retrieve timestamp ranges:', err);
      return {};
    }
  }

  async findGapsInData(exchange: string, symbol: string, interval: string, timeGapInMilliseconds: number): Promise<any[]> {
    const query = `
      WITH OrderedCandles AS (
        SELECT
          id,
          "openTime",
          LAG("openTime") OVER (PARTITION BY exchange, symbol, interval ORDER BY "openTime") as prevOpenTime
        FROM
          footprint_candle
        WHERE
          exchange = $1
          AND symbol = $2
          AND interval = $3
      ),
      Gaps AS (
        SELECT
          id,
          "openTime",
          prevOpenTime,
          EXTRACT(EPOCH FROM ("openTime" - prevOpenTime)) * 1000 as timeDifference -- Convert interval to milliseconds
        FROM
          OrderedCandles
        WHERE
          prevOpenTime IS NOT NULL -- Exclude the first row which has no previous row
      )
      SELECT
        id,
        "openTime",
        prevOpenTime,
        timeDifference
      FROM
        Gaps
      WHERE
        timeDifference > $4; -- The gap is larger than specified time gap in milliseconds
    `;

    try {
      return await this.footprintCandleRepository.query(query, [exchange, symbol, interval, timeGapInMilliseconds]);
    } catch (error) {
      this.logger.error('Error finding gaps in data:', error);
      throw error;
    }
  }
}
