import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 市场API
export const marketAPI = {
  getSentiment: (date) => api.get(`/market/sentiment/${date}`),
  getTodaySentiment: () => api.get('/market/sentiment'),
  getLatestTradingDate: () => api.get('/market/latest-trading-date'),
};

// 股票API
export const stocksAPI = {
  getList: () => api.get('/stocks'),
  add: (stock) => api.post('/stocks', stock),
  delete: (code) => api.delete(`/stocks/${code}`),
  getDetail: (code, date) => api.get(`/stocks/${code}/detail`, { params: { date } }),
  getPopularity: (date, limit = 30) => api.get(`/stocks/popularity/${date}`, { params: { limit } }),
  getIntraday: (code, date) => api.get(`/stocks/intraday/${code}/${date}`),
  // 新增接口
  getQuote: (code) => api.get(`/stocks/${code}/quote`),
  getDaily: (code, startDate, endDate) => api.get(`/stocks/${code}/daily`, { 
    params: { start_date: startDate, end_date: endDate } 
  }),
  batchQuote: (codes) => api.post('/stocks/batch-quote', { codes }),
};

// 概念API
export const conceptsAPI = {
  getList: () => api.get('/concepts'),
  getStocks: (conceptName) => api.get(`/concepts/${conceptName}/stocks`),
  addStock: (conceptName, data) => api.post(`/concepts/${conceptName}/stocks`, data),
  removeStock: (conceptName, code) => api.delete(`/concepts/${conceptName}/stocks/${code}`),
  getHeatmap: (date) => api.get(`/concepts/heatmap/${date}`),
  getAnalysis: (conceptName, date) => api.get(`/concepts/${conceptName}/analysis/${date}`),
};

// 分析API
export const analysisAPI = {
  analyzeStock: (code, date) => api.post('/analysis/stock', { code, date }),
  analyzeConcept: (conceptName, date) => api.post('/analysis/concept', { concept_name: conceptName, date }),
  getLeaders: (date) => api.get(`/analysis/leaders/${date}`),
};

export default api;
