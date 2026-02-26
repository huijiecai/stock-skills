import React, { useEffect, useRef } from 'react';
import * as echarts from 'echarts';

/**
 * 分时图组件
 * @param {Object} props
 * @param {Array} props.data - 分时数据 [{trade_time, price, avg_price, change_percent, volume, turnover}]
 * @param {String} props.stockCode - 股票代码
 * @param {String} props.stockName - 股票名称
 * @param {String} props.date - 日期
 */
const IntradayChart = ({ data, stockCode, stockName, date }) => {
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

    // 处理数据
    const times = data.map(item => item.trade_time.substring(11, 16)); // HH:MM
    const prices = data.map(item => item.price);
    const avgPrices = data.map(item => item.avg_price);
    const volumes = data.map(item => item.volume);

    // 计算涨跌幅
    const firstPrice = prices[0]; // 开盘价（数据按时间升序）
    const currentPrice = prices[prices.length - 1]; // 最新价
    const changePercent = ((currentPrice - firstPrice) / firstPrice * 100).toFixed(2);
    const changeAmount = (currentPrice - firstPrice).toFixed(2);

    // 配置图表
    const option = {
      title: {
        text: `${stockName} (${stockCode})`,
        subtext: `${date} | ${currentPrice.toFixed(2)} 元 | ${changePercent > 0 ? '+' : ''}${changePercent}% (${changeAmount > 0 ? '+' : ''}${changeAmount})`,
        left: 'center',
        textStyle: {
          fontSize: 16,
          fontWeight: 'bold'
        },
        subtextStyle: {
          fontSize: 14,
          color: changePercent >= 0 ? '#ef5350' : '#26a69a'
        }
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'cross'
        },
        formatter: function(params) {
          let result = `时间: ${params[0].axisValue}<br/>`;
          params.forEach(item => {
            if (item.seriesName === '分时线') {
              const price = item.value;
              const percent = ((price - firstPrice) / firstPrice * 100).toFixed(2);
              result += `${item.marker}${item.seriesName}: ${price.toFixed(2)} 元 (${percent > 0 ? '+' : ''}${percent}%)<br/>`;
            } else if (item.seriesName === '均价线') {
              result += `${item.marker}${item.seriesName}: ${item.value.toFixed(2)} 元<br/>`;
            } else if (item.seriesName === '成交量') {
              result += `${item.marker}${item.seriesName}: ${(item.value / 10000).toFixed(2)} 万手<br/>`;
            }
          });
          return result;
        }
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
          data: times,
          gridIndex: 0,
          axisLabel: {
            interval: Math.floor(times.length / 6),
            formatter: function(value) {
              return value;
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
          data: times,
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
      series: [
        {
          name: '分时线',
          type: 'line',
          data: prices,
          xAxisIndex: 0,
          yAxisIndex: 0,
          smooth: false,
          symbol: 'none',
          lineStyle: {
            color: '#2196f3',
            width: 1
          },
          itemStyle: {
            color: '#2196f3'
          },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              {
                offset: 0,
                color: 'rgba(33, 150, 243, 0.3)'
              },
              {
                offset: 1,
                color: 'rgba(33, 150, 243, 0.05)'
              }
            ])
          }
        },
        {
          name: '均价线',
          type: 'line',
          data: avgPrices,
          xAxisIndex: 0,
          yAxisIndex: 0,
          smooth: false,
          symbol: 'none',
          lineStyle: {
            color: '#ff9800',
            width: 1
          },
          itemStyle: {
            color: '#ff9800'
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
              const idx = params.dataIndex;
              if (idx === 0) return '#ef5350';
              return prices[idx] >= prices[idx + 1] ? '#ef5350' : '#26a69a';
            }
          }
        }
      ]
    };

    chartInstance.current.setOption(option);

    // 响应式调整
    const handleResize = () => {
      chartInstance.current?.resize();
    };
    window.addEventListener('resize', handleResize);

    // 清理函数：只移除事件监听，不销毁图表
    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, [data, stockCode, stockName, date]);

  // 组件卸载时销毁图表
  useEffect(() => {
    return () => {
      if (chartInstance.current) {
        chartInstance.current.dispose();
        chartInstance.current = null;
      }
    };
  }, []);

  if (!data || data.length === 0) {
    return (
      <div style={{ 
        height: '500px', 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'center',
        color: '#999'
      }}>
        暂无分时数据
      </div>
    );
  }

  return <div ref={chartRef} style={{ width: '100%', height: '500px' }} />;
};

export default IntradayChart;
