import axios, { AxiosInstance } from 'axios';
import { 
  APIResponse, 
  PaginatedResponse,
  StockInfo, 
  StockDaily, 
  StockIntraday,
  CapitalFlow,
  IndexInfo,
  IndexDaily,
  IndexIntraday,
  ConceptInfo,
  ConceptDaily,
  ConceptRank,
  MarketSnapshot,
  LimitUpStock,
  ContinuousBoard,
  LimitUpDistribution,
  AccountInfo,
  Position,
  TradeRecord,
  MarketSnapshotByTime,
  TimeSnapshot
} from '../types';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 响应拦截器
api.interceptors.response.use(
  response => response.data,
  error => {
    console.error('API Error:', error);
    return Promise.reject(error);
  }
);

// ==================== 股票 API ====================
export const stockAPI = {
  getInfo: (code: string): Promise<APIResponse<StockInfo>> => 
    api.get(`/stock/info/${code}`),
  
  getDaily: (code: string, days: number = 60): Promise<APIResponse<{ items: StockDaily[] }>> => 
    api.get(`/stock/daily/${code}`, { params: { days } }),
  
  getIntraday: (code: string, date?: string): Promise<APIResponse<StockIntraday[]>> => 
    api.get(`/stock/intraday/${code}`, { params: { date } }),
  
  getRealtime: (codes: string[]): Promise<APIResponse<{ items: any[] }>> => 
    api.post('/stock/realtime', codes),
  
  getCapitalFlow: (code: string, date?: string): Promise<APIResponse<CapitalFlow>> => 
    api.get(`/stock/capital-flow/${code}`, { params: { date } }),
  
  getConcepts: (code: string): Promise<APIResponse<{ concepts: ConceptInfo[] }>> => 
    api.get(`/stock/concepts/${code}`),
  
  search: (keyword: string): Promise<APIResponse<{ items: StockInfo[] }>> => 
    api.get('/stock/search', { params: { keyword } }),
};

// ==================== 指数 API ====================
export const indexAPI = {
  getList: (): Promise<APIResponse<{ items: IndexInfo[] }>> => 
    api.get('/index/list'),
  
  getDaily: (code: string, days: number = 60): Promise<APIResponse<{ items: IndexDaily[] }>> => 
    api.get(`/index/daily/${code}`, { params: { days } }),
  
  getIntraday: (code: string, date?: string): Promise<APIResponse<IndexIntraday[]>> => 
    api.get(`/index/intraday/${code}`, { params: { date } }),
};

// ==================== 概念板块 API ====================
export const conceptAPI = {
  getList: (page?: number, pageSize?: number): Promise<APIResponse<PaginatedResponse<ConceptInfo>>> => 
    api.get('/concept/list', { params: { page, page_size: pageSize } }),
  
  getDaily: (code: string, startDate?: string, endDate?: string): Promise<APIResponse<{ items: ConceptDaily[] }>> => 
    api.get(`/concept/daily/${code}`, {
      params: { start_date: startDate, end_date: endDate }
    }),
  
  getIntraday: (code: string, date?: string): Promise<APIResponse<any>> => 
    api.get(`/concept/intraday/${code}`, { params: { date } }),
  
  getComponents: (code: string): Promise<APIResponse<{ items: any[] }>> => 
    api.get(`/concept/components/${code}`),
  
  getRank: (
    date?: string, 
    sortBy?: string, 
    order?: string, 
    page?: number, 
    pageSize?: number
  ): Promise<APIResponse<PaginatedResponse<ConceptRank>>> => 
    api.get('/concept/rank', {
      params: { date, sort_by: sortBy, order, page, page_size: pageSize }
    }),
  
  search: (keyword: string): Promise<APIResponse<{ items: ConceptInfo[] }>> => 
    api.get('/concept/search', { params: { keyword } }),
};

// ==================== 市场数据 API ====================
export const marketAPI = {
  getLatestTradeDate: (): Promise<APIResponse<{ date: string }>> => 
    api.get('/market/latest-trade-date'),
  
  getSnapshot: (date?: string): Promise<APIResponse<MarketSnapshot>> => 
    api.get('/market/snapshot', { params: { date } }),
  
  getStatistics: (date?: string): Promise<APIResponse<MarketSnapshot>> => 
    api.get('/market/statistics', { params: { date } }),
  
  getStockRanking: (params: {
    date?: string;
    sort?: string;
    order?: string;
    page?: number;
    page_size?: number;
  }): Promise<APIResponse<PaginatedResponse<any>>> => 
    api.get('/market/stock-ranking', { params }),
  
  getLimitUp: (
    date?: string, 
    page?: number, 
    pageSize?: number
  ): Promise<APIResponse<PaginatedResponse<LimitUpStock>>> => 
    api.get('/market/limit-up', {
      params: { date, page, page_size: pageSize }
    }),
  
  getLimitDown: (
    date?: string, 
    page?: number, 
    pageSize?: number
  ): Promise<APIResponse<PaginatedResponse<LimitUpStock>>> => 
    api.get('/market/limit-down', {
      params: { date, page, page_size: pageSize }
    }),
  
  getContinuousBoard: (date?: string): Promise<APIResponse<ContinuousBoard>> => 
    api.get('/market/continuous-board', { params: { date } }),
  
  getBrokenBoard: (
    date?: string, 
    page?: number, 
    pageSize?: number
  ): Promise<APIResponse<PaginatedResponse<LimitUpStock>>> => 
    api.get('/market/broken-board', {
      params: { date, page, page_size: pageSize }
    }),
  
  getRank: (
    date?: string, 
    rankType?: string, 
    direction?: string, 
    page?: number, 
    pageSize?: number
  ): Promise<APIResponse<any>> => 
    api.get('/market/rank', {
      params: { date, rank_type: rankType, direction, page, page_size: pageSize }
    }),
  
  getSealRateHistory: (
    startDate?: string, 
    endDate?: string
  ): Promise<APIResponse<{ items: any[] }>> => 
    api.get('/market/history/seal-rate', {
      params: { start_date: startDate, end_date: endDate }
    }),
  
  getLimitTimesHistory: (
    stockCode: string, 
    limitType?: string, 
    limit?: number
  ): Promise<APIResponse<{ items: any[] }>> => 
    api.get('/market/history/limit-times', {
      params: { stock_code: stockCode, limit_type: limitType, limit }
    }),

  getLimitUpDistribution: (date?: string): Promise<APIResponse<{ items: LimitUpDistribution[] }>> =>
    api.get('/market/limit-up-distribution', { params: { date } }),
};

