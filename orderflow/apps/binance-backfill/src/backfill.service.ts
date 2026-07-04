import { HttpService } from '@nestjs/axios';
import { Injectable, Logger } from '@nestjs/common';
import { parse } from 'csv-parse/sync';
import * as JSZip from 'jszip';
import { firstValueFrom } from 'rxjs';
import { DatabaseService } from '@database';
import { CANDLE_BUILDER_RULES } from '@orderflow/constants';
import { IAggregatedTrade } from '@orderflow/dto/binanceData.dto';
import { IFootPrintClosedCandle } from '@orderflow/dto/orderflow.dto';
import { calculateCandlesNeeded } from '@orderflow/utils/candleBuildHelper';
import { adjustBackfillEndDate, adjustBackfillStartDate, getTimestampStartOfDay } from '@orderflow/utils/date';
import { OrderFlowAggregator } from '@orderflow/utils/orderFlowAggregator';
import { mergeFootPrintCandles } from '@orderflow/utils/orderFlowUtil';
import { Exchange } from '@shared/constants/exchange';
import { INTERVALS, KlineIntervalMs, KlineIntervalTimes } from '@shared/utils/intervals';

@Injectable()
export class BackfillService {
  private readonly baseUrl = 'https://data.binance.vision/data/futures/um/daily/aggTrades';
  private readonly BASE_INTERVAL = INTERVALS.ONE_MINUTE;
  private currTestMinute: number = new Date().getTime();
  private nextMinuteCandleClose: number = new Date().getTime();

  protected symbols: string[] = process.env.SYMBOLS ? process.env.SYMBOLS.split(',') : ['BTCUSDT'];
  private readonly BASE_SYMBOL = this.symbols.shift() as string;

  private timestampsRange: {
    [symbol: string]: {
      [interval: string]: {
        first: number;
        last: number;
      };
    };
  } = {};

  private logger: Logger = new Logger(BackfillService.name);

  private aggregators: { [symbol: string]: OrderFlowAggregator } = {};
  private candles: { [key: string]: IFootPrintClosedCandle[] } = {
    [INTERVALS.ONE_MINUTE]: [],
    [INTERVALS.FIVE_MINUTES]: [],
    [INTERVALS.FIFTEEN_MINUTES]: [],
    [INTERVALS.THIRTY_MINUTES]: [],
    [INTERVALS.ONE_HOUR]: [],
    [INTERVALS.TWO_HOURS]: [],
    [INTERVALS.FOUR_HOURS]: [],
    [INTERVALS.SIX_HOURS]: [],
    [INTERVALS.TWELVE_HOURS]: [],
    [INTERVALS.ONE_DAY]: [],
    [INTERVALS.ONE_WEEK]: [],
    [INTERVALS.ONE_MONTH]: []
  };

  constructor(private readonly databaseService: DatabaseService, private readonly httpService: HttpService) {}

  async onModuleInit() {
    console.time(`Backfilling for ${this.BASE_SYMBOL} took`);
    this.logger.log('start backfilling');

    await this.checkForGaps();

    this.setupTradeAggregator();

    await this.getStoredFirstAndLastTimestamps(this.BASE_SYMBOL);
    this.logStoredTimestampsRange();

    // We need to populate 1D, 1W, 1M to build HTF candles
    await this.populateHTFStoredCandles();

    await this.downloadAndProcessCsvFiles();
    // this.logFirstAndLastCandles()
    console.timeEnd(`Backfilling for ${this.BASE_SYMBOL} took`);
  }

  private setupTradeAggregator(): void {
    const intervalSizeMs: number = KlineIntervalMs[INTERVALS.ONE_MINUTE];
    this.aggregators[this.BASE_SYMBOL] = new OrderFlowAggregator(Exchange.BINANCE, this.BASE_SYMBOL, INTERVALS.ONE_MINUTE, intervalSizeMs, {});
  }

  private async checkForGaps(): Promise<void> {
    for (const interval of Object.keys(this.candles)) {
      const gaps = await this.databaseService.findGapsInData(Exchange.BINANCE, this.BASE_SYMBOL, interval, KlineIntervalMs[interval]);
      // Log the number of gaps
      this.logger.log(`${interval}: Total Gaps - ${gaps.length}`);

      // Only print the gap details when there are fewer than 10 gaps
      if (gaps.length < 10) {
        this.logger.log(`${interval}: Gap Details -`, gaps);
      }

      // Add a visual separator after each interval's output
      this.logger.log('--------------------------------------------------');
    }
  }

  private async populateHTFStoredCandles(): Promise<void> {
    this.candles[INTERVALS.ONE_DAY] = (await this.databaseService.getCandles(Exchange.BINANCE, this.BASE_SYMBOL, INTERVALS.ONE_DAY)) ?? [];
    this.candles[INTERVALS.ONE_WEEK] = (await this.databaseService.getCandles(Exchange.BINANCE, this.BASE_SYMBOL, INTERVALS.ONE_WEEK)) ?? [];
    this.candles[INTERVALS.ONE_MONTH] = (await this.databaseService.getCandles(Exchange.BINANCE, this.BASE_SYMBOL, INTERVALS.ONE_MONTH)) ?? [];
  }

