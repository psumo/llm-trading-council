/* eslint-disable @typescript-eslint/no-unused-vars */
/* eslint-disable @typescript-eslint/no-empty-function */
import { Injectable } from '@nestjs/common';
import { Observable, Subject } from 'rxjs';
import { DefaultLogger, Instrument, Trade, WebsocketClient, WsChannelSubUnSubRequestArg, WsDataEvent } from 'okx-api';
import { getRoundedAssetPrice } from './okx.utils';

const logger = {
  ...DefaultLogger,
  silly: (..._params) => {},
  debug: (..._params) => {},
  notice: (..._params) => {},
  info: (..._params) => {}
};

@Injectable()
export class OkxWebSocketService {
  private ws: WebsocketClient;
  private tradeUpdates$: Subject<Trade[]> = new Subject();
  private reconnect$: Subject<boolean> = new Subject();
  private connected$: Subject<boolean> = new Subject();

  get reconnected(): Observable<boolean> {
    return this.reconnect$.asObservable();
  }

  get connected(): Observable<boolean> {
    return this.connected$.asObservable();
  }

  get tradeUpdates(): Observable<Trade[]> {
    return this.tradeUpdates$.asObservable();
  }

  initWebSocket(instrumentInfo: Instrument[]): void {
    this.ws = new WebsocketClient({ pongTimeout: 1000 * 30 }, logger);

    this.ws.on('update', (message: WsDataEvent<Trade[]>) => {
      if (message.arg.channel === 'trades') {
        const tradeUpdates = message.data.map((data) => {
          const roundedPrice = getRoundedAssetPrice(data.instId, Number(data.px), instrumentInfo);
          return {
            ...data,
            p: roundedPrice
          };
        });
        this.tradeUpdates$.next(tradeUpdates as Trade[]);
      }
    });

    this.ws.on('open', () => {
      console.log('connection opened');
      this.connected$.next(true);
    });

    this.ws.on('reconnect', () => {
      console.log('ws automatically reconnecting.... ');
    });

    this.ws.on('reconnected', () => {
      this.reconnect$.next(true);
    });

    this.ws.on('error', (data) => {
      console.log('ws saw error ', data?.wsKey);
    });
  }

  public async subscribeToTopics(symbols: string[], category: string): Promise<void> {
    const wsTopics: WsChannelSubUnSubRequestArg[] = symbols.map((symbol) => {
      return {
        channel: 'trades',
        instId: symbol
      };
    });
    await this.ws.subscribe(wsTopics);
  }
}
