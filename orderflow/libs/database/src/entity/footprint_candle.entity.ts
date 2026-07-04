/* eslint-disable @typescript-eslint/no-unused-vars */
/* eslint-disable indent */
import { Entity, PrimaryGeneratedColumn, Column, Index } from 'typeorm';
import { IPriceLevel } from '../../../orderflow/src/dto/orderflow.dto';

export const CandleUniqueColumns = ['exchange', 'symbol', 'interval', 'openTime'];

@Entity({ name: 'footprint_candle' })
@Index(CandleUniqueColumns, { unique: true })
export class FootPrintCandle {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ type: 'timestamptz' })
  openTime: Date;

  @Column({ type: 'timestamptz' })
  closeTime: Date;

  @Column({ type: 'bigint' })
  openTimeMs: number;

  @Column({ type: 'bigint' })
  closeTimeMs: number;

  @Column()
  exchange: string;

  @Column()
  interval: string;

  @Column()
  symbol: string;

  @Column('double precision')
  volumeDelta: number;

  @Column('double precision')
  volume: number;

  @Column('double precision', { default: 0 })
  aggressiveBid: number;

  @Column('double precision', { default: 0 })
  aggressiveAsk: number;

  @Column('double precision')
  high: number;

  @Column('double precision')
  low: number;

  @Column('double precision')
  close: number;

  // Storing bid and ask as JSON
  @Column('jsonb', { default: {} })
  // @OneToMany(() => FootPrintCandleLevel, (level) => level.closeTime)
  // @JoinColumn()
  priceLevels: Record<string, IPriceLevel>;
}