  private logStoredTimestampsRange(): void {
    const earliestTimestamp = Math.min(...Object.values(this.timestampsRange[this.BASE_SYMBOL]).map((range) => range.first));
    const latestTimestamp = Math.max(...Object.values(this.timestampsRange[this.BASE_SYMBOL]).map((range) => range.last));

    this.logger.log('==================== Timestamp Range ====================');
    this.logger.log(`Earliest timestamp for ${this.BASE_SYMBOL} found is ${new Date(earliestTimestamp)}`);
    this.logger.log(`Latest timestamp for ${this.BASE_SYMBOL} found is ${new Date(latestTimestamp)}`);
    for (const interval of Object.keys(this.timestampsRange[this.BASE_SYMBOL])) {
      const { first, last } = this.timestampsRange[this.BASE_SYMBOL][interval];
      this.logger.log(
        `Interval: ${interval}, First: ${new Date(first).toISOString().replace('T', ' ').substring(0, 19)}, Last: ${new Date(last)
          .toISOString()
          .replace('T', ' ')
          .substring(0, 19)}`
      );
    }
    this.logger.log('==========================================================');
  }

  private logFirstAndLastCandles(): void {
    Object.keys(this.candles).forEach((interval: INTERVALS) => {
      this.logger.log(`${interval} has ${this.candles[interval].length} candles`);
      this.logger.log(`${interval} first open candle ${this.candles[interval]?.[0]?.openTime}`);
      this.logger.log(`${interval} last open candle ${this.candles[interval]?.[this.candles[interval].length - 1]?.openTime}`);
    });
  }

  private async saveData(): Promise<void> {
    this.logger.log('saving data');
    console.time('Saving data completed');

    for (const interval of Object.keys(this.candles)) {
      // Filter candles that have not been persisted to the store
      const candles = this.candles[interval].filter((candle) => !candle.didPersistToStore);
      if (candles.length > 0) {
        this.logger.log(`Processing ${candles.length} candles for interval ${interval}`);

        // Save the candles for the current interval
        const savedUUIDs = await this.databaseService.batchSaveFootPrintCandles(candles);

        this.logger.log(`Successfully saved ${savedUUIDs.length} out of ${candles.length} candles for interval ${interval}`);

        // Update didPersistToStore to true for saved candles
        for (const candle of this.candles[interval]) {
          if (candle.uuid && savedUUIDs.includes(candle?.uuid)) {
            candle.didPersistToStore = true;
          }
        }
        // TODO: Check whether the candles were saved. Handle ones that aren't saved
      }
    }
    console.timeEnd('Saving data completed');
  }

  /** Clear after each file is processed and saved, otherwise the heap size would grow too large. Don't clear 1d, 1w, 1M */
  private clearCandles(): void {
    for (const interval of Object.keys(this.candles)) {
      this.candles[interval] = [];
    }
  }

  async getStoredFirstAndLastTimestamps(symbol: string) {
    if (!this.timestampsRange[symbol]) {
      this.timestampsRange[symbol] = {};
    }

    const resultMap = await this.databaseService.getTimestampRange(Exchange.BINANCE, symbol);

    for (const interval in resultMap[symbol]) {
      // Store the timestamp range for each interval in the symbol's data
      this.timestampsRange[symbol][interval] = resultMap[symbol][interval];
    }
  }

  private checkAndBuildLargerTimeframeCandles(baseInterval: INTERVALS, targetInterval: INTERVALS, value: IFootPrintClosedCandle) {
    const rules = CANDLE_BUILDER_RULES[baseInterval];
    const targetRule = rules?.find((rule) => rule.target === targetInterval) ?? rules?.[0];
    let openTime: number = value.openTimeMs;
    const { amount, duration } = KlineIntervalTimes[baseInterval];

    if (!targetRule) {
      return;
    }

    if (duration === 'minutes') {
      openTime += amount * 60 * 1000; // 60 seconds * 1000 ms
    } else if (duration === 'h') {
      // Convert 'amount' from hours to milliseconds
      openTime += amount * 60 * 60 * 1000; // 60 minutes * 60 seconds * 1000 ms
    }

    if (targetRule?.condition(openTime)) {
      const numCandlesNeeded: number = calculateCandlesNeeded(KlineIntervalMs[baseInterval], KlineIntervalMs[targetRule.target]);

      if (this.candles[baseInterval].length >= numCandlesNeeded) {
        const candles: IFootPrintClosedCandle[] = this.candles[baseInterval].slice(-numCandlesNeeded);
        const newCandle: IFootPrintClosedCandle = mergeFootPrintCandles(candles, targetRule.target);

        const nextBase: INTERVALS = targetRule.target;
        const nextTarget: INTERVALS = targetRule.target;

        this.candles[targetRule.target].push(newCandle);
        this.checkAndBuildLargerTimeframeCandles(nextBase, nextTarget, newCandle);
      }
    }
  }

