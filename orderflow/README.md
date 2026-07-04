# Orderflow

An Orderflow service that processes real-time trade data from WebSockets to build Footprint Candles for individual crypto exchanges. Currently supports Binance, Bybit, OKX, Bitget and Gate.io.

## Get Started

1. Clone the repository:
   ```
   git clone git@github.com:focus1691/orderflow.git
   ```

2. Set up a PostgreSQL TimescaleDB instance (Required):
   ```
   docker run -d --name timescaledb -p 5433:5432 -e POSTGRES_PASSWORD=password timescale/timescaledb-ha:pg14-latest
   ```

3. Set up a RabbitMQ instance (optional) to listen for candle closes:
   ```
   docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 -e RABBITMQ_DEFAULT_USER=admin -e RABBITMQ_DEFAULT_PASS=admin rabbitmq:4.0-management
   ```

4. Configure environment variables:
   - `DB_URL`
   - `USE_RABBITMQ`
   - `RABBITMQ_URL`
   - `BINANCE_DOCKER_PORT`
   - `BITGET_DOCKER_PORT`
   - `BYBIT_DOCKER_PORT`
   - `GATEIO_DOCKER_PORT`
   - `OKX_DOCKER_PORT`
   - `SYMBOLS`

5. Build and Run the services:
   ```
   yarn binance:docker
   ```
   ```
   yarn bitget:docker
   ```
   ```
   yarn gateio:docker
   ```
   ```
   yarn bybit:docker
   ```
   ```
   yarn okx:docker
   ```

## Binance Backfill

For historical data processing:

1. Set the following environment variables:
   - `SYMBOLS`: Trading pair(s) to backfill for. Comma-separated values.
   - `BACKFILL_START_AT`: Start timestamp (ms)
   - `BACKFILL_END_AT`: End timestamp (ms)

2. Run the Binance Backfill service:
   ```
   yarn start:binance-backfill
   ```


# Indicators

The [`chart-patterns`](https://github.com/focus1691/chart-patterns) library has indicators to use the FootPrint candles generated from this service. Below are examples of using the `stackedImbalances` and `highVolumeNodes` indicators.

### Stacked Imbalances

A stacked imbalance occurs when there is a cluster of price levels where the volume difference between the bid and ask exceeds a defined threshold. This indicator helps identify aggressive buying or selling.

```javascript
import { Orderflow } from 'chart-patterns';

const footprintCandlePrices = {
  '98891': { volSumAsk: 0.002, volSumBid: 0.611 },
  '98892': { volSumAsk: 0.002, volSumBid: 1.49 },
  '98893': { volSumAsk: 0.005, volSumBid: 1.386 },
  '98894': { volSumAsk: 0.022, volSumBid: 2.58 },
  '98895': { volSumAsk: 0.018, volSumBid: 2.18 },
};

const stackedImbalance = Orderflow.detectStackedImbalances(footprintCandlePrices, {
  threshold: 200, // Minimum volume imbalance percentage
  stackCount: 3, // Number of consecutive imbalances
  tickSize: 0.1, // Tick Size (e.g., 0.1 for BTCUSDT)
});

console.log(stackedImbalance);
/*
[
  {
    imbalanceStartAt: 98891,
    imbalanceEndAt: 98895,
    stackedCount: 5,
    imbalanceSide: "buy"
  }
]
*/
```
### High Volume Nodes

A high volume node identifies price levels where significant trading volume occurs, potentially marking areas of interest or support/resistance levels.

```javascript
const highVolumeNodes = Orderflow.findHighVolumeNodes(footprintCandlePrices, { 
  threshold: 0.3, // Node Volume Percentage 30%
});

console.log(highVolumeNodes);
/*
[
  {
    nodePrice: 98894,
    totalVolume: 8.305,
    sellVolume: 0.022,
    buyVolume: 2.58,
    nodeVolumePercent: 0.31
  }
]
*/
```
