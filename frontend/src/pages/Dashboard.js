import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Statistic, Table, Tag, Spin } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined, FireOutlined } from '@ant-design/icons';
import { marketAPI, analysisAPI, stocksAPI } from '../services/api';
import dayjs from 'dayjs';

export default function Dashboard() {
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState(dayjs().format('YYYY-MM-DD'));
  const [marketData, setMarketData] = useState(null);
  const [leaders, setLeaders] = useState(null);
  const [popularity, setPopularity] = useState([]);

  useEffect(() => {
    loadData();
  }, [date]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [marketRes, leadersRes, popularityRes] = await Promise.all([
        marketAPI.getSentiment(date),
        analysisAPI.getLeaders(date),
        stocksAPI.getPopularity(date, 30),
      ]);
      
      setMarketData(marketRes.data.data);
      setLeaders(leadersRes.data);
      setPopularity(popularityRes.data.data);
    } catch (error) {
      console.error('加载数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const getPhaseColor = (phase) => {
    if (phase === '冰点') return 'blue';
    if (phase === '主升') return 'red';
    return 'default';
  };

  const popularityColumns = [
    {
      title: '排名',
      dataIndex: 'rank',
      key: 'rank',
      width: 60,
    },
    {
      title: '股票代码',
      dataIndex: 'stock_code',
      key: 'stock_code',
      width: 100,
    },
    {
      title: '股票名称',
      dataIndex: 'stock_name',
      key: 'stock_name',
      width: 120,
    },
    {
      title: '涨跌幅',
      dataIndex: 'change_percent',
      key: 'change_percent',
      width: 100,
      render: (value) => (
        <span style={{ color: value >= 0 ? '#cf1322' : '#3f8600' }}>
          {(value * 100).toFixed(2)}%
        </span>
      ),
    },
    {
      title: '成交额',
      dataIndex: 'turnover',
      key: 'turnover',
      render: (value) => `${(value / 100000000).toFixed(2)}亿`,
    },
  ];

  if (loading) {
    return <div style={{ textAlign: 'center', padding: '100px' }}><Spin size="large" /></div>;
  }

  return (
    <div>
      <h2>市场总览 - {date}</h2>
      
      {/* 市场情绪卡片 */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="市场阶段"
              value={marketData?.market_phase || '正常'}
              valueStyle={{ color: getPhaseColor(marketData?.market_phase) === 'red' ? '#cf1322' : '#3f8600' }}
              prefix={<Tag color={getPhaseColor(marketData?.market_phase)}>{marketData?.market_phase}</Tag>}
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
              title="最高连板"
              value={marketData?.max_streak || 0}
              prefix={<FireOutlined />}
              suffix="板"
            />
          </Card>
        </Col>
      </Row>

      {/* 人气榜 */}
      <Card title="人气榜 Top 30" style={{ marginBottom: 24 }}>
        <Table
          columns={popularityColumns}
          dataSource={popularity}
          rowKey="stock_code"
          pagination={false}
          size="small"
          scroll={{ y: 400 }}
        />
      </Card>

      {/* 概念龙头 */}
      {leaders?.concept_leaders && leaders.concept_leaders.length > 0 && (
        <Card title="概念龙头">
          <Row gutter={[16, 16]}>
            {leaders.concept_leaders.map((leader) => (
              <Col span={8} key={leader.concept_name}>
                <Card size="small">
                  <h4>{leader.concept_name}</h4>
                  <p>涨停：{leader.limit_up_count}家</p>
                  <p>领涨股：{leader.leader_name}</p>
                  <p>平均涨幅：{(leader.avg_change * 100).toFixed(2)}%</p>
                </Card>
              </Col>
            ))}
          </Row>
        </Card>
      )}
    </div>
  );
}
