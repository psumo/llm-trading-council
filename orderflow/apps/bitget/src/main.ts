import { Logger } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import { BitgetModule } from './bitget.module';

async function bootstrap() {
  Logger.log(new Date(), `Starting apps/bitget...`, 'Startup');

  const app = await NestFactory.create(BitgetModule);

  setupExceptionCatchers();
  await app.listen(3000);
}

function setupExceptionCatchers() {
  process.on('uncaughtException', (e) => {
    Logger.error(new Date(), 'unhandled exception: ', e?.stack, e);
  });

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  process.on('unhandledRejection', (e: any, p) => {
    Logger.error(new Date(), 'unhandled rejection: ', e?.stack, e, p);
  });
}

bootstrap();
