import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Statistic, Table, Tag, Spin, DatePicker, Space, Typography, Button, message } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined, FireOutlined, CalendarOutlined, LeftOutlined, RightOutlined, ReloadOutlined } from '@ant-design/icons';
import { marketAPI, simulationAPI, stockAPI } from '../services/api';
import dayjs from 'dayjs';

const { Title, Text } = Typography;

export default function Dashboard() {
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState(dayjs().format('YYYY-MM-DD'));
  const [marketData, setMarketData] = useState(null);
  const [hotStocks, setHotStocks] = useState([]);

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [snapshotRes, hotStocksRes] = await Promise.all([
        marketAPI.getSnapshot(date),
        simulationAPI.getHotStocks(date, 30),
      ]);
      
      if (snapshotRes.code === 200) {
        setMarketData(snapshotRes.data);
      }
      
      if (hotStocksRes.code === 200) {
        setHotStocks(hotStocksRes.data.items || []);
      }
    } catch (error) {
      console.error('加载数据失败:', error);
      message.error('加载数据失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  // 日期导航
  const goToPreviousDay = () => {
    const prevDay = dayjs(date).subtract(1, 'day');
    setDate(prevDay.format('YYYY-MM-DD'));
  };

  const goToNextDay = () => {
    const nextDay = dayjs(date).add(1, 'day');
    if (nextDay.isAfter(dayjs(), 'day')) {
      message.warning('不能选择未来日期');
      return;
    }
    setDate(nextDay.format('YYYY-MM-DD'));
  };

  const goToToday = () => {
    setDate(dayjs().format('YYYY-MM-DD'));
  };

  const getPhaseColor = (phase) => {
    if (phase === '冰点') return 'blue';
    if (phase === '主升') return 'red';
    return 'default';
  };

  // 根据涨停家数判断市场阶段
  const getMarketPhase = () => {
    const upCount = marketData?.limit_up_count || 0;
    if (upCount > 50) return '主升';
    if (upCount < 10) return '冰点';
    return '正常';
  };

  const hotStocksColumns = [
    {
      title: '排名',
      dataIndex: 'rank',
      key: 'rank',
      width: 60,
      fixed: 'left',
      render: (rank) => {
        let color = '#999';
        if (rank === 1) color = '#cf1322';
        else if (rank === 2) color = '#fa8c16';
        else if (rank === 3) color = '#faad14';
        return <Tag color={color} style={{ fontWeight: 'bold' }}>{rank}</Tag>;
      },
    },
    {
      title: '股票代码',
      dataIndex: 'stock_code',
      key: 'stock_code',
      width: 100,
      render: (code) => <Text copyable style={{ fontFamily: 'monospace' }}>{code}</Text>,
    },
    {
      title: '股票名称',
      dataIndex: 'stock_name',
      key: 'stock_name',
      width: 120,
      render: (name) => <Text strong>{name || '-'}</Text>,
    },
    {
      title: '涨跌幅',
      dataIndex: 'change_pct',
      key: 'change_pct',
      width: 100,
      align: 'right',
      render: (value) => (
        <span style={{ 
          color: value >= 0 ? '#cf1322' : '#3f8600',
          fontWeight: 'bold',
          fontSize: '14px'
        }}>
          {value >= 0 ? '+' : ''}{(value || 0).toFixed(2)}%
        </span>
      ),
      sorter: (a, b) => (a.change_pct || 0) - (b.change_pct || 0),
    },
    {
      title: '成交额',
      dataIndex: 'amount',
      key: 'amount',
      width: 120,
      align: 'right',
      render: (value) => (
        <Text>{((value || 0) / 100000000).toFixed(2)}亿</Text>
      ),
      sorter: (a, b) => (a.amount || 0) - (b.amount || 0),
    },
  ];

  if (loading) {
    return <div style={{ textAlign: 'center', padding: '100px' }}><Spin size="large" /></div>;
  }

  return (
    <div>
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={2} style={{ margin: 0 }}>
          <CalendarOutlined style={{ marginRight: 8 }} />
          市场总览
        </Title>
        <Space size="middle">
          <Button.Group>
            <Button icon={<LeftOutlined />} onClick={goToPreviousDay}>
              上一天
            </Button>
            <Button onClick={goToToday}>
              今天
            </Button>
            <Button 
              icon={<RightOutlined />} 
              onClick={goToNextDay}
              disabled={dayjs(date).isSame(dayjs(), 'day')}
            >
              下一天
            </Button>
          </Button.Group>
          <DatePicker
            value={dayjs(date)}
            onChange={(dateObj) => {
              if (dateObj) {
                setDate(dateObj.format('YYYY-MM-DD'));
              }
            }}
            format="YYYY-MM-DD"
            placeholder="选择日期"
            allowClear={false}
            disabledDate={(current) => {
              return current && current > dayjs().endOf('day');
            }}
          />
          <Button icon={<ReloadOutlined />} onClick={loadData} loading={loading}>
            刷新
          </Button>
        </Space>
      </div>

      <Card style={{ marginBottom: 16, background: '#f0f2f5', borderLeft: '4px solid #1890ff' }}>
        <div style={{ textAlign: 'center' }}>
          <Space size="large">
            <Title level={4} style={{ margin: 0, color: '#1890ff' }}>
              {dayjs(date).format('YYYY年MM月DD日')}
            </Title>
            {date === dayjs().format('YYYY-MM-DD') && (
              <Tag color="green" style={{ fontSize: 14, padding: '4px 12px' }}>
                今日
              </Tag>
            )}
            <Text type="secondary">{dayjs(date).format('dddd')}</Text>
          </Space>
        </div>
      </Card>
      
      {/* 市场情绪卡片 */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="市场阶段"
              value={getMarketPhase()}
              valueStyle={{ color: getPhaseColor(getMarketPhase()) === 'red' ? '#cf1322' : '#3f8600' }}
              prefix={<Tag color={getPhaseColor(getMarketPhase())}>{getMarketPhase()}</Tag>}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="涨停家数"
              value={marketData?.limit_up_count || 0}
              prefix={<ArrowUpOutlined />}
              valueStyle={{ color: '#cf1322' }}
              suffix="家"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="跌停家数"
              value={marketData?.limit_down_count || 0}
              prefix={<ArrowDownOutlined />}
              valueStyle={{ color: '#3f8600' }}
              suffix="家"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="封板率"
              value={marketData?.seal_rate || 0}
              prefix={<FireOutlined />}
              suffix="%"
            />
          </Card>
        </Col>
      </Row>

      {/* 热门个股 */}
      <Card 
        title={
          <Space>
            <FireOutlined style={{ color: '#fa541c' }} />
            <span>热门个股 Top 30</span>
            <Tag color="orange">{hotStocks.length}只</Tag>
          </Space>
        } 
        style={{ marginBottom: 24 }}
      >
        <Table
          columns={hotStocksColumns}
          dataSource={hotStocks}
          rowKey="stock_code"
          pagination={false}
          size="small"
          scroll={{ y: 400 }}
        />
      </Card>
    </div>
  );
}
