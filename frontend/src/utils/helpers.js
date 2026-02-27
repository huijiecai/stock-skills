/**
 * 前端工具函数集合
 */

/**
 * 格式化数值
 * @param {number} num - 数值
 * @param {number} decimals - 小数位数
 * @returns {string} 格式化后的字符串
 */
export const formatNumber = (num, decimals = 2) => {
  if (num === null || num === undefined || isNaN(num)) return '-';
  
  if (Math.abs(num) >= 100000000) {
    return (num / 100000000).toFixed(decimals) + '亿';
  }
  if (Math.abs(num) >= 10000) {
    return (num / 10000).toFixed(decimals) + '万';
  }
  return num.toFixed(decimals);
};

/**
 * 格式化涨跌幅
 * @param {number} value - 涨跌幅（小数形式）
 * @param {boolean} withPrefix - 是否添加+/-前缀
 * @returns {string} 格式化后的字符串
 */
export const formatChangePercent = (value, withPrefix = true) => {
  if (value === null || value === undefined || isNaN(value)) return '-';
  
  const prefix = withPrefix && value >= 0 ? '+' : '';
  return `${prefix}${(value * 100).toFixed(2)}%`;
};

/**
 * 格式化涨跌额
 * @param {number} value - 涨跌额
 * @param {boolean} withPrefix - 是否添加+/-前缀
 * @returns {string} 格式化后的字符串
 */
export const formatChange = (value, withPrefix = true) => {
  if (value === null || value === undefined || isNaN(value)) return '-';
  
  const prefix = withPrefix && value >= 0 ? '+' : '';
  return `${prefix}${value.toFixed(2)}`;
};

/**
 * 格式化价格
 * @param {number} value - 价格
 * @param {number} decimals - 小数位数
 * @returns {string} 格式化后的字符串
 */
export const formatPrice = (value, decimals = 2) => {
  if (value === null || value === undefined || isNaN(value)) return '-';
  return value.toFixed(decimals);
};

/**
 * 获取涨跌幅颜色
 * @param {number} value - 涨跌幅
 * @returns {string} 颜色代码
 */
export const getChangeColor = (value) => {
  if (value === null || value === undefined || isNaN(value)) return '#666';
  return value >= 0 ? '#cf1322' : '#3f8600';
};

/**
 * 复制文本到剪贴板
 * @param {string} text - 要复制的文本
 * @returns {Promise<boolean>} 是否成功
 */
export const copyToClipboard = async (text) => {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (err) {
    // 降级方案
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.left = '-999999px';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
      document.execCommand('copy');
      return true;
    } catch (err) {
      console.error('复制失败:', err);
      return false;
    } finally {
      document.body.removeChild(textArea);
    }
  }
};

/**
 * 导出CSV文件
 * @param {Array<Object>} data - 数据数组
 * @param {Array<string>} headers - 表头数组
 * @param {string} filename - 文件名
 */
export const exportToCSV = (data, headers, filename) => {
  if (!data || data.length === 0) {
    return false;
  }
  
  const csvContent = [
    headers.join(','),
    ...data.map(row => 
      headers.map(header => {
        const value = row[header] ?? '';
        // 处理包含逗号的字段
        return typeof value === 'string' && value.includes(',') 
          ? `"${value}"` 
          : value;
      }).join(',')
    )
  ].join('\n');
  
  const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  
  return true;
};

/**
 * 防抖函数
 * @param {Function} func - 要防抖的函数
 * @param {number} wait - 等待时间（毫秒）
 * @returns {Function} 防抖后的函数
 */
export const debounce = (func, wait = 300) => {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
};

/**
 * 节流函数
 * @param {Function} func - 要节流的函数
 * @param {number} wait - 等待时间（毫秒）
 * @returns {Function} 节流后的函数
 */
export const throttle = (func, wait = 300) => {
  let inThrottle;
  return function executedFunction(...args) {
    if (!inThrottle) {
      func(...args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, wait);
    }
  };
};

/**
 * 格式化日期
 * @param {Date|string} date - 日期对象或字符串
 * @param {string} format - 格式化模板
 * @returns {string} 格式化后的日期字符串
 */
export const formatDate = (date, format = 'YYYY-MM-DD') => {
  const d = new Date(date);
  if (isNaN(d.getTime())) return '-';
  
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  const hour = String(d.getHours()).padStart(2, '0');
  const minute = String(d.getMinutes()).padStart(2, '0');
  const second = String(d.getSeconds()).padStart(2, '0');
  
  return format
    .replace('YYYY', year)
    .replace('MM', month)
    .replace('DD', day)
    .replace('HH', hour)
    .replace('mm', minute)
    .replace('ss', second);
};

/**
 * 本地存储封装
 */
export const storage = {
  get: (key, defaultValue = null) => {
    try {
      const item = localStorage.getItem(key);
      return item ? JSON.parse(item) : defaultValue;
    } catch (e) {
      console.error('读取localStorage失败:', e);
      return defaultValue;
    }
  },
  
  set: (key, value) => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (e) {
      console.error('写入localStorage失败:', e);
      return false;
    }
  },
  
  remove: (key) => {
    try {
      localStorage.removeItem(key);
      return true;
    } catch (e) {
      console.error('删除localStorage失败:', e);
      return false;
    }
  },
  
  clear: () => {
    try {
      localStorage.clear();
      return true;
    } catch (e) {
      console.error('清空localStorage失败:', e);
      return false;
    }
  }
};

/**
 * 验证股票代码
 * @param {string} code - 股票代码
 * @returns {boolean} 是否有效
 */
export const isValidStockCode = (code) => {
  return /^\d{6}$/.test(code);
};

/**
 * 获取市场名称
 * @param {string} market - 市场代码（SH/SZ）
 * @returns {string} 市场名称
 */
export const getMarketName = (market) => {
  const marketMap = {
    'SH': '上海',
    'SZ': '深圳',
    'BJ': '北京'
  };
  return marketMap[market] || market;
};

/**
 * 错误处理
 * @param {Error} error - 错误对象
 * @returns {string} 错误消息
 */
export const handleError = (error) => {
  if (error.response) {
    // 服务器返回错误
    const { status, data } = error.response;
    if (status === 404) return '请求的资源不存在';
    if (status === 500) return '服务器内部错误';
    if (status === 401) return '未授权，请登录';
    if (status === 403) return '没有权限访问';
    return data?.detail || data?.message || '请求失败';
  } else if (error.request) {
    // 请求已发送但没有收到响应
    return '网络连接失败，请检查网络';
  } else {
    // 其他错误
    return error.message || '发生未知错误';
  }
};
