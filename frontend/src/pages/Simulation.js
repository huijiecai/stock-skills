import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Statistic, Table, Tag, Spin, DatePicker, Typography, Tabs } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import { simulationAPI } from '../services/api';
import dayjs from 'dayjs';

const { Title } = Typography;
const { TabPane } = Tabs;

const Simulation = () => {
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState(dayjs().format('YYYY-MM-DD'));
  const [overview, setOverview] = useState(null);
  const [hotStocks, setHotStocks] = useState([]);
  const [capitalIn, setCapitalIn] = useState([]);
  const [capitalOut, setCapitalOut] = useState([]);

  useEffect(() => {
    loadData();
  }, [date]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [overviewRes, hotRes, inRes, outRes] = await Promise.all([
        simulationAPI.getMarketOverview(date),
        simulationAPI.getHotStocks(date, 20),
        simulationAPI.getCapitalFlowRank(date, 'in', 10),
        simulationAPI.getCapitalFlowRank(date, 'out', 10),
      ]);
      
      if (overviewRes.code === 200) setOverview(overviewRes.data);
      if (hotRes.code === 200) setHotStocks(hotRes.data.items || []);
      if (inRes.code === 200) setCapitalIn(inRes.data.items || []);
      if (outRes.code === 200) setCapitalOut(outRes.data.items || []);
    } catch (error) {
      console.error('加载数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const hotColumns = [
    { title: '排名', dataIndex: 'rank', width: 60 },
    { title: '代码', dataIndex: 'stock_code', width: 80 },
    { title: '名称', dataIndex: 'stock_name', width: 100 },
    { 
      title: '涨幅', 
      dataIndex: 'change_pct', 
      width: 80,
      render: (v) => <Tag color={v >= 0 ? 'red' : 'green'}>{v?.toFixed(2)}%</Tag>
    },
    { 
      title: '成交额', 
      dataIndex: 'amount', 
      width: 100,
      render: (v) => v > 100000000 ? `${(v / 100000000).toFixed(2)}亿` : `${(v / 10000).toFixed(0)}万`
    },
  ];

  const capitalColumns = [
    { title: '排名', dataIndex: 'rank', width: 60 },
    { title: '代码', dataIndex: 'stock_code', width: 80 },
    { title: '名称', dataIndex: 'stock_name', width: 100 },
    { 
      title: '涨幅', 
      dataIndex: 'change_pct', 
      width: 80,
      render: (v) => <Tag color={v >= 0 ? 'red' : 'green'}>{v?.toFixed(2)}%</Tag>
    },
    { 
      title: '主力净流入', 
      dataIndex: 'main_net_inflow', 
      width: 120,
      render: (v) => (
        <span style={{ color: v >= 0 ? 'red' : 'green' }}>
          {v > 0 ? '+' : ''}{(v / 100000000).toFixed(2)}亿
        </span>
      )
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3} style={{ margin: 0 }}>模拟看盘</Title>
        <DatePicker 
          value={dayjs(date)} 
          onChange={(d) => setDate(d.format('YYYY-MM-DD'))}
          style={{ width: 200 }}
        />
      </div>

      <Spin spinning={loading}>
        {/* 市场概览 */}
        <Card title="市场情绪" style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            <Col span={4}>
              <Statistic
                title="涨停家数"
                value={overview?.market_sentiment?.limit_up_count || 0}
                valueStyle={{ color: '#cf1322' }}
                prefix={<ArrowUpOutlined />}
              />
            </Col>
            <Col span={4}>
              <Statistic
                title="跌停家数"
                value={overview?.market_sentiment?.limit_down_count || 0}
                valueStyle={{ color: '#3f8600' }}
                prefix={<ArrowDownOutlined />}
              />
            </Col>
            <Col span={4}>
              <Statistic
                title="炸板家数"
                value={overview?.market_sentiment?.broken_board_count || 0}
                valueStyle={{ color: '#faad14' }}
              />
            </Col>
            <Col span={4}>
              <Statistic
                title="封板率"
                value={overview?.market_sentiment?.seal_rate || 0}
                suffix="%"
              />
            </Col>
          </Row>
        </Card>

        {/* 主要指数 */}
        <Card title="主要指数" style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            {(overview?.indices || []).map((idx) => (
              <Col span={6} key={idx.code}>
                <Statistic
                  title={idx.name}
                  value={idx.price}
                  precision={2}
                  valueStyle={{ color: idx.change_pct >= 0 ? '#cf1322' : '#3f8600' }}
                  suffix={`(${idx.change_pct >= 0 ? '+' : ''}${idx.change_pct?.toFixed(2)}%)`}
                />
              </Col>
            ))}
          </Row>
        </Card>

        {/* 热门板块 */}
        <Card title="热门板块" style={{ marginBottom: 16 }}>
          <Row gutter={[8, 8]}>
            {(overview?.hot_concepts || []).map((concept) => (
              <Col key={concept.code}>
                <Tag color={concept.change_pct >= 0 ? 'red' : 'green'}>
                  {concept.name} {concept.change_pct >= 0 ? '+' : ''}{concept.change_pct?.toFixed(2)}%
                </Tag>
              </Col>
            ))}
          </Row>
        </Card>

        <Tabs defaultActiveKey="hot">
          <TabPane tab="成交额排行" key="hot">
            <Table
              columns={hotColumns}
              dataSource={hotStocks}
              rowKey="stock_code"
              pagination={false}
              size="small"
            />
          </TabPane>
          <TabPane tab="主力流入" key="in">
            <Table
              columns={capitalColumns}
              dataSource={capitalIn}
              rowKey="stock_code"
              pagination={false}
              size="small"
            />
          </TabPane>
          <TabPane tab="主力流出" key="out">
            <Table
              columns={capitalColumns}
              dataSource={capitalOut}
              rowKey="stock_code"
              pagination={false}
              size="small"
            />
          </TabPane>
        </Tabs>
      </Spin>
    </div>
  );
};

export default Simulation;
