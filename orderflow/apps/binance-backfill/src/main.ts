import { NestFactory } from '@nestjs/core';
import { BinanceBackfillModule } from './backfill.module';
import { Logger } from '@nestjs/common';
import { validateEnvironment } from '@orderflow/utils/validation';

async function bootstrap() {
  if (!validateEnvironment()) {
    Logger.error('Environment validation failed. Exiting application.', 'Startup');
    process.exit(1);
  }

  setupExceptionCatchers();

  const app = await NestFactory.create(BinanceBackfillModule);
  await app.listen(3000);
}

function setupExceptionCatchers() {
  process.on('uncaughtException', (e) => {
    console.error(new Date(), 'unhandled exception: ', e?.stack, e);
  });

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  process.on('unhandledRejection', (e: any, p) => {
    console.error(new Date(), 'unhandled rejection: ', e?.stack, e, p);
  });
}

bootstrap();
