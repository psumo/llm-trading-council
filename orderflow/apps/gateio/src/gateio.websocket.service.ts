/* eslint-disable @typescript-eslint/no-unused-vars */
/* eslint-disable @typescript-eslint/no-empty-function */
import { Injectable } from '@nestjs/common';
import { Observable, Subject } from 'rxjs';
import { DefaultLogger, FuturesContract, FuturesTrade, WebsocketClient, WsKey, WsTopicRequest } from 'gateio-api';
import { getRoundedAssetPrice } from './gateio.utils';

const logger = {
  ...DefaultLogger,
  silly: (..._params) => {},
  debug: (..._params) => {},
  notice: (..._params) => {},
  info: (..._params) => {}
};

@Injectable()
export class GateioWebSocketService {
  private ws: WebsocketClient;
  private tradeUpdates$: Subject<FuturesTrade[]> = new Subject();
  private reconnect$: Subject<boolean> = new Subject();
  private connected$: Subject<boolean> = new Subject();

  get reconnected(): Observable<boolean> {
    return this.reconnect$.asObservable();
  }

  get connected(): Observable<boolean> {
    return this.connected$.asObservable();
  }

  get tradeUpdates(): Observable<FuturesTrade[]> {
    return this.tradeUpdates$.asObservable();
  }

  initWebSocket(futuresContracts: FuturesContract[]): void {
    this.ws = new WebsocketClient({ pongTimeout: 1000 * 30 }, logger);

    this.ws.on('update', (response: { channel: string, result: FuturesTrade[] }) => {
      const { channel, result } = response;

      if (channel === 'futures.trades') {
        const tradeUpdates = result.map((data) => {
          const roundedPrice: number = getRoundedAssetPrice(data.contract, Number(data.price), futuresContracts);
          return {
            ...data,
            roundedPrice
          };
        });
        this.tradeUpdates$.next(tradeUpdates as FuturesTrade[]);
      }
    });

    this.ws.on('open', (wsKey) => {
      console.log('connection opened', wsKey);
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

  public async subscribeToTopics(futuresContracts: FuturesContract[], contractType: WsKey): Promise<void> {
    const wsRequest: WsTopicRequest = {
      topic: 'futures.trades',
      payload: futuresContracts.map((contract) => contract.name)
    };

    await this.ws.subscribe(wsRequest, contractType);
  }
}
