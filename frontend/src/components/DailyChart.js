import React, { useEffect, useRef, useState } from 'react';
import * as echarts from 'echarts';

/**
 * 日K线图组件
 * @param {Object} props
 * @param {Array} props.data - K线数据 [{date, open, high, low, close, volume, turnover}]
 * @param {String} props.stockCode - 股票代码
 * @param {String} props.stockName - 股票名称
 * @param {Function} props.onDateClick - 点击日期回调，用于跳转到分时图
 */
const DailyChart = ({ data, stockCode, stockName, onDateClick }) => {
  const chartRef = useRef(null);
  const chartInstance = useRef(null);
  const [volumeType, setVolumeType] = useState('turnover'); // 默认成交额

  useEffect(() => {
    if (!data || data.length === 0) {
      if (chartInstance.current) {
        chartInstance.current.dispose();
        chartInstance.current = null;
      }
      return;
    }

    if (!chartInstance.current && chartRef.current) {
      chartInstance.current = echarts.init(chartRef.current);
    }

    if (!chartInstance.current) return;

    // 处理数据
    const dates = data.map(item => item.date);
    const ohlcData = data.map(item => [item.open, item.close, item.low, item.high]);
    const volumes = data.map(item => item.volume);
    const turnovers = data.map(item => item.turnover);
    const rawData = data;

    // 根据类型选择数据
    const barData = volumeType === 'turnover' ? turnovers : volumes;
    const barName = volumeType === 'turnover' ? '成交额' : '成交量';

    // 计算均线
    const ma5 = calculateMA(data.map(d => d.close), 5);
    const ma10 = calculateMA(data.map(d => d.close), 10);
    const ma20 = calculateMA(data.map(d => d.close), 20);

    // 配置图表
    const option = {
      title: {
        text: `${stockName} (${stockCode}) 日K线`,
        left: 'center',
        top: 5,
        textStyle: { fontSize: 16, fontWeight: 'bold' }
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        formatter: function (params) {
          const dataIndex = params[0].dataIndex;
          const item = rawData[dataIndex];
          let result = `<strong>${params[0].axisValue}</strong><br/>`;
          result += `开盘: ${item.open?.toFixed(2)} | 收盘: ${item.close?.toFixed(2)}<br/>`;
          result += `最高: ${item.high?.toFixed(2)} | 最低: ${item.low?.toFixed(2)}<br/>`;
          const changePct = item.change_percent;
          const changeColor = changePct >= 0 ? '#f5222d' : '#52c41a';
          result += `涨跌幅: <span style="color:${changeColor}">${changePct >= 0 ? '+' : ''}${(changePct * 100).toFixed(2)}%</span><br/>`;
          result += `成交量: ${(item.volume / 10000).toFixed(2)}万手<br/>`;
          result += `成交额: ${(item.turnover / 100000000).toFixed(2)}亿元<br/>`;
          if (item.turnover_rate) result += `换手率: ${(item.turnover_rate * 100).toFixed(2)}%<br/>`;
          result += `<span style="color:#1890ff;font-size:11px">💡 点击查看分时图</span>`;
          return result;
        }
      },
      legend: {
        data: ['K线', 'MA5', 'MA10', 'MA20', barName],
        top: 5,
        right: 10
      },
      grid: [
        { left: '8%', right: '3%', top: '15%', height: '50%' },
        { left: '8%', right: '3%', top: '72%', height: '14%' }
      ],
      xAxis: [
        { type: 'category', data: dates, gridIndex: 0, axisLabel: { interval: Math.floor(dates.length / 8), formatter: v => v.substring(5) }, splitLine: { show: true, lineStyle: { color: '#f0f0f0' } } },
        { type: 'category', data: dates, gridIndex: 1, axisLabel: { show: false } }
      ],
      yAxis: [
        { type: 'value', gridIndex: 0, scale: true, splitLine: { lineStyle: { color: '#f0f0f0' } }, axisLabel: { formatter: '{value}' } },
        { type: 'value', gridIndex: 1, splitLine: { show: false }, axisLabel: { formatter: v => volumeType === 'turnover' ? (v >= 1e8 ? (v/1e8).toFixed(0)+'亿' : (v/1e4).toFixed(0)+'万') : (v >= 1e4 ? (v/1e4).toFixed(0)+'万' : v) } }
      ],
      dataZoom: [
        { type: 'inside', xAxisIndex: [0, 1], start: 50, end: 100 },
        { show: true, xAxisIndex: [0, 1], type: 'slider', top: '88%', start: 50, end: 100 }
      ],
      series: [
        { name: 'K线', type: 'candlestick', data: ohlcData, xAxisIndex: 0, yAxisIndex: 0, itemStyle: { color: '#f5222d', color0: '#52c41a', borderColor: '#f5222d', borderColor0: '#52c41a' } },
        { name: 'MA5', type: 'line', data: ma5, xAxisIndex: 0, yAxisIndex: 0, smooth: true, symbol: 'none', lineStyle: { color: '#1890ff', width: 1 } },
        { name: 'MA10', type: 'line', data: ma10, xAxisIndex: 0, yAxisIndex: 0, smooth: true, symbol: 'none', lineStyle: { color: '#ff9800', width: 1 } },
        { name: 'MA20', type: 'line', data: ma20, xAxisIndex: 0, yAxisIndex: 0, smooth: true, symbol: 'none', lineStyle: { color: '#9c27b0', width: 1 } },
        { name: barName, type: 'bar', data: barData, xAxisIndex: 1, yAxisIndex: 1, itemStyle: { color: params => params.dataIndex === 0 ? '#f5222d' : (ohlcData[params.dataIndex][1] >= ohlcData[params.dataIndex - 1][1] ? '#f5222d' : '#52c41a') } }
      ]
    };

    chartInstance.current.setOption(option);

    if (onDateClick) {
      chartInstance.current.off('click');
      chartInstance.current.on('click', function(params) {
        if (params.componentType === 'series') {
          const date = dates[params.dataIndex];
          if (date) onDateClick(date);
        }
      });
    }

    const handleResize = () => chartInstance.current?.resize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [data, stockCode, stockName, onDateClick, volumeType]);

  useEffect(() => {
    return () => {
      if (chartInstance.current) {
        chartInstance.current.dispose();
        chartInstance.current = null;
      }
    };
  }, []);

  function calculateMA(data, dayCount) {
    const result = [];
    for (let i = 0; i < data.length; i++) {
      if (i < dayCount - 1) { result.push(null); continue; }
      let sum = 0;
      for (let j = 0; j < dayCount; j++) sum += data[i - j];
      result.push(sum / dayCount);
    }
    return result;
  }

  if (!data || data.length === 0) {
    return <div style={{ height: '600px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999' }}>暂无K线数据</div>;
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', padding: '8px 0', fontSize: 13 }}>
        <span style={{ marginRight: 16, cursor: 'pointer', color: volumeType === 'turnover' ? '#1890ff' : '#666', fontWeight: volumeType === 'turnover' ? 'bold' : 'normal' }} onClick={() => setVolumeType('turnover')}>成交额</span>
        <span style={{ cursor: 'pointer', color: volumeType === 'volume' ? '#ff9800' : '#666', fontWeight: volumeType === 'volume' ? 'bold' : 'normal' }} onClick={() => setVolumeType('volume')}>成交量</span>
      </div>
      <div ref={chartRef} style={{ width: '100%', height: '520px' }} />
    </div>
  );
};

export default DailyChart;
