import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { ScheduleModule } from '@nestjs/schedule';
import { TypeOrmModule } from '@nestjs/typeorm';
import { DatabaseModule, DatabaseConfiguration } from '@database';
import { RabbitMQModule } from '@rabbitmq';
import { OkxService } from './okx.service';
import { OkxWebSocketService } from './okx.websocket.service';

@Module({
  imports: [ConfigModule.forRoot({ isGlobal: true }), ScheduleModule.forRoot(), TypeOrmModule.forRoot(DatabaseConfiguration), DatabaseModule, RabbitMQModule],
  providers: [OkxService, OkxWebSocketService]
})
export class OkxModule {}
