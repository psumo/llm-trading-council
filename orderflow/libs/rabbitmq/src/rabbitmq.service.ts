import { Injectable, Logger, OnModuleDestroy, OnModuleInit } from '@nestjs/common';
import { Channel, connect, Connection } from 'amqplib';

@Injectable()
export class RabbitMQService implements OnModuleInit, OnModuleDestroy {
  private logger: Logger = new Logger(RabbitMQService.name);

  private connection: Connection;
  private channel: Channel;

  private readonly USE_RABBITMQ = process.env.USE_RABBITMQ === 'true';
  private readonly RABBITMQ_URL = process.env.RABBITMQ_URL || null;
  private readonly EXCHANGE = process.env.RABBITMQ_EXCHANGE || 'default_exchange';

  async onModuleInit() {
    await this.connect();
  }

  async onModuleDestroy() {
    await this.disconnect();
  }

  private async connect() {
    if (!this.USE_RABBITMQ || this.RABBITMQ_URL === null) {
      this.logger.log('RabbitMQ config not set. Skipping connection.');
      return;
    }

    try {
      this.connection = await connect(this.RABBITMQ_URL);
      this.channel = await this.connection.createChannel();
      await this.channel.assertExchange(this.EXCHANGE, 'direct', { durable: true });
      this.logger.log('RabbitMQ connected');
    } catch (error) {
      this.logger.error('RabbitMQ connection failed:', error);
    }
  }

  private async disconnect() {
    if (!this.connection || !this.channel) return;

    try {
      await this.channel.close();
      await this.connection.close();
      this.logger.log('RabbitMQ disconnected');
    } catch (error) {
      this.logger.error('Failed to close RabbitMQ connection:', error);
    }
  }

  async publish(exchangeName: string, message: object) {
    if (!this.connection || !this.channel) return;

    try {
      const messageBuffer = Buffer.from(JSON.stringify(message));
      this.channel.publish(this.EXCHANGE, exchangeName, messageBuffer);
      this.logger.log(`Message published to exchange ${exchangeName}:`, message);
    } catch (error) {
      this.logger.error('Failed to publish message:', error);
    }
  }

  async subscribe(queue: string, exchangeName: string, onMessage: (msg: any) => void) {
    try {
      await this.channel.assertQueue(queue, { durable: true });
      await this.channel.bindQueue(queue, this.EXCHANGE, exchangeName);

      this.channel.consume(queue, (msg) => {
        if (msg) {
          const content = JSON.parse(msg.content.toString());
          this.logger.log(`Message received from exchange ${exchangeName}:`, content);
          onMessage(content);
          this.channel.ack(msg);
        }
      });
      this.logger.log(`Subscribed to queue ${queue} from exchange ${exchangeName}`);
    } catch (error) {
      this.logger.error('Failed to subscribe to queue:', error);
    }
  }
}
