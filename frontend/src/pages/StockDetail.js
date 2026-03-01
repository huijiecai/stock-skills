import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Tabs, DatePicker, Card, Row, Col, Spin, message } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
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
      <div style={{ marginBottom: 12 }}>
        <Button 
          icon={<ArrowLeftOutlined />} 
          onClick={handleBack}
          size="small"
        >
          返回列表
        </Button>
      </div>

      {/* 顶部行情信息栏 - 紧凑布局 */}
      {quote && (
        <Card size="small" style={{ marginBottom: 12 }}>
          <Row gutter={[16, 8]} align="middle">
            {/* 左侧：股票名称和价格 */}
            <Col span={4}>
              <div style={{ fontWeight: 'bold', fontSize: 18 }}>
                {quote.name}
                <span style={{ fontSize: 12, color: '#999', marginLeft: 4 }}>({quote.code})</span>
              </div>
              <div style={{ fontSize: 28, fontWeight: 'bold', color: getPriceColor(quote.change), lineHeight: 1.2 }}>
                {quote.price?.toFixed(2)}
              </div>
              <div style={{ fontSize: 13, color: getPriceColor(quote.change) }}>
                {quote.change >= 0 ? '+' : ''}{quote.change?.toFixed(2)} 
                ({quote.change_percent >= 0 ? '+' : ''}{(quote.change_percent * 100)?.toFixed(2)}%)
              </div>
            </Col>
            
            {/* 右侧：关键指标 */}
            <Col span={20}>
              <Row gutter={[16, 4]}>
                <Col span={4}>
                  <div style={labelStyle}>开盘</div>
                  <div style={valueStyle}>{quote.open?.toFixed(2)}</div>
                </Col>
                <Col span={4}>
                  <div style={labelStyle}>最高</div>
                  <div style={{...valueStyle, color: '#f5222d'}}>{quote.high?.toFixed(2)}</div>
                </Col>
                <Col span={4}>
                  <div style={labelStyle}>最低</div>
                  <div style={{...valueStyle, color: '#52c41a'}}>{quote.low?.toFixed(2)}</div>
                </Col>
                <Col span={4}>
                  <div style={labelStyle}>昨收</div>
                  <div style={valueStyle}>{quote.prev_close?.toFixed(2)}</div>
                </Col>
                <Col span={4}>
                  <div style={labelStyle}>成交量</div>
                  <div style={valueStyle}>{quote.volume ? (quote.volume / 10000).toFixed(2) : '-'}<span style={unitStyle}>万手</span></div>
                </Col>
                <Col span={4}>
                  <div style={labelStyle}>成交额</div>
                  <div style={valueStyle}>{quote.turnover ? (quote.turnover / 100000000).toFixed(2) : '-'}<span style={unitStyle}>亿</span></div>
                </Col>
                <Col span={4}>
                  <div style={labelStyle}>换手率</div>
                  <div style={valueStyle}>{(quote.turnover_rate * 100)?.toFixed(2)}<span style={unitStyle}>%</span></div>
                </Col>
                <Col span={4}>
                  <div style={labelStyle}>实换率</div>
                  <div style={valueStyle}>{quote.turnover_rate_f ? (quote.turnover_rate_f * 100).toFixed(2) : '-'}<span style={unitStyle}>%</span></div>
                </Col>
                <Col span={4}>
                  <div style={labelStyle}>总市值</div>
                  <div style={valueStyle}>{quote.total_mv ? (quote.total_mv / 100000000).toFixed(2) : '-'}<span style={unitStyle}>亿</span></div>
                </Col>
                <Col span={4}>
                  <div style={labelStyle}>流通市值</div>
                  <div style={valueStyle}>{quote.circ_mv ? (quote.circ_mv / 100000000).toFixed(2) : '-'}<span style={unitStyle}>亿</span></div>
                </Col>
                <Col span={4}>
                  <div style={labelStyle}>PE(TTM)</div>
                  <div style={valueStyle}>{quote.pe_ttm?.toFixed(2) || '-'}</div>
                </Col>
                <Col span={4}>
                  <div style={labelStyle}>PB</div>
                  <div style={valueStyle}>{quote.pb?.toFixed(2) || '-'}</div>
                </Col>
              </Row>
            </Col>
          </Row>
        </Card>
      )}

      {/* 图表区域 */}
      <Card>
        <div style={{ marginBottom: 12 }}>
          {activeTab === 'intraday' && selectedDate && (
            <DatePicker 
              value={selectedDate}
              onChange={handleDateChange}
              format="YYYY-MM-DD"
              allowClear={false}
              size="small"
            />
          )}
        </div>
        <Tabs
          activeKey={activeTab}
          items={tabItems}
          onChange={handleTabChange}
          size="small"
        />
      </Card>
    </div>
  );
}

// 样式定义
const labelStyle = { 
  fontSize: 12, 
  color: '#999', 
  lineHeight: 1.2 
};

const valueStyle = { 
  fontSize: 14, 
  fontWeight: 500, 
  lineHeight: 1.4 
};

const unitStyle = { 
  fontSize: 11, 
  color: '#999', 
  marginLeft: 2 
};
