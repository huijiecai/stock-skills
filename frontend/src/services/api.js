import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

const api = axios.create({
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
  // 获取股票信息
  getInfo: (code) => api.get(`/stock/info/${code}`),
  // 获取股票日线
  getDaily: (code, days = 60) => api.get(`/stock/daily/${code}`, {
    params: { days }
  }),
  // 获取股票分时
  getIntraday: (code, date) => api.get(`/stock/intraday/${code}`, { params: { date } }),
  // 批量获取实时行情
  getRealtime: (codes) => api.post('/stock/realtime', codes),
  // 获取资金流向
  getCapitalFlow: (code, date) => api.get(`/stock/capital-flow/${code}`, { params: { date } }),
  // 获取股票所属概念
  getConcepts: (code) => api.get(`/stock/concepts/${code}`),
  // 搜索股票
  search: (keyword) => api.get('/stock/search', { params: { keyword } }),
};

// ==================== 指数 API ====================
export const indexAPI = {
  // 获取指数列表
  getList: () => api.get('/index/list'),
  // 获取指数日线
  getDaily: (code, days = 60) => api.get(`/index/daily/${code}`, {
    params: { days }
  }),
  // 获取指数分时
  getIntraday: (code, date) => api.get(`/index/intraday/${code}`, { params: { date } }),
};

// ==================== 概念板块 API ====================
export const conceptAPI = {
  // 获取概念列表
  getList: (page, pageSize) => api.get('/concept/list', { params: { page, page_size: pageSize } }),
  // 获取概念日线
  getDaily: (code, startDate, endDate) => api.get(`/concept/daily/${code}`, {
    params: { start_date: startDate, end_date: endDate }
  }),
  // 获取概念分时
  getIntraday: (code, date) => api.get(`/concept/intraday/${code}`, { params: { date } }),
  // 获取概念成分股
  getComponents: (code) => api.get(`/concept/components/${code}`),
  // 获取概念涨幅榜
  getRank: (date, sortBy, order, page, pageSize) => api.get('/concept/rank', {
    params: { date, sort_by: sortBy, order, page, page_size: pageSize }
  }),
  // 搜索概念
  search: (keyword) => api.get('/concept/search', { params: { keyword } }),
};

// ==================== 市场数据 API ====================
export const marketAPI = {
  // 获取市场快照
  getSnapshot: (date) => api.get('/market/snapshot', { params: { date } }),
  // 获取市场统计
  getStatistics: (date) => api.get('/market/statistics', { params: { date } }),
  // 获取个股排行
  getStockRanking: ({ date, sort, order, page, page_size }) => api.get('/market/stock-ranking', {
    params: { date, sort, order, page, page_size }
  }),
  // 获取涨停股列表
  getLimitUp: (date, page, pageSize) => api.get('/market/limit-up', {
    params: { date, page, page_size: pageSize }
  }),
  // 获取跌停股列表
  getLimitDown: (date, page, pageSize) => api.get('/market/limit-down', {
    params: { date, page, page_size: pageSize }
  }),
  // 获取连板天梯
  getContinuousBoard: (date) => api.get('/market/continuous-board', { params: { date } }),
  // 获取炸板股列表
  getBrokenBoard: (date, page, pageSize) => api.get('/market/broken-board', {
    params: { date, page, page_size: pageSize }
  }),
  // 获取个股排行
  getRank: (date, rankType, direction, page, pageSize) => api.get('/market/rank', {
    params: { date, rank_type: rankType, direction, page, page_size: pageSize }
  }),
  // 获取封板率历史
  getSealRateHistory: (startDate, endDate) => api.get('/market/history/seal-rate', {
    params: { start_date: startDate, end_date: endDate }
  }),
  // 获取个股连板历史
  getLimitTimesHistory: (stockCode, limitType, limit) => api.get('/market/history/limit-times', {
    params: { stock_code: stockCode, limit_type: limitType, limit }
  }),
};

// ==================== 数据采集 API ====================
export const collectorAPI = {
  // 触发日线采集
  triggerDaily: (date) => api.post('/collector/trigger/daily', null, { params: { date } }),
  // 触发分时采集
  triggerIntraday: (date) => api.post('/collector/trigger/intraday', null, { params: { date } }),
  // 触发概念采集
  triggerConcept: () => api.post('/collector/trigger/concept'),
  // 触发涨跌停采集
  triggerLimitList: (date) => api.post('/collector/trigger/limit-list', null, { params: { date } }),
  // 触发概念映射更新
  triggerConceptMapping: () => api.post('/collector/trigger/concept-mapping'),
  // 触发全量采集
  triggerAll: (date) => api.post('/collector/trigger/all', null, { params: { date } }),
};

// ==================== 模拟看盘 API ====================
export const simulationAPI = {
  // 获取市场概览
  getMarketOverview: (date) => api.get('/simulation/market-overview', { params: { date } }),
  // 获取连板天梯详情
  getLadderDetail: (date) => api.get('/simulation/ladder-detail', { params: { date } }),
  // 获取热门个股
  getHotStocks: (date, limit) => api.get('/simulation/hot-stocks', { params: { date, limit } }),
  // 获取资金流向排行
  getCapitalFlowRank: (date, direction, limit) => api.get('/simulation/capital-flow-rank', {
    params: { date, direction, limit }
  }),
  // 获取涨停监控
  getBoardWatch: (date) => api.get('/simulation/board-watch', { params: { date } }),
};

// ==================== 账户管理 API ====================
export const accountAPI = {
  // 获取账户信息
  getInfo: () => api.get('/account/info'),
  // 更新账户信息
  updateInfo: (accountName, initialCapital) => api.put('/account/info', null, {
    params: { account_name: accountName, initial_capital: initialCapital }
  }),
  // 获取持仓
  getPositions: () => api.get('/account/positions'),
  // 更新持仓价格
  updatePositionPrices: () => api.post('/account/positions/update-price'),
  // 获取交易记录
  getTrades: (startDate, endDate, page, pageSize) => api.get('/account/trades', {
    params: { start_date: startDate, end_date: endDate, page, page_size: pageSize }
  }),
  // 执行交易
  executeTrade: (stockCode, action, price, quantity, reason) => api.post('/account/trade', null, {
    params: { stock_code: stockCode, action, price, quantity, reason }
  }),
  // 获取快照
  getSnapshots: (startDate, endDate, limit) => api.get('/account/snapshots', {
    params: { start_date: startDate, end_date: endDate, limit }
  }),
  // 创建快照
  createSnapshot: () => api.post('/account/snapshot/create'),
};

export default api;