// ==================== 数据采集 API ====================
export const collectorAPI = {
  triggerDaily: (date?: string): Promise<APIResponse<any>> => 
    api.post('/collector/trigger/daily', null, { params: { date } }),
  
  triggerIntraday: (date?: string): Promise<APIResponse<any>> => 
    api.post('/collector/trigger/intraday', null, { params: { date } }),
  
  triggerConcept: (): Promise<APIResponse<any>> => 
    api.post('/collector/trigger/concept'),
  
  triggerLimitList: (date?: string): Promise<APIResponse<any>> => 
    api.post('/collector/trigger/limit-list', null, { params: { date } }),
  
  triggerConceptMapping: (): Promise<APIResponse<any>> => 
    api.post('/collector/trigger/concept-mapping'),
  
  triggerAll: (date?: string): Promise<APIResponse<any>> => 
    api.post('/collector/trigger/all', null, { params: { date } }),
};

// ==================== 模拟看盘 API ====================
export const simulationAPI = {
  getMarketOverview: (date?: string): Promise<APIResponse<any>> => 
    api.get('/simulation/market-overview', { params: { date } }),
  
  getLadderDetail: (date?: string): Promise<APIResponse<ContinuousBoard>> => 
    api.get('/simulation/ladder-detail', { params: { date } }),
  
  getHotStocks: (date?: string, limit?: number): Promise<APIResponse<{ items: any[] }>> => 
    api.get('/simulation/hot-stocks', { params: { date, limit } }),
  
  getCapitalFlowRank: (
    date?: string, 
    direction?: string, 
    limit?: number
  ): Promise<APIResponse<{ items: any[] }>> => 
    api.get('/simulation/capital-flow-rank', {
      params: { date, direction, limit }
    }),
  
  getBoardWatch: (date?: string): Promise<APIResponse<any>> => 
    api.get('/simulation/board-watch', { params: { date } }),

  // 新增：时间点快照 API
  getMarketSnapshotByTime: (params: {
    time: string;
    date?: string;
    top_n?: number;
  }): Promise<APIResponse<MarketSnapshotByTime>> =>
    api.post('/simulation/market-snapshot', params),

  getWatchlistSnapshot: (params: {
    time: string;
    date?: string;
    codes: string[];
  }): Promise<APIResponse<TimeSnapshot>> =>
    api.post('/simulation/watchlist-snapshot', params),

  getTimeline: (params: {
    date?: string;
    times: string[];
    codes: string[];
  }): Promise<APIResponse<{ date: string; snapshots: TimeSnapshot[] }>> =>
    api.post('/simulation/timeline', params),
};

// ==================== 账户管理 API ====================
export const accountAPI = {
  getInfo: (): Promise<APIResponse<AccountInfo>> => 
    api.get('/account/info'),
  
  updateInfo: (
    accountName?: string, 
    initialCapital?: number
  ): Promise<APIResponse<any>> => 
    api.put('/account/info', null, {
      params: { account_name: accountName, initial_capital: initialCapital }
    }),
  
  getPositions: (): Promise<APIResponse<{ items: Position[] }>> => 
    api.get('/account/positions'),
  
  updatePositionPrices: (): Promise<APIResponse<any>> => 
    api.post('/account/positions/update-price'),
  
  getTrades: (
    startDate?: string, 
    endDate?: string, 
    page?: number, 
    pageSize?: number
  ): Promise<APIResponse<PaginatedResponse<TradeRecord>>> => 
    api.get('/account/trades', {
      params: { start_date: startDate, end_date: endDate, page, page_size: pageSize }
    }),
  
  executeTrade: (
    stockCode: string, 
    action: string, 
    price: number, 
    quantity: number, 
    reason?: string
  ): Promise<APIResponse<any>> => 
    api.post('/account/trade', null, {
      params: { stock_code: stockCode, action, price, quantity, reason }
    }),
  
  getSnapshots: (
    startDate?: string, 
    endDate?: string, 
    limit?: number
  ): Promise<APIResponse<{ items: any[] }>> => 
    api.get('/account/snapshots', {
      params: { start_date: startDate, end_date: endDate, limit }
    }),
  
  createSnapshot: (): Promise<APIResponse<any>> => 
    api.post('/account/snapshot/create'),
};

export default api;
