import { Injectable } from '@nestjs/common';
import { Observable, Subject } from 'rxjs';
import { TradeData, TradeResponse } from './websocket.responses';
import { APIResponseV3WithTime, CategoryV5, InstrumentInfoResponseV5, WebsocketClient } from 'bybit-api';
import { getRoundedAssetPrice } from './bybit.utils';

@Injectable()
export class BybitWebSocketService {
  private ws: WebsocketClient;
  private tradeUpdates$: Subject<TradeData[]> = new Subject();
  private reconnect$: Subject<boolean> = new Subject();
  private connected$: Subject<boolean> = new Subject();

  get reconnected(): Observable<boolean> {
    return this.reconnect$.asObservable();
  }

  get connected(): Observable<boolean> {
    return this.connected$.asObservable();
  }

  get tradeUpdates(): Observable<TradeData[]> {
    return this.tradeUpdates$.asObservable();
  }

  initWebSocket(instrumentInfo: APIResponseV3WithTime<InstrumentInfoResponseV5<'linear'>>): void {
    this.ws = new WebsocketClient({ market: 'v5' });

    this.ws.on('update', (response: TradeResponse) => {
      if (response.topic.startsWith('publicTrade')) {
        const tradeUpdates = response.data.map((data) => {
          const roundedPrice = getRoundedAssetPrice(data.s, Number(data.p), instrumentInfo);

          return {
            ...data,
            p: roundedPrice
          };
        });
        this.tradeUpdates$.next(tradeUpdates as TradeData[]);
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

  public async subscribeToTopics(topics: string[], category: string): Promise<void> {
    await this.ws.subscribeV5(topics, category as CategoryV5);
  }
}
