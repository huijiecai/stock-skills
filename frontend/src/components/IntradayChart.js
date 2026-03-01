import React, { useEffect, useRef } from 'react';
import * as echarts from 'echarts';

/**
 * 分时图组件
 * @param {Object} props
 * @param {Array} props.data - 分时数据 [{trade_time, price, avg_price, change_percent, volume, turnover}]
 * @param {String} props.stockCode - 股票代码
 * @param {String} props.stockName - 股票名称
 * @param {String} props.date - 日期
 * @param {Object} props.auctionData - 竞价数据 {open_vol, open_amount, close_vol, close_amount}
 */
const IntradayChart = ({ data, stockCode, stockName, date, auctionData }) => {
  const chartRef = useRef(null);
  const chartInstance = useRef(null);

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
    const times = data.map(item => item.trade_time.substring(11, 16));
    const prices = data.map(item => item.price);
    
    // 计算每分钟的增量（Tushare返回的是累计值）
    const minuteVolumes = [];
    const minuteTurnovers = [];
    for (let i = 0; i < data.length; i++) {
      if (i === 0) {
        minuteVolumes.push(Math.max(0, data[i].volume || 0));
        minuteTurnovers.push(Math.max(0, data[i].turnover || 0));
      } else {
        const volDiff = (data[i].volume || 0) - (data[i - 1].volume || 0);
        const amtDiff = (data[i].turnover || 0) - (data[i - 1].turnover || 0);
        minuteVolumes.push(Math.max(0, volDiff < 0 ? data[i].volume : volDiff));
        minuteTurnovers.push(Math.max(0, amtDiff < 0 ? data[i].turnover : amtDiff));
      }
    }

    // 获取最新价格和涨跌幅
    const currentPrice = prices[prices.length - 1];
    const lastItem = data[data.length - 1];
    const changePercent = (lastItem.change_percent * 100).toFixed(2);

    // 计算累计值
    // volume单位：股，turnover单位：元
    const totalVolume = data[data.length - 1].volume || 0;
    const totalTurnover = data[data.length - 1].turnover || 0;

    // 配置图表
    const option = {
      title: {
        text: `${stockName} (${stockCode})`,
        subtext: `${date} | ${currentPrice.toFixed(2)} 元 | ${changePercent > 0 ? '+' : ''}${changePercent}%`,
        left: 'center',
        top: 5,
        textStyle: { fontSize: 16, fontWeight: 'bold' },
        subtextStyle: { fontSize: 13, color: changePercent >= 0 ? '#ef5350' : '#26a69a' }
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        formatter: function(params) {
          let result = `时间: ${params[0].axisValue}<br/>`;
          params.forEach(item => {
            if (item.seriesName === '分时线') {
              const dataIndex = item.dataIndex;
              const dataItem = data[dataIndex];
              const percent = dataItem ? (dataItem.change_percent * 100).toFixed(2) : '0.00';
              result += `${item.marker}${item.seriesName}: ${item.value.toFixed(2)} 元 (${percent > 0 ? '+' : ''}${percent}%)<br/>`;
            } else if (item.seriesName === '成交额') {
              // turnover单位：元
              result += `${item.marker}成交额: ${(item.value / 10000).toFixed(2)} 万元<br/>`;
            } else if (item.seriesName === '成交量') {
              // volume单位：股
              result += `${item.marker}成交量: ${(item.value / 100).toFixed(0)} 手<br/>`;
            }
          });
          return result;
        }
      },
      legend: {
        data: ['成交额', '成交量'],
        top: 5,
        right: 10,
        selected: { '成交额': true, '成交量': false }
      },
      grid: [
        { left: '8%', right: '3%', top: '15%', height: '50%' },
        { left: '8%', right: '3%', top: '70%', height: '18%' }
      ],
      xAxis: [
        { type: 'category', data: times, gridIndex: 0, axisLabel: { interval: Math.floor(times.length / 6) }, splitLine: { show: true, lineStyle: { color: '#f0f0f0' } } },
        { type: 'category', data: times, gridIndex: 1, axisLabel: { show: false } }
      ],
      yAxis: [
        { type: 'value', gridIndex: 0, scale: true, splitLine: { lineStyle: { color: '#f0f0f0' } }, axisLabel: { formatter: '{value}' } },
        { 
          type: 'value', 
          gridIndex: 1, 
          splitLine: { show: false }, 
          axisLabel: { 
            formatter: v => {
              // 成交额单位元，成交量单位股
              if (v >= 100000000) return (v/100000000).toFixed(1) + '亿';
              if (v >= 10000) return (v/10000).toFixed(0) + '万';
              return v;
            }
          } 
        }
      ],
      series: [
        {
          name: '分时线',
          type: 'line',
          data: prices,
          xAxisIndex: 0,
          yAxisIndex: 0,
          smooth: false,
          symbol: 'none',
          lineStyle: { color: '#2196f3', width: 1 },
          itemStyle: { color: '#2196f3' },
          areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(33, 150, 243, 0.3)' },
            { offset: 1, color: 'rgba(33, 150, 243, 0.05)' }
          ])}
        },
        {
          name: '成交额',
          type: 'bar',
          data: minuteTurnovers,
          xAxisIndex: 1,
          yAxisIndex: 1,
          itemStyle: { color: params => params.dataIndex === 0 ? '#ef5350' : (prices[params.dataIndex] >= prices[params.dataIndex - 1] ? '#ef5350' : '#26a69a') }
        },
        {
          name: '成交量',
          type: 'bar',
          data: minuteVolumes,
          xAxisIndex: 1,
          yAxisIndex: 1,
          itemStyle: { color: params => params.dataIndex === 0 ? '#ff9800' : (prices[params.dataIndex] >= prices[params.dataIndex - 1] ? '#ff9800' : '#9c27b0') }
        }
      ]
    };

    chartInstance.current.setOption(option);

    const handleResize = () => chartInstance.current?.resize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [data, stockCode, stockName, date]);

  useEffect(() => {
    return () => {
      if (chartInstance.current) {
        chartInstance.current.dispose();
        chartInstance.current = null;
      }
    };
  }, []);

  if (!data || data.length === 0) {
    return <div style={{ height: '500px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999' }}>暂无分时数据</div>;
  }

  // 计算累计值（volume单位：股，turnover单位：元）
  const totalVolume = data[data.length - 1].volume || 0;
  const totalTurnover = data[data.length - 1].turnover || 0;

  // 格式化竞价数据
  const formatAuction = () => {
    if (!auctionData) return null;
    const openInfo = auctionData.open_vol ? `开盘竞价: ${(auctionData.open_vol / 10000).toFixed(0)}万手 / ${(auctionData.open_amount / 100000000).toFixed(2)}亿` : '';
    const closeInfo = auctionData.close_vol ? `收盘竞价: ${(auctionData.close_vol / 10000).toFixed(0)}万手 / ${(auctionData.close_amount / 100000000).toFixed(2)}亿` : '';
    if (openInfo || closeInfo) {
      return <span style={{ color: '#722ed1' }}>{openInfo} {closeInfo}</span>;
    }
    return null;
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', fontSize: 13, color: '#666' }}>
        <span>累计成交额: <b style={{ color: '#1890ff' }}>{(totalTurnover / 100000000).toFixed(2)} 亿</b></span>
        <span>累计成交量: <b style={{ color: '#ff9800' }}>{(totalVolume / 100 / 10000).toFixed(2)} 万手</b></span>
      </div>
      {formatAuction() && (
        <div style={{ padding: '4px 0', fontSize: 12, color: '#666' }}>
          {formatAuction()}
        </div>
      )}
      <div ref={chartRef} style={{ width: '100%', height: '480px' }} />
    </div>
  );
};

export default IntradayChart;
