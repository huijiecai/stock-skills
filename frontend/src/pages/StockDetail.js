import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Tabs, DatePicker, Card, Statistic, Row, Col, Spin, message } from 'antd';
import { ArrowLeftOutlined, ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { stocksAPI, marketAPI } from '../services/api';
import IntradayChart from '../components/IntradayChart';
import DailyChart from '../components/DailyChart';

export default function StockDetail() {
  const { code } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [quote, setQuote] = useState(null);
  const [activeTab, setActiveTab] = useState('intraday');
  const [selectedDate, setSelectedDate] = useState(null);  // 初始为 null，加载后设置
  const [intradayData, setIntradayData] = useState([]);
  const [dailyData, setDailyData] = useState([]);

  useEffect(() => {
    // 先加载最近交易日，再加载图表数据
    initPage();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code]);

  const initPage = async () => {
    try {
      // 获取最近交易日
      const res = await marketAPI.getLatestTradingDate();
      const latestDate = res.data.date || dayjs().format('YYYY-MM-DD');
      setSelectedDate(dayjs(latestDate));
      
      // 加载行情和图表数据
      loadQuote();
      loadChartData('intraday', dayjs(latestDate));
    } catch (error) {
      // 获取失败时使用当前日期
      setSelectedDate(dayjs());
      loadQuote();
      loadChartData('intraday', dayjs());
    }
  };

  useEffect(() => {
    if (selectedDate) {
      loadChartData(activeTab);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, selectedDate]);

  const loadQuote = async () => {
    try {
      const res = await stocksAPI.getQuote(code);
      setQuote(res.data.data);
    } catch (error) {
      message.error('加载行情数据失败');
    }
  };

  const loadChartData = async (tab, date = null) => {
    setLoading(true);
    const useDate = date || selectedDate;
    if (!useDate) {
      setLoading(false);
      return;
    }
    
    try {
      if (tab === 'intraday') {
        // 加载分时数据
        const res = await stocksAPI.getIntraday(code, useDate.format('YYYY-MM-DD'));
        setIntradayData(res.data.data || []);
      } else if (tab === 'daily') {
        // 加载日K线数据（最近1年）
        const endDate = dayjs().format('YYYY-MM-DD');
        const startDate = dayjs().subtract(1, 'year').format('YYYY-MM-DD');
        const res = await stocksAPI.getDaily(code, startDate, endDate);
        setDailyData(res.data.data || []);
      }
    } catch (error) {
      message.error('加载图表数据失败');
      if (tab === 'intraday') {
        setIntradayData([]);
      } else {
        setDailyData([]);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleTabChange = (key) => {
    setActiveTab(key);
  };

  const handleDateChange = (date) => {
    setSelectedDate(date);
  };

  const handleBack = () => {
    navigate('/stocks');
  };

  // 从K线图跳转到分时图
  const handleJumpToIntraday = (date) => {
    setSelectedDate(dayjs(date));
    setActiveTab('intraday');
  };

  // 渲染价格颜色
  const getPriceColor = (value) => {
    if (!value) return '#000';
    return value >= 0 ? '#f5222d' : '#52c41a';
  };

  const tabItems = [
    {
      key: 'intraday',
      label: '分时图',
      children: loading || !selectedDate ? (
        <div style={{ textAlign: 'center', padding: '100px' }}>
          <Spin size="large" />
        </div>
      ) : (
        <IntradayChart
          data={intradayData}
          stockCode={code}
          stockName={quote?.name || code}
          date={selectedDate.format('YYYY-MM-DD')}
        />
      ),
    },
    {
      key: 'daily',
      label: '日K线',
      children: loading ? (
        <div style={{ textAlign: 'center', padding: '100px' }}>
          <Spin size="large" />
        </div>
      ) : (
        <DailyChart
          data={dailyData}
          stockCode={code}
          stockName={quote?.name || code}
          onDateClick={handleJumpToIntraday}
        />
      ),
    },
    {
      key: 'info',
      label: '基本信息',
      children: (
        <div style={{ padding: '20px' }}>
          <Card title="股票信息">
            <p>功能开发中...</p>
          </Card>
        </div>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Button 
          icon={<ArrowLeftOutlined />} 
          onClick={handleBack}
        >
          返回列表
        </Button>
      </div>

      {/* 顶部行情信息栏 */}
      {quote && (
        <Card style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            <Col span={6}>
              <div>
                <div style={{ fontSize: 24, fontWeight: 'bold', marginBottom: 8 }}>
                  {quote.name}
                  <span style={{ fontSize: 14, color: '#999', marginLeft: 8 }}>
                    ({quote.code})
                  </span>
                </div>
                <div style={{ fontSize: 32, fontWeight: 'bold', color: getPriceColor(quote.change) }}>
                  {quote.price?.toFixed(2)}
                </div>
                <div style={{ fontSize: 16, color: getPriceColor(quote.change) }}>
                  {quote.change >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
                  {' '}
                  {quote.change >= 0 ? '+' : ''}{quote.change?.toFixed(2)}
                  {' '}
                  ({quote.change_percent >= 0 ? '+' : ''}{(quote.change_percent * 100)?.toFixed(2)}%)
                </div>
              </div>
            </Col>
            <Col span={18}>
              <Row gutter={16}>
                <Col span={6}>
                  <Statistic title="开盘" value={quote.open?.toFixed(2)} />
                </Col>
                <Col span={6}>
                  <Statistic title="最高" value={quote.high?.toFixed(2)} valueStyle={{ color: '#f5222d' }} />
                </Col>
                <Col span={6}>
                  <Statistic title="最低" value={quote.low?.toFixed(2)} valueStyle={{ color: '#52c41a' }} />
                </Col>
                <Col span={6}>
                  <Statistic title="昨收" value={quote.prev_close?.toFixed(2)} />
                </Col>
              </Row>
              <Row gutter={16} style={{ marginTop: 16 }}>
                <Col span={6}>
                  <Statistic 
                    title="成交量" 
                    value={quote.volume ? (quote.volume / 10000).toFixed(2) : '-'} 
                    suffix="万手"
                  />
                </Col>
                <Col span={6}>
                  <Statistic 
                    title="成交额" 
                    value={quote.turnover ? (quote.turnover / 100000000).toFixed(2) : '-'} 
                    suffix="亿"
                  />
                </Col>
                <Col span={6}>
                  <Statistic 
                    title="换手率" 
                    value={quote.turnover_rate?.toFixed(2)} 
                    suffix="%"
                  />
                </Col>
              </Row>
            </Col>
          </Row>
        </Card>
      )}

      {/* 图表区域 */}
      <Card>
        <div style={{ marginBottom: 16 }}>
          {activeTab === 'intraday' && selectedDate && (
            <DatePicker 
              value={selectedDate}
              onChange={handleDateChange}
              format="YYYY-MM-DD"
              allowClear={false}
            />
          )}
        </div>
        <Tabs
          activeKey={activeTab}
          items={tabItems}
          onChange={handleTabChange}
        />
      </Card>
    </div>
  );
}
