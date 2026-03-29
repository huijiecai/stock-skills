import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Tabs, DatePicker, Card, Row, Col, Spin, message, Typography } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { stockAPI } from '../services/api';
import IntradayChart from '../components/IntradayChart';
import DailyChart from '../components/DailyChart';

const { Text } = Typography;

export default function StockDetail() {
  const { code } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [stockInfo, setStockInfo] = useState(null);
  const [activeTab, setActiveTab] = useState('intraday');
  const [selectedDate, setSelectedDate] = useState(dayjs());
  const [intradayData, setIntradayData] = useState([]);
  const [dailyData, setDailyData] = useState([]);

  useEffect(() => {
    loadStockInfo();
    loadDailyData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code]);

  useEffect(() => {
    if (selectedDate) {
      loadIntradayData();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDate]);

  const loadStockInfo = async () => {
    try {
      const res = await stockAPI.getInfo(code);
      if (res.code === 200) {
        setStockInfo(res.data);
      }
    } catch (error) {
      message.error('加载股票信息失败');
    }
  };

  const loadIntradayData = async () => {
    setLoading(true);
    try {
      const res = await stockAPI.getIntraday(code, selectedDate.format('YYYY-MM-DD'));
      if (res.code === 200) {
        setIntradayData(res.data.items || []);
      }
    } catch (error) {
      setIntradayData([]);
    } finally {
      setLoading(false);
    }
  };

  const loadDailyData = async () => {
    try {
      const endDate = dayjs().format('YYYY-MM-DD');
      const startDate = dayjs().subtract(1, 'year').format('YYYY-MM-DD');
      const res = await stockAPI.getDaily(code, startDate, endDate);
      if (res.code === 200) {
        setDailyData(res.data.items || []);
      }
    } catch (error) {
      setDailyData([]);
    }
  };

  const handleTabChange = (key) => {
    setActiveTab(key);
  };

  const handleDateChange = (date) => {
    setSelectedDate(date);
  };

  const handleBack = () => {
    navigate(-1);
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
      children: loading ? (
        <div style={{ textAlign: 'center', padding: '100px' }}>
          <Spin size="large" />
        </div>
      ) : (
        <IntradayChart
          data={intradayData}
          stockCode={code}
          stockName={stockInfo?.stock_name || code}
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
          stockName={stockInfo?.stock_name || code}
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
            {stockInfo ? (
              <Row gutter={[16, 8]}>
                <Col span={8}><Text strong>股票代码：</Text><Text>{stockInfo.stock_code}</Text></Col>
                <Col span={8}><Text strong>股票名称：</Text><Text>{stockInfo.stock_name}</Text></Col>
                <Col span={8}><Text strong>所属行业：</Text><Text>{stockInfo.industry || '-'}</Text></Col>
                <Col span={8}><Text strong>上市日期：</Text><Text>{stockInfo.list_date || '-'}</Text></Col>
                <Col span={8}><Text strong>市场：</Text><Text>{stockInfo.market || '-'}</Text></Col>
              </Row>
            ) : (
              <Spin />
            )}
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
          返回
        </Button>
      </div>

      {/* 顶部股票信息栏 */}
      {stockInfo && (
        <Card size="small" style={{ marginBottom: 12 }}>
          <Row gutter={16} align="middle">
            <Col>
              <div style={{ fontWeight: 'bold', fontSize: 18 }}>
                {stockInfo.stock_name}
                <span style={{ fontSize: 12, color: '#999', marginLeft: 4 }}>({stockInfo.stock_code})</span>
              </div>
              <div style={{ color: '#999', fontSize: 12 }}>
                {stockInfo.industry || '-'} | {stockInfo.market || '-'}
              </div>
            </Col>
          </Row>
        </Card>
      )}

      {/* 图表区域 */}
      <Card>
        <div style={{ marginBottom: 12 }}>
          {activeTab === 'intraday' && (
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
