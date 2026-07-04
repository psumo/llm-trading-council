import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { DatabaseService } from '@database/database.service';
import { FootPrintCandle } from '@database/entity/footprint_candle.entity';

@Module({
  imports: [TypeOrmModule.forFeature([FootPrintCandle])],
  providers: [DatabaseService],
  exports: [DatabaseService]
})
export class DatabaseModule {}