  private async closeAndPrepareNextCandle(): Promise<void> {
    const closedCandle: IFootPrintClosedCandle | undefined = this.aggregators[this.BASE_SYMBOL].retireActiveCandle();

    if (closedCandle) {
      this.candles[this.BASE_INTERVAL].push(closedCandle);
    }

    this.checkAndBuildLargerTimeframeCandles(
      this.BASE_INTERVAL,
      INTERVALS.FIVE_MINUTES,
      this.candles[INTERVALS.ONE_MINUTE][this.candles[INTERVALS.ONE_MINUTE].length - 1]
    );

    this.incrementTestMinute();
    this.aggregators[this.BASE_SYMBOL].createNewCandle();
  }

  private processTradeRow(trade: IAggregatedTrade): void {
    const isBuyerMaker: boolean = trade.is_buyer_maker === 'true';
    const quantity: number = Number(trade.quantity);
    const price: number = Number(trade.price);
    this.aggregators[this.BASE_SYMBOL].processNewTrades(isBuyerMaker, quantity, price);
  }

  private incrementTestMinute(): void {
    this.currTestMinute = this.nextMinuteCandleClose;
    this.nextMinuteCandleClose = this.nextMinuteCandleClose + 60 * 1000;
    this.aggregators[this.BASE_SYMBOL].simulationMinute = this.currTestMinute;
  }

  private async downloadAndProcessCsvFiles() {
    const selectedBackfillStartAt = getTimestampStartOfDay(process.env.BACKFILL_START_AT as string);
    const selectedBackfillEndAt = getTimestampStartOfDay(process.env.BACKFILL_END_AT as string);
    this.logger.log('========== Backfill Time Selection ==========');
    this.logger.log(`Selected backfillStartAt ${selectedBackfillStartAt}`);
    this.logger.log(`Selected backfillEndAt: ${selectedBackfillEndAt}`);

    const backfillStartAt = adjustBackfillStartDate(this.timestampsRange[this.BASE_SYMBOL], getTimestampStartOfDay(process.env.BACKFILL_START_AT as string));
    const backfillEndAt = adjustBackfillEndDate(this.timestampsRange[this.BASE_SYMBOL], getTimestampStartOfDay(process.env.BACKFILL_END_AT as string));
    this.logger.log(`Adjusted backfillStartAt: ${backfillStartAt}`);
    this.logger.log(`Adjusted backfillEndAt: ${backfillEndAt}`);
    this.logger.log('============================================');
    let currentTestDate = backfillStartAt;

    console.time(`Downloading and processing aggTrades ${backfillStartAt} - ${backfillEndAt}`);

    this.currTestMinute = backfillStartAt;
    this.nextMinuteCandleClose = this.currTestMinute + 60 * 1000;
    this.aggregators[this.BASE_SYMBOL].simulationMinute = this.currTestMinute;

    this.logger.log(`currTestMinute: ${this.currTestMinute}`);
    this.logger.log(`nextMinuteCandleClose: ${this.nextMinuteCandleClose}`);

    while (currentTestDate <= backfillEndAt) {
      const date = new Date(currentTestDate);
      const dateString = date.toISOString().split('T')[0];
      const fileUrl = `${this.baseUrl}/${this.BASE_SYMBOL}/${this.BASE_SYMBOL}-aggTrades-${dateString}.zip`;

      try {
        console.time(`downloading ${fileUrl}`);
        const response: any = await firstValueFrom(
          this.httpService.get(fileUrl, {
            responseType: 'arraybuffer'
          })
        );
        console.timeEnd(`downloading ${fileUrl}`);

        console.time(`extracting ${fileUrl}`);
        const zip = await JSZip.loadAsync(response.data);
        const csvFileName: string = Object.keys(zip.files)[0];
        const csvFile: string = await zip.files[csvFileName].async('string');
        console.timeEnd(`extracting ${fileUrl}`);

        console.time(`parsing ${fileUrl}`);
        const trades = parse(csvFile, {
          columns: true,
          skip_empty_lines: true
        });
        console.timeEnd(`parsing ${fileUrl}`);

        console.time('Processing trades');
        this.logger.log(`trades ${trades.length}`);
        for (let i = 0; i < trades.length; i++) {
          const trade: IAggregatedTrade = trades[i];
          const transactTimestamp: number = Number(trade.transact_time);

          if (transactTimestamp >= this.nextMinuteCandleClose || i === trades.length - 1) {
            await this.closeAndPrepareNextCandle();
          }
          this.processTradeRow(trade);
        }
        console.timeEnd('Processing trades');

        this.logger.log(`Downloaded and parsed file for ${dateString}`);

        // Clear up memory by saving & removing candles in memory
        await this.saveData();
        this.clearCandles();
      } catch (error) {
        this.logger.error(`Failed to download or process the file for ${dateString}:`, error);
      }

      currentTestDate += 24 * 60 * 60 * 1000;
    }
    console.timeEnd(`Downloading and processing aggTrades ${backfillStartAt} - ${backfillEndAt}`);
  }
}
