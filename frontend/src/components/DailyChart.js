import React, { useEffect, useRef } from 'react';
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

  useEffect(() => {
    if (!data || data.length === 0) {
      // 如果没有数据，清理图表实例
      if (chartInstance.current) {
        chartInstance.current.dispose();
        chartInstance.current = null;
      }
      return;
    }

    // 初始化图表（只初始化一次）
    if (!chartInstance.current && chartRef.current) {
      chartInstance.current = echarts.init(chartRef.current);
    }

    // 如果图表实例不存在，返回
    if (!chartInstance.current) return;

    // 处理数据
    const dates = data.map(item => item.date);
    const ohlcData = data.map(item => [item.open, item.close, item.low, item.high]);
    const volumes = data.map(item => item.volume);
    // 保存原始数据用于tooltip显示
    const rawData = data;

    // 计算均线
    const ma5 = calculateMA(data.map(d => d.close), 5);
    const ma10 = calculateMA(data.map(d => d.close), 10);
    const ma20 = calculateMA(data.map(d => d.close), 20);

    // 配置图表
    const option = {
      title: {
        text: `${stockName} (${stockCode}) 日K线`,
        left: 'center',
        textStyle: {
          fontSize: 16,
          fontWeight: 'bold'
        }
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'cross'
        },
        formatter: function (params) {
          const dataIndex = params[0].dataIndex;
          const item = rawData[dataIndex];
          let result = `<strong>${params[0].axisValue}</strong><br/>`;
          result += `─────────────<br/>`;
          result += `开盘: ${item.open?.toFixed(2)}<br/>`;
          result += `收盘: ${item.close?.toFixed(2)}<br/>`;
          result += `最高: ${item.high?.toFixed(2)}<br/>`;
          result += `最低: ${item.low?.toFixed(2)}<br/>`;
          result += `─────────────<br/>`;
          // 涨跌幅
          const changePct = item.change_percent;
          const changeSign = changePct >= 0 ? '+' : '';
          const changeColor = changePct >= 0 ? '#f5222d' : '#52c41a';
          result += `涨跌幅: <span style="color:${changeColor}">${changeSign}${(changePct * 100).toFixed(2)}%</span><br/>`;
          // 成交量（万手）
          const volWan = (item.volume / 10000).toFixed(2);
          result += `成交量: ${volWan}万手<br/>`;
          // 成交额（亿元）
          const amtYi = (item.turnover / 100000000).toFixed(2);
          result += `成交额: ${amtYi}亿元<br/>`;
          // 换手率
          if (item.turnover_rate !== null && item.turnover_rate !== undefined) {
            result += `换手率: ${(item.turnover_rate * 100).toFixed(2)}%<br/>`;
          }
          // 实换率（自由流通股换手率）
          if (item.turnover_rate_f !== null && item.turnover_rate_f !== undefined) {
            result += `实换率: ${(item.turnover_rate_f * 100).toFixed(2)}%<br/>`;
          }
          result += `─────────────<br/>`;
          // 均线数据
          params.forEach(p => {
            if (p.seriesName && p.seriesName.includes('MA') && p.data !== null) {
              result += `${p.seriesName}: ${p.data.toFixed(2)}<br/>`;
            }
          });
          // 点击提示
          result += `<span style="color:#1890ff;font-size:12px">💡 点击查看分时图</span>`;
          return result;
        }
      },
      legend: {
        data: ['K线', 'MA5', 'MA10', 'MA20', '成交量'],
        top: 30
      },
      grid: [
        {
          left: '5%',
          right: '5%',
          top: '15%',
          height: '50%'
        },
        {
          left: '5%',
          right: '5%',
          top: '70%',
          height: '18%'
        }
      ],
      xAxis: [
        {
          type: 'category',
          data: dates,
          gridIndex: 0,
          axisLabel: {
            interval: Math.floor(dates.length / 10),
            formatter: function(value) {
              return value.substring(5); // 只显示MM-DD
            }
          },
          splitLine: {
            show: true,
            lineStyle: {
              color: '#f0f0f0'
            }
          }
        },
        {
          type: 'category',
          data: dates,
          gridIndex: 1,
          axisLabel: {
            show: false
          }
        }
      ],
      yAxis: [
        {
          type: 'value',
          gridIndex: 0,
          scale: true,
          splitLine: {
            lineStyle: {
              color: '#f0f0f0'
            }
          },
          axisLabel: {
            formatter: '{value}'
          }
        },
        {
          type: 'value',
          gridIndex: 1,
          splitLine: {
            show: false
          },
          axisLabel: {
            formatter: function(value) {
              return (value / 10000).toFixed(0) + '万';
            }
          }
        }
      ],
      dataZoom: [
        {
          type: 'inside',
          xAxisIndex: [0, 1],
          start: 0,
          end: 100
        },
        {
          show: true,
          xAxisIndex: [0, 1],
          type: 'slider',
          top: '90%',
          start: 0,
          end: 100
        }
      ],
      series: [
        {
          name: 'K线',
          type: 'candlestick',
          data: ohlcData,
          xAxisIndex: 0,
          yAxisIndex: 0,
          itemStyle: {
            color: '#f5222d',
            color0: '#52c41a',
            borderColor: '#f5222d',
            borderColor0: '#52c41a'
          }
        },
        {
          name: 'MA5',
          type: 'line',
          data: ma5,
          xAxisIndex: 0,
          yAxisIndex: 0,
          smooth: true,
          symbol: 'none',
          lineStyle: {
            color: '#1890ff',
            width: 1
          }
        },
        {
          name: 'MA10',
          type: 'line',
          data: ma10,
          xAxisIndex: 0,
          yAxisIndex: 0,
          smooth: true,
          symbol: 'none',
          lineStyle: {
            color: '#ff9800',
            width: 1
          }
        },
        {
          name: 'MA20',
          type: 'line',
          data: ma20,
          xAxisIndex: 0,
          yAxisIndex: 0,
          smooth: true,
          symbol: 'none',
          lineStyle: {
            color: '#9c27b0',
            width: 1
          }
        },
        {
          name: '成交量',
          type: 'bar',
          data: volumes,
          xAxisIndex: 1,
          yAxisIndex: 1,
          itemStyle: {
            color: function(params) {
              const dataIndex = params.dataIndex;
              if (dataIndex === 0) return '#f5222d';
              const current = ohlcData[dataIndex];
              const prev = ohlcData[dataIndex - 1];
              return current[1] >= prev[1] ? '#f5222d' : '#52c41a';
            }
          }
        }
      ]
    };

    chartInstance.current.setOption(option);

    // 点击事件：跳转到分时图
    if (onDateClick) {
      chartInstance.current.off('click');  // 先移除旧事件
      chartInstance.current.on('click', function(params) {
        if (params.componentType === 'series') {
          const dataIndex = params.dataIndex;
          const date = dates[dataIndex];
          if (date) {
            onDateClick(date);
          }
        }
      });
    }

    // 响应式调整
    const handleResize = () => {
      chartInstance.current?.resize();
    };
    window.addEventListener('resize', handleResize);

    // 清理函数：只移除事件监听，不销毁图表
    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, [data, stockCode, stockName, onDateClick]);

  // 组件卸载时销毁图表
  useEffect(() => {
    return () => {
      if (chartInstance.current) {
        chartInstance.current.dispose();
        chartInstance.current = null;
      }
    };
  }, []);

  // 计算移动平均线
  function calculateMA(data, dayCount) {
    const result = [];
    for (let i = 0; i < data.length; i++) {
      if (i < dayCount - 1) {
        result.push(null);
        continue;
      }
      let sum = 0;
      for (let j = 0; j < dayCount; j++) {
        sum += data[i - j];
      }
      result.push(sum / dayCount);
    }
    return result;
  }

  if (!data || data.length === 0) {
    return (
      <div style={{ 
        height: '600px', 
        display: 'flex', 
        alignments: 'center', 
        justifyContent: 'center',
        color: '#999'
      }}>
        暂无K线数据
      </div>
    );
  }

  return <div ref={chartRef} style={{ width: '100%', height: '600px' }} />;
};

export default DailyChart;
