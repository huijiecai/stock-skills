/**
 * 全局类型定义
 */

// ==================== 基础类型 ====================

export interface APIResponse<T = any> {
  code: number;
  message: string;
  data: T;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ==================== 股票相关 ====================

export interface StockInfo {
  stock_code: string;
  stock_name: string;
  industry?: string;
  list_date?: string;
  market?: string;
}

export interface StockDaily {
  trade_date: string;
  open: number;
  close: number;
  high: number;
  low: number;
  change_pct: number;
  volume: number;
  amount: number;
  turnover_rate?: number;
}

export interface StockIntraday {
  time: string;
  price: number;
  change_pct: number;
  volume: number;
  amount: number;
  avg?: number;
}

export interface CapitalFlow {
  stock_code: string;
  stock_name: string;
  date: string;
  main_net_inflow: number;
  main_net_inflow_pct: number;
  retail_net_inflow: number;
  retail_net_inflow_pct: number;
  super_net_inflow: number;
  big_net_inflow: number;
  mid_net_inflow: number;
  small_net_inflow: number;
}

// ==================== 指数相关 ====================

export interface IndexInfo {
  index_code: string;
  index_name: string;
  close: number;
  change_pct: number;
  amount?: number;
  pre_close?: number;
}

export interface IndexDaily {
  trade_date: string;
  open: number;
  close: number;
  high: number;
  low: number;
  change_pct: number;
  volume: number;
  amount: number;
}

export interface IndexIntraday {
  time: string;
  price: number;
  change_pct: number;
  volume: number;
  amount: number;
}

// ==================== 概念板块 ====================

export interface ConceptInfo {
  concept_code: string;
  concept_name: string;
  component_count?: number;
}

export interface ConceptDaily {
  trade_date: string;
  open: number;
  close: number;
  high: number;
  low: number;
  change_pct: number;
  volume: number;
  amount: number;
}

export interface ConceptRank extends ConceptInfo {
  change_pct: number;
  limit_up_count?: number;
  leading_stock?: string;
}

// ==================== 市场数据 ====================

export interface MarketSnapshot {
  date: string;
  limit_up_count: number;
  limit_down_count: number;
  broken_board_count: number;
  seal_rate: number;
  max_continuous_board?: number;
  indices?: IndexInfo[];
}

export interface LimitUpStock {
  stock_code: string;
  stock_name: string;
  close_price: number;
  change_pct: number;
  first_time: string;
  last_time: string;
  open_times: number;
  limit_times: number;
  limit_amount?: number;
  is_broken: boolean;
  broken_time?: string;
  reseal_time?: string;
}

export interface ContinuousBoardLevel {
  level: string;
  limit_times: number;
  count: number;
  stocks: Array<{
    stock_code: string;
    stock_name: string;
    first_time: string;
    last_time: string;
    is_broken: boolean;
    close: number;
    change_pct: number;
  }>;
}

export interface ContinuousBoard {
  date: string;
  ladder: ContinuousBoardLevel[];
}

export interface LimitUpDistribution {
  concept_code: string;
  concept_name: string;
  limit_up_count: number;
  stocks: string[];
}

// ==================== 账户相关 ====================

export interface AccountInfo {
  id: number;
  account_name: string;
  initial_capital: number;
  available_cash: number;
  market_value: number;
  total_asset: number;
  total_profit: number;
  total_profit_pct: number;
}

export interface Position {
  stock_code: string;
  stock_name: string;
  quantity: number;
  available: number;
  cost_price: number;
  current_price: number;
  market_value: number;
  profit: number;
  profit_pct: number;
}

export interface TradeRecord {
  trade_id: string;
  trade_time: string;
  stock_code: string;
  stock_name: string;
  action: 'buy' | 'sell';
  price: number;
  quantity: number;
  amount: number;
  reason?: string;
}

// ==================== 模拟看盘 ====================

export interface TimeSnapshot {
  time: string;
  date: string;
  items: Array<{
    code: string;
    name: string;
    price: number;
    change_pct: number;
    volume: number;
    amount: number;
  }>;
}

export interface MarketSnapshotByTime {
  time: string;
  date: string;
  index: Record<string, {
    name: string;
    price: number;
    change_pct: number;
  }>;
  market_sentiment: {
    limit_up_count: number;
    limit_down_count: number;
    broken_board_count: number;
    seal_rate: number;
  };
  top_gainers: Array<{
    code: string;
    name: string;
    price: number;
    change_pct: number;
  }>;
  top_concepts: Array<{
    code: string;
    name: string;
    change_pct: number;
  }>;
  limit_up_list: Array<{
    code: string;
    name: string;
    seal_time: string;
    limit_times: number;
  }>;
}
