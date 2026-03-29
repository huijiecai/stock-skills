import React, { useState, useEffect } from 'react';
import { Card, Table, Tag, Spin, DatePicker, Row, Col, Typography } from 'antd';
import { marketAPI } from '../services/api';
import dayjs from 'dayjs';

const { Title } = Typography;

const Ladder = () => {
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState(dayjs().format('YYYY-MM-DD'));
  const [ladder, setLadder] = useState([]);

  useEffect(() => {
    loadData();
  }, [date]);

  const loadData = async () => {
    setLoading(true);
    try {
      const res = await marketAPI.getContinuousBoard(date);
      if (res.code === 200) {
        setLadder(res.data.ladder || []);
      }
    } catch (error) {
      console.error('加载连板天梯失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const getColumns = (level) => [
    { 
      title: '代码', 
      dataIndex: 'stock_code', 
      width: 80,
      render: (v) => <a href={`/stock/${v}`}>{v}</a>
    },
    { title: '名称', dataIndex: 'stock_name', width: 100 },
    { 
      title: '涨幅', 
      dataIndex: 'change_pct', 
      width: 80,
      render: (v) => <Tag color="red">{v?.toFixed(2)}%</Tag>
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3} style={{ margin: 0 }}>连板天梯</Title>
        <DatePicker 
          value={dayjs(date)} 
          onChange={(d) => setDate(d.format('YYYY-MM-DD'))}
          style={{ width: 200 }}
        />
      </div>

      <Spin spinning={loading}>
        <Row gutter={[16, 16]}>
          {ladder.map((level) => (
            <Col span={24} key={level.limit_times}>
              <Card 
                title={
                  <span>
                    <Tag color={level.limit_times >= 5 ? 'gold' : level.limit_times >= 3 ? 'orange' : 'blue'}>
                      {level.level}
                    </Tag>
                    共 {level.count} 只
                  </span>
                }
                size="small"
              >
                <Table
                  columns={getColumns(level.level)}
                  dataSource={level.stocks}
                  rowKey="stock_code"
                  pagination={false}
                  size="small"
                  showHeader={false}
                />
              </Card>
            </Col>
          ))}
          {ladder.length === 0 && !loading && (
            <Col span={24}>
              <Card>
                <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
                  暂无连板数据
                </div>
              </Card>
            </Col>
          )}
        </Row>
      </Spin>
    </div>
  );
};

export default Ladder;
