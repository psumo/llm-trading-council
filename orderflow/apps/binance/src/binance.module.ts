import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { ScheduleModule } from '@nestjs/schedule';
import { TypeOrmModule } from '@nestjs/typeorm';
import { DatabaseModule, DatabaseConfiguration } from '@database';
import { RabbitMQModule } from '@rabbitmq';
import { BinanceService } from './binance.service';
import { BinanceWebSocketService } from './binance.websocket.service';

@Module({
  imports: [ConfigModule.forRoot({ isGlobal: true }), ScheduleModule.forRoot(), TypeOrmModule.forRoot(DatabaseConfiguration), DatabaseModule, RabbitMQModule],
  providers: [BinanceService, BinanceWebSocketService]
})
export class BinanceModule {}
