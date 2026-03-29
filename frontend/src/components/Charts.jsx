import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import * as echarts from 'echarts';

/**
 * 分时图组件
 * @param {Array} data - 分时数据 [{time: '09:30', price: 10.5, volume: 1000, avg: 10.3}, ...]
 * @param {number} preClose - 昨收价
 * @param {string} name - 股票名称
 * @param {number} height - 图表高度
 */
export const IntradayChart = ({ data = [], preClose = 0, name = '', height = 400 }) => {
  const option = useMemo(() => {
    if (!data || data.length === 0) {
      return {};
    }

    const times = data.map(d => d.time);
    const prices = data.map(d => d.price);
    const avgs = data.map(d => d.avg || d.price);
    const volumes = data.map(d => d.volume || 0);
    
    // 计算涨跌幅范围
    const maxPrice = Math.max(...prices, preClose);
    const minPrice = Math.min(...prices, preClose);
    const priceRange = Math.max(maxPrice - preClose, preClose - minPrice);
    const yMin = preClose - priceRange * 1.1;
    const yMax = preClose + priceRange * 1.1;

    return {
      animation: false,
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(30, 34, 45, 0.95)',
        borderColor: '#2A2E39',
        textStyle: { color: '#D1D4DC' },
        formatter: (params) => {
          const time = params[0].axisValue;
          const price = params[0].value;
          const change = ((price - preClose) / preClose * 100).toFixed(2);
          const sign = change >= 0 ? '+' : '';
          return `
            <div style="font-family: SF Mono, monospace;">
              <div style="color: #787B86; margin-bottom: 4px;">${time}</div>
              <div>价格: <span style="color: ${change >= 0 ? '#26A69A' : '#EF5350'}">${price.toFixed(2)}</span></div>
              <div>涨跌: <span style="color: ${change >= 0 ? '#26A69A' : '#EF5350'}">${sign}${change}%</span></div>
            </div>
          `;
        }
      },
      axisPointer: {
        link: [{ xAxisIndex: 'all' }],
        lineStyle: { color: '#787B86', type: 'dashed' }
      },
      grid: [
        { left: 60, right: 50, top: 20, height: '60%' },
        { left: 60, right: 50, top: '75%', height: '18%' }
      ],
      xAxis: [
        {
          type: 'category',
          data: times,
          boundaryGap: false,
          axisLine: { lineStyle: { color: '#2A2E39' } },
          axisTick: { show: false },
          axisLabel: { 
            color: '#787B86',
            fontSize: 11,
            interval: Math.floor(times.length / 6)
          },
          splitLine: { show: false }
        },
        {
          type: 'category',
          gridIndex: 1,
          data: times,
          boundaryGap: false,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: { show: false },
          splitLine: { show: false }
        }
      ],
      yAxis: [
        {
          type: 'value',
          min: yMin,
          max: yMax,
          position: 'right',
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: { 
            color: '#787B86',
            fontSize: 11,
            formatter: (value) => value.toFixed(2)
          },
          splitLine: { 
            lineStyle: { color: '#2A2E39' }
          }
        },
        {
          type: 'value',
          gridIndex: 1,
          splitNumber: 2,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: { show: false },
          splitLine: { show: false }
        }
      ],
      series: [
        {
          name: '价格',
          type: 'line',
          data: prices,
          smooth: true,
          symbol: 'none',
          lineStyle: {
            width: 1.5,
            color: '#2962FF'
          },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(41, 98, 255, 0.3)' },
                { offset: 1, color: 'rgba(41, 98, 255, 0.02)' }
              ]
            }
          },
          markLine: {
            silent: true,
            symbol: 'none',
            lineStyle: { color: '#787B86', type: 'dashed', width: 1 },
            data: [{ yAxis: preClose, label: { show: false } }]
          }
        },
        {
          name: '均价',
          type: 'line',
          data: avgs,
          smooth: true,
          symbol: 'none',
          lineStyle: { width: 1, color: '#FFA726', type: 'dashed' }
        },
        {
          name: '成交量',
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: volumes,
          itemStyle: {
            color: (params) => {
              const idx = params.dataIndex;
              if (idx === 0) return prices[0] >= preClose ? '#26A69A' : '#EF5350';
              return prices[idx] >= prices[idx - 1] ? '#26A69A' : '#EF5350';
            }
          },
          barWidth: '60%'
        }
      ]
    };
  }, [data, preClose, name]);

  if (!data || data.length === 0) {
    return <div className="empty-data">暂无分时数据</div>;
  }

  return (
    <ReactECharts
      echarts={echarts}
      option={option}
      style={{ height }}
      notMerge={true}
      lazyUpdate={true}
    />
  );
};

