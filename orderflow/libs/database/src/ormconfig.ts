require('dotenv').config();

import { DataSource, DataSourceOptions } from 'typeorm';
import { FootPrintCandle } from '@database/entity/footprint_candle.entity';

export const DatabaseConfiguration: DataSourceOptions = {
  type: 'postgres',
  url: process.env.DB_URL,
  entities: [FootPrintCandle],
  synchronize: true
};

export const AppDataSource = new DataSource(DatabaseConfiguration);
