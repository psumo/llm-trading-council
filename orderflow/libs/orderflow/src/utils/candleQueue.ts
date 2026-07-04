import { DatabaseService } from '@database';
import { RabbitMQService } from '@rabbitmq';
import { IFootPrintClosedCandle } from '@orderflow/dto/orderflow.dto';
import { Exchange } from '@shared/constants/exchange';

export class CandleQueue {
  private exchange: Exchange;

  private queue: IFootPrintClosedCandle[] = [];

  private databaseService: DatabaseService;
  private rabbitmqService: RabbitMQService;

  constructor(exchange: Exchange, databaseService: DatabaseService, rabbitmqService: RabbitMQService) {
    this.exchange = exchange;
    this.databaseService = databaseService;
    this.rabbitmqService = rabbitmqService;
  }

  /** Get only candles that haven't been saved to DB yet */
  public getQueuedCandles(): IFootPrintClosedCandle[] {
    return this.queue.filter((candle) => !candle.didPersistToStore);
  }

  public enqueCandle(candle: IFootPrintClosedCandle): void {
    this.queue.push(candle);
  }

  private clearQueue(): void {
    this.queue = [];
  }

  /** Marks which candles have been saved to DB */
  public markSavedCandles(savedUUIDs: string[]) {
    for (const uuid of savedUUIDs) {
      const candle = this.queue.find((c) => c.uuid === uuid);
      if (candle) {
        candle.didPersistToStore = true;
      } else {
        console.log(`no candle found for uuid (${uuid})`, this.queue);
      }
    }
  }

  public async persistCandlesToStorage({ clearQueue }: { clearQueue: boolean }): Promise<void> {
    const queuedCandles = this.getQueuedCandles();
    if (queuedCandles.length === 0) {
      return;
    }

    console.log(
      'Saving batch of candles',
      queuedCandles.map((c) => `${c.symbol} ${c.interval} ${c.openTime}`)
    );

    const savedUUIDs = await this.databaseService.batchSaveFootPrintCandles([...queuedCandles]);
    const savedCandles = this.queue.filter((candle) => candle.uuid && savedUUIDs.includes(candle.uuid));

    this.markSavedCandles(savedUUIDs);

    if (savedCandles.length > 0) {
      const topics = Array.from(new Set(savedCandles.map((candle) => `${this.exchange}.${candle.symbol}.${candle.interval}.${candle.openTimeMs}`)));
      await this.rabbitmqService.publish('footprint_candles.closed', topics);
    }

    if (clearQueue) {
      this.clearQueue();
    }
  }
}
