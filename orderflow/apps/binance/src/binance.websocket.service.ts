import { Injectable, Logger } from '@nestjs/common';
import { Observable, Subject } from 'rxjs';
import { FuturesExchangeInfo, WsMessageAggTradeRaw } from 'binance';
import { getRoundedAssetPrice } from './binance.utils';

// The binance lib's WebsocketClient (2.13.x) connects but never surfaces
// frames under this webpack bundle (its isomorphic-ws resolves to the browser
// stub). This service talks to the futures stream directly using Node 21+'s
// native WebSocket global, keeping the original Observable interface.
const FUTURES_WS_BASE = 'wss://fstream.binance.com/ws';
const RECONNECT_DELAY_MS = 5_000;
const STALE_CHECK_INTERVAL_MS = 60_000;
const STALE_AFTER_MS = 5 * 60_000; // futures stream pings every ~3 min; reconnect beyond this

interface ManagedConnection {
  symbol: string;
  socket: WebSocket | null;
  lastActivity: number;
  everConnected: boolean;
}

@Injectable()
export class BinanceWebSocketService {
  private logger: Logger = new Logger(BinanceWebSocketService.name);
  private exchangeInfo: FuturesExchangeInfo | null = null;
  private connections: Map<string, ManagedConnection> = new Map();
  private tradeUpdates$: Subject<WsMessageAggTradeRaw> = new Subject();
  private reconnect$: Subject<string> = new Subject();
  private connected$: Subject<string> = new Subject();
  private staleTimer: NodeJS.Timeout | null = null;

  get reconnected(): Observable<string> {
    return this.reconnect$.asObservable();
  }

  get connected(): Observable<string> {
    return this.connected$.asObservable();
  }

  get tradeUpdates(): Observable<WsMessageAggTradeRaw> {
    return this.tradeUpdates$.asObservable();
  }

  initWebSocket(exchangeInfo: FuturesExchangeInfo): void {
    this.exchangeInfo = exchangeInfo;
    if (!this.staleTimer) {
      this.staleTimer = setInterval(() => this.reconnectStaleConnections(), STALE_CHECK_INTERVAL_MS);
      this.staleTimer.unref();
    }
  }

  public subscribeToTrades(symbol: string, _market: 'spot' | 'usdm' | 'coinm'): { wsKey: string } {
    const wsKey = `usdm_aggTrade_${symbol.toLowerCase()}_`;
    if (!this.connections.has(wsKey)) {
      this.connections.set(wsKey, { symbol, socket: null, lastActivity: 0, everConnected: false });
      this.openConnection(wsKey);
    }
    return { wsKey };
  }

  private openConnection(wsKey: string): void {
    const conn = this.connections.get(wsKey);
    if (!conn) {
      return;
    }

    const url = `${FUTURES_WS_BASE}/${conn.symbol.toLowerCase()}@aggTrade`;
    const socket = new WebSocket(url); // Node 21+ native WebSocket (undici); protocol-level ping/pong is automatic
    conn.socket = socket;

    socket.addEventListener('open', () => {
      conn.lastActivity = Date.now();
      this.logger.log(`connection opened: ${wsKey} ${url}`);
      if (conn.everConnected) {
        this.reconnect$.next(wsKey);
      } else {
        conn.everConnected = true;
        this.connected$.next(wsKey);
      }
    });

    socket.addEventListener('message', (event: MessageEvent) => {
      conn.lastActivity = Date.now();
      if (typeof event.data !== 'string') {
        return; // aggTrade frames are text
      }
      let message: WsMessageAggTradeRaw;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      if (!message || message.e !== 'aggTrade' || !message.s) {
        return;
      }
      const price = this.exchangeInfo ? getRoundedAssetPrice(message.s, Number(message.p), this.exchangeInfo) : Number(message.p);
      this.tradeUpdates$.next({ ...message, p: price });
    });

    socket.addEventListener('error', () => {
      this.logger.warn(`ws error on ${wsKey}`);
    });

    socket.addEventListener('close', (event: CloseEvent) => {
      if (conn.socket !== socket) {
        return; // superseded by a newer connection (stale reconnect)
      }
      this.logger.warn(`ws closed (${event.code}) on ${wsKey}; reconnecting in ${RECONNECT_DELAY_MS}ms`);
      setTimeout(() => this.openConnection(wsKey), RECONNECT_DELAY_MS).unref();
    });
  }

  private reconnectStaleConnections(): void {
    const now = Date.now();
    for (const [wsKey, conn] of this.connections) {
      const isOpen = conn.socket?.readyState === WebSocket.OPEN;
      if (isOpen && conn.lastActivity > 0 && now - conn.lastActivity > STALE_AFTER_MS) {
        this.logger.warn(`no activity on ${wsKey} for ${Math.round((now - conn.lastActivity) / 1000)}s; forcing reconnect`);
        const old = conn.socket;
        conn.socket = null; // detach so the close handler doesn't double-reconnect
        old?.close();
        this.openConnection(wsKey);
      }
    }
  }
}
