/* eslint-disable @typescript-eslint/no-unused-vars */
/* eslint-disable @typescript-eslint/no-empty-function */
import { Injectable } from '@nestjs/common';
import { Observable, Subject } from 'rxjs';
import { DefaultLogger, WebsocketClientV2, WsSnapshotChannelEvent, WsTopicSubscribePublicArgsV2 } from 'bitget-api';
import { getRoundedAssetPrice } from './bitget.utils';
import { ITrade, IWsTrade } from './bitget.types';

const logger = {
  ...DefaultLogger,
  silly: (..._params) => {},
  debug: (..._params) => {},
  notice: (..._params) => {},
  info: (..._params) => {}
};

@Injectable()
export class BitgetWebSocketService {
  private ws: WebsocketClientV2;
  private tradeUpdates$: Subject<ITrade[]> = new Subject();
  private reconnect$: Subject<boolean> = new Subject();
  private connected$: Subject<boolean> = new Subject();

  get reconnected(): Observable<boolean> {
    return this.reconnect$.asObservable();
  }

  get connected(): Observable<boolean> {
    return this.connected$.asObservable();
  }

  get tradeUpdates(): Observable<IWsTrade[]> {
    return this.tradeUpdates$.asObservable();
  }

  initWebSocket(symbolInfo: any): void {
    this.ws = new WebsocketClientV2({ pongTimeout: 1000 * 30 }, logger);

    this.ws.on('update', (message: WsSnapshotChannelEvent) => {
      if ((message as WsSnapshotChannelEvent).arg.channel === 'trade') {
        const { instId: symbol } = message.arg;
        const data = message.data as IWsTrade[];
        const tradeUpdates = data.map((data) => {
          const roundedPrice = getRoundedAssetPrice(symbol, Number(data.price), symbolInfo);
          return {
            ...data,
            symbol,
            roundedPrice
          };
        });
        this.tradeUpdates$.next(tradeUpdates as ITrade[]);
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

    this.ws.on('exception', (data) => {
      console.log('ws saw error ', data?.wsKey);
    });
  }

  public async subscribeToTopics(args: WsTopicSubscribePublicArgsV2[]): Promise<void> {
    await this.ws.subscribe(args);
  }
}