/**
 * K线图组件
 * @param {Array} data - K线数据 [{date: '2026-03-27', open: 10, close: 10.5, high: 11, low: 9.8, volume: 10000}, ...]
 * @param {Array} maLines - 均线配置 [{key: 'ma5', color: '#fff'}, ...]
 * @param {number} height - 图表高度
 */
export const KLineChart = ({ data = [], maLines = [], height = 400 }) => {
  const option = useMemo(() => {
    if (!data || data.length === 0) {
      return {};
    }

    const dates = data.map(d => d.date);
    const ohlc = data.map(d => [d.open, d.close, d.low, d.high]);
    const volumes = data.map(d => d.volume || 0);
    const closes = data.map(d => d.close);

    // 计算均线
    const calculateMA = (dayCount) => {
      const result = [];
      for (let i = 0; i < closes.length; i++) {
        if (i < dayCount - 1) {
          result.push('-');
          continue;
        }
        let sum = 0;
        for (let j = 0; j < dayCount; j++) {
          sum += closes[i - j];
        }
        result.push((sum / dayCount).toFixed(2));
      }
      return result;
    };

    const maData = {};
    maLines.forEach(ma => {
      maData[ma.key] = calculateMA(parseInt(ma.key.replace('ma', '')));
    });

    return {
      animation: false,
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(30, 34, 45, 0.95)',
        borderColor: '#2A2E39',
        textStyle: { color: '#D1D4DC' },
        axisPointer: {
          type: 'cross',
          crossStyle: { color: '#787B86' }
        },
        formatter: (params) => {
          const date = params[0].axisValue;
          const ohlcData = params[0].data;
          const change = ((ohlcData[1] - ohlcData[0]) / ohlcData[0] * 100).toFixed(2);
          const sign = change >= 0 ? '+' : '';
          return `
            <div style="font-family: SF Mono, monospace;">
              <div style="color: #787B86; margin-bottom: 4px;">${date}</div>
              <div>开: ${ohlcData[0]?.toFixed(2)} 高: ${ohlcData[3]?.toFixed(2)}</div>
              <div>收: <span style="color: ${change >= 0 ? '#26A69A' : '#EF5350'}">${ohlcData[1]?.toFixed(2)}</span> 低: ${ohlcData[2]?.toFixed(2)}</div>
              <div>涨跌: <span style="color: ${change >= 0 ? '#26A69A' : '#EF5350'}">${sign}${change}%</span></div>
            </div>
          `;
        }
      },
      grid: [
        { left: 60, right: 50, top: 20, height: '55%' },
        { left: 60, right: 50, top: '70%', height: '18%' }
      ],
      xAxis: [
        {
          type: 'category',
          data: dates,
          axisLine: { lineStyle: { color: '#2A2E39' } },
          axisTick: { show: false },
          axisLabel: { 
            color: '#787B86',
            fontSize: 11,
            interval: Math.floor(dates.length / 6)
          }
        },
        {
          type: 'category',
          gridIndex: 1,
          data: dates,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: { show: false }
        }
      ],
      yAxis: [
        {
          type: 'value',
          position: 'right',
          scale: true,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: { 
            color: '#787B86',
            fontSize: 11
          },
          splitLine: { 
            lineStyle: { color: '#2A2E39' }
          }
        },
        {
          type: 'value',
          gridIndex: 1,
          splitNumber: 2,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: { show: false },
          splitLine: { show: false }
        }
      ],
      dataZoom: [
        {
          type: 'inside',
          xAxisIndex: [0, 1],
          start: Math.max(0, (dates.length - 60) / dates.length * 100),
          end: 100
        }
      ],
      series: [
        {
          name: 'K线',
          type: 'candlestick',
          data: ohlc,
          itemStyle: {
            color: '#26A69A',
            color0: '#EF5350',
            borderColor: '#26A69A',
            borderColor0: '#EF5350'
          }
        },
        ...maLines.map(ma => ({
          name: ma.key.toUpperCase(),
          type: 'line',
          data: maData[ma.key],
          smooth: true,
          symbol: 'none',
          lineStyle: { width: 1, color: ma.color }
        })),
        {
          name: '成交量',
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: volumes,
          itemStyle: {
            color: (params) => {
              const idx = params.dataIndex;
              if (idx === 0 || !ohlc[idx - 1]) return '#26A69A';
              return ohlc[idx][1] >= ohlc[idx - 1][1] ? '#26A69A' : '#EF5350';
            }
          },
          barWidth: '60%'
        }
      ]
    };
  }, [data, maLines]);

  if (!data || data.length === 0) {
    return <div className="empty-data">暂无K线数据</div>;
  }

  return (
    <ReactECharts
      echarts={echarts}
      option={option}
      style={{ height }}
      notMerge={true}
      lazyUpdate={true}
    />
  );
};

export default { IntradayChart, KLineChart };
