import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Statistic, Table, Tag, Spin, DatePicker } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined, StockOutlined } from '@ant-design/icons';
import { marketAPI, indexAPI } from '../services/api';
import dayjs from 'dayjs';

const Dashboard = () => {
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState(dayjs().format('YYYY-MM-DD'));
  const [snapshot, setSnapshot] = useState(null);
  const [limitUpList, setLimitUpList] = useState([]);

  useEffect(() => {
    loadData();
  }, [date]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [snapshotRes, limitUpRes] = await Promise.all([
        marketAPI.getSnapshot(date),
        marketAPI.getLimitUp(date, 1, 10),
      ]);
      
      if (snapshotRes.code === 200) {
        setSnapshot(snapshotRes.data);
      }
      if (limitUpRes.code === 200) {
        setLimitUpList(limitUpRes.data.items || []);
      }
    } catch (error) {
      console.error('加载数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const columns = [
    { title: '代码', dataIndex: 'stock_code', width: 80 },
    { title: '名称', dataIndex: 'stock_name', width: 80 },
    { 
      title: '涨幅', 
      dataIndex: 'change_pct', 
      width: 80,
      render: (v) => <Tag color="red">{v?.toFixed(2)}%</Tag>
    },
    { title: '连板', dataIndex: 'limit_times', width: 60, render: (v) => `${v}板` },
    { title: '首封', dataIndex: 'first_time', width: 70 },
    { title: '炸板', dataIndex: 'open_times', width: 60 },
  ];

  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 16 }}>
        <DatePicker 
          value={dayjs(date)} 
          onChange={(d) => setDate(d.format('YYYY-MM-DD'))}
          style={{ width: 200 }}
        />
      </div>

      <Spin spinning={loading}>
        {/* 市场统计 */}
        <Row gutter={16} style={{ marginBottom: 24 }}>
          <Col span={4}>
            <Card>
              <Statistic
                title="涨停家数"
                value={snapshot?.limit_up_count || 0}
                valueStyle={{ color: '#cf1322' }}
                prefix={<ArrowUpOutlined />}
              />
            </Card>
          </Col>
          <Col span={4}>
            <Card>
              <Statistic
                title="跌停家数"
                value={snapshot?.limit_down_count || 0}
                valueStyle={{ color: '#3f8600' }}
                prefix={<ArrowDownOutlined />}
              />
            </Card>
          </Col>
          <Col span={4}>
            <Card>
              <Statistic
                title="炸板家数"
                value={snapshot?.broken_board_count || 0}
                valueStyle={{ color: '#faad14' }}
              />
            </Card>
          </Col>
          <Col span={4}>
            <Card>
              <Statistic
                title="封板率"
                value={snapshot?.seal_rate || 0}
                suffix="%"
                valueStyle={{ color: snapshot?.seal_rate >= 70 ? '#3f8600' : '#faad14' }}
              />
            </Card>
          </Col>
        </Row>

        {/* 指数行情 */}
        <Card title="主要指数" style={{ marginBottom: 24 }}>
          <Row gutter={16}>
            {(snapshot?.indices || []).map((idx) => (
              <Col span={6} key={idx.index_code}>
                <Statistic
                  title={idx.index_name}
                  value={idx.close}
                  precision={2}
                  valueStyle={{ color: idx.change_pct >= 0 ? '#cf1322' : '#3f8600' }}
                  suffix={`(${idx.change_pct >= 0 ? '+' : ''}${idx.change_pct?.toFixed(2)}%)`}
                />
              </Col>
            ))}
          </Row>
        </Card>

        {/* 涨停榜 */}
        <Card title="涨停股一览">
          <Table
            columns={columns}
            dataSource={limitUpList}
            rowKey="stock_code"
            pagination={false}
            size="small"
          />
        </Card>
      </Spin>
    </div>
  );
};

export default Dashboard;
