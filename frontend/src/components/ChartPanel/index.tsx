import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import * as echarts from 'echarts';
import { StockIntraday, StockDaily, IndexIntraday, IndexDaily } from '../../types';

interface IntradayChartProps {
  data: StockIntraday[] | IndexIntraday[];
  preClose: number;
  name?: string;
  height?: number;
}

interface KLineChartProps {
  data: (StockDaily | IndexDaily)[];
  maLines?: Array<{ key: string; color: string }>;
  height?: number;
}

/**
 * 分时图组件
 */
export const IntradayChart: React.FC<IntradayChartProps> = ({ 
  data = [], 
  preClose = 0, 
  name = '', 
  height = 400 
}) => {
  const option = useMemo(() => {
    if (!data || data.length === 0) {
      return {};
    }

    const times = data.map(d => d.time);
    const prices = data.map(d => d.price);
    const avgs = data.map(d => ('avg' in d ? d.avg : d.price) || d.price);
    const volumes = data.map(d => d.volume || 0);
    
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
        formatter: (params: any) => {
          const time = params[0].axisValue;
          const price = params[0].value;
          const change = ((price - preClose) / preClose * 100).toFixed(2);
          const sign = Number(change) >= 0 ? '+' : '';
          return `
            <div style="font-family: SF Mono, monospace;">
              <div style="color: #787B86; margin-bottom: 4px;">${time}</div>
              <div>价格: <span style="color: ${Number(change) >= 0 ? '#26A69A' : '#EF5350'}">${price.toFixed(2)}</span></div>
              <div>涨跌: <span style="color: ${Number(change) >= 0 ? '#26A69A' : '#EF5350'}">${sign}${change}%</span></div>
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
            formatter: (value: number) => value.toFixed(2)
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
            color: (params: any) => {
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
 */
export const KLineChart: React.FC<KLineChartProps> = ({ 
  data = [], 
  maLines = [], 
  height = 400 
}) => {
  const option = useMemo(() => {
    if (!data || data.length === 0) {
      return {};
    }

    const dates = data.map(d => d.trade_date || (d as any).date);
    const ohlc = data.map(d => [d.open, d.close, d.low, d.high]);
    const volumes = data.map(d => d.volume || 0);
    const closes = data.map(d => d.close);

    // 计算均线
    const calculateMA = (dayCount: number) => {
      const result: (string | number)[] = [];
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

    const maData: Record<string, (string | number)[]> = {};
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
        formatter: (params: any) => {
          const date = params[0].axisValue;
          const ohlcData = params[0].data;
          const change = ((ohlcData[1] - ohlcData[0]) / ohlcData[0] * 100).toFixed(2);
          const sign = Number(change) >= 0 ? '+' : '';
          return `
            <div style="font-family: SF Mono, monospace;">
              <div style="color: #787B86; margin-bottom: 4px;">${date}</div>
              <div>开: ${ohlcData[0]?.toFixed(2)} 高: ${ohlcData[3]?.toFixed(2)}</div>
              <div>收: <span style="color: ${Number(change) >= 0 ? '#26A69A' : '#EF5350'}">${ohlcData[1]?.toFixed(2)}</span> 低: ${ohlcData[2]?.toFixed(2)}</div>
              <div>涨跌: <span style="color: ${Number(change) >= 0 ? '#26A69A' : '#EF5350'}">${sign}${change}%</span></div>
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
            color: (params: any) => {
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

interface ChartPanelProps {
  type: 'intraday' | 'daily';
  data: StockIntraday[] | IndexIntraday[] | StockDaily[] | IndexDaily[];
  preClose?: number;
  name?: string;
  height?: number;
  onTypeChange?: (type: 'intraday' | 'daily') => void;
}

/**
 * 图表面板组件 - 统一的分时/K线切换
 */
const ChartPanel: React.FC<ChartPanelProps> = ({
  type,
  data,
  preClose = 0,
  name = '',
  height = 400,
  onTypeChange
}) => {
  return (
    <div className="chart-panel">
      {onTypeChange && (
        <div className="chart-tabs" style={{ marginBottom: 12 }}>
          <span 
            className={`chart-tab ${type === 'intraday' ? 'active' : ''}`}
            onClick={() => onTypeChange('intraday')}
          >
            分时
          </span>
          <span 
            className={`chart-tab ${type === 'daily' ? 'active' : ''}`}
            onClick={() => onTypeChange('daily')}
          >
            日K
          </span>
        </div>
      )}
      {type === 'intraday' ? (
        <IntradayChart 
          data={data as (StockIntraday[] | IndexIntraday[])}
          preClose={preClose}
          name={name}
          height={height}
        />
      ) : (
        <KLineChart 
          data={data as (StockDaily[] | IndexDaily[])}
          maLines={[
            { key: 'ma5', color: '#fff' },
            { key: 'ma10', color: '#FFA726' },
            { key: 'ma20', color: '#9C27B0' },
          ]}
          height={height}
        />
      )}
    </div>
  );
};

export default ChartPanel;
