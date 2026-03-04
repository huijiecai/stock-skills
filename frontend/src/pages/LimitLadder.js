import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Table, Tag, Spin, DatePicker, Space, Typography, message, Statistic, Badge, Tooltip } from 'antd';
import { TrophyOutlined, CalendarOutlined, LeftOutlined, RightOutlined, ReloadOutlined, RiseOutlined, FallOutlined } from '@ant-design/icons';
import { thsAPI } from '../services/api';
import dayjs from 'dayjs';

const { Title, Text } = Typography;

export default function LimitLadder() {
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState(dayjs().format('YYYY-MM-DD'));
  const [ladderData, setLadderData] = useState({ ladder: {}, stats: {} });

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date]);

  const loadData = async () => {
    setLoading(true);
    try {
      const res = await thsAPI.getLimitLadder(date);
      setLadderData(res.data || { ladder: {}, stats: {} });
    } catch (error) {
      console.error('加载连板天梯数据失败:', error);
      message.error('加载连板天梯数据失败，请重试');
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

  // 连板表格列配置
  const getColumns = (level) => [
    {
      title: '股票代码',
      dataIndex: 'ts_code',
      key: 'ts_code',
      width: 100,
      render: (code) => {
        const simpleCode = code?.split('.')[0];
        return <Text copyable style={{ fontFamily: 'monospace' }}>{simpleCode}</Text>;
      },
    },
    {
      title: '股票名称',
      dataIndex: 'ts_name',
      key: 'ts_name',
      width: 100,
      render: (name, record) => (
        <Space>
          <Text strong>{name}</Text>
          {record.status === '一字板' && <Tag color="red">一字</Tag>}
        </Space>
      ),
    },
    {
      title: '涨幅',
      dataIndex: 'pct_chg',
      key: 'pct_chg',
      width: 70,
      align: 'right',
      render: (pct) => {
        const num = parseFloat(pct) || 0;
        return <Text style={{ color: '#cf1322', fontWeight: 'bold' }}>{num.toFixed(2)}%</Text>;
      },
    },
    {
      title: '封单额',
      dataIndex: 'limit_order',
      key: 'limit_order',
      width: 90,
      align: 'right',
      render: (order) => {
        const num = parseFloat(order) || 0;
        if (num >= 100000000) return <Text>{(num / 100000000).toFixed(2)}亿</Text>;
        if (num >= 10000) return <Text>{(num / 10000).toFixed(0)}万</Text>;
        return <Text>{num.toFixed(0)}</Text>;
      },
    },
    {
      title: '首次封板',
      dataIndex: 'first_lu_time',
      key: 'first_lu_time',
      width: 80,
      render: (time) => {
        if (!time) return '-';
        const hour = parseInt(time.split(':')[0]);
        const minute = parseInt(time.split(':')[1]);
        const isEarly = hour < 10 || (hour === 10 && minute <= 30);
        return (
          <Text style={{ color: isEarly ? '#cf1322' : '#999' }}>
            {time?.substring(0, 5)}
          </Text>
        );
      },
      sorter: (a, b) => (a.first_lu_time || '99:99').localeCompare(b.first_lu_time || '99:99'),
    },
    {
      title: '开板次数',
      dataIndex: 'open_num',
      key: 'open_num',
      width: 80,
      align: 'center',
      render: (num) => {
        const n = parseInt(num) || 0;
        if (n === 0) return <Tag color="green">未开</Tag>;
        if (n <= 2) return <Tag color="orange">{n}次</Tag>;
        return <Tag color="red">{n}次</Tag>;
      },
    },
    {
      title: '涨停原因',
      dataIndex: 'lu_desc',
      key: 'lu_desc',
      ellipsis: true,
      render: (desc) => (
        <Tooltip title={desc}>
          <Text type="secondary" style={{ fontSize: 12 }}>{desc || '-'}</Text>
        </Tooltip>
      ),
    },
  ];

  // 获取连板等级列表（从高到低）
  const levels = Object.keys(ladderData.ladder || {})
    .map(Number)
    .sort((a, b) => b - a);

  // 获取等级标题颜色
  const getLevelColor = (level) => {
    if (level >= 7) return '#722ed1'; // 紫色
    if (level >= 5) return '#cf1322'; // 红色
    if (level >= 3) return '#fa8c16'; // 橙色
    if (level >= 2) return '#52c41a'; // 绿色
    return '#1890ff'; // 蓝色
  };

  // 获取等级标题
  const getLevelTitle = (level) => {
    if (level === 1) return '首板';
    return `${level}连板`;
  };

  return (
    <div style={{ padding: '24px' }}>
      <Card>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          {/* 标题和日期导航 */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Title level={3} style={{ margin: 0 }}>
              <TrophyOutlined style={{ color: '#faad14', marginRight: 8 }} />
              连板天梯
              <Badge count="同花顺" style={{ marginLeft: 8, backgroundColor: '#52c41a' }} />
            </Title>
            <Space>
              <LeftOutlined onClick={goToPreviousDay} style={{ cursor: 'pointer', fontSize: 16 }} />
              <DatePicker 
                value={dayjs(date)} 
                onChange={(d) => setDate(d.format('YYYY-MM-DD'))}
                allowClear={false}
              />
              <RightOutlined onClick={goToNextDay} style={{ cursor: 'pointer', fontSize: 16 }} />
              <CalendarOutlined onClick={goToToday} style={{ cursor: 'pointer', fontSize: 16, marginLeft: 8 }} />
              <ReloadOutlined onClick={loadData} style={{ cursor: 'pointer', fontSize: 16, marginLeft: 8 }} />
            </Space>
          </div>

          {/* 统计信息 */}
          <Row gutter={16}>
            <Col span={4}>
              <Card size="small" style={{ background: '#fff2f0' }}>
                <Statistic 
                  title={<Text style={{ color: '#cf1322' }}>涨停池</Text>}
                  value={ladderData.stats['涨停池'] || 0}
                  valueStyle={{ color: '#cf1322' }}
                  suffix="只"
                />
              </Card>
            </Col>
            <Col span={4}>
              <Card size="small" style={{ background: '#fff7e6' }}>
                <Statistic 
                  title={<Text style={{ color: '#fa8c16' }}>连扳池</Text>}
                  value={ladderData.stats['连扳池'] || 0}
                  valueStyle={{ color: '#fa8c16' }}
                  suffix="只"
                />
              </Card>
            </Col>
            <Col span={4}>
              <Card size="small" style={{ background: '#fff1f0' }}>
                <Statistic 
                  title={<Text style={{ color: '#ff4d4f' }}>炸板池</Text>}
                  value={ladderData.stats['炸板池'] || 0}
                  valueStyle={{ color: '#ff4d4f' }}
                  suffix="只"
                />
              </Card>
            </Col>
            <Col span={4}>
              <Card size="small" style={{ background: '#f6ffed' }}>
                <Statistic 
                  title={<Text style={{ color: '#52c41a' }}>跌停池</Text>}
                  value={ladderData.stats['跌停池'] || 0}
                  valueStyle={{ color: '#52c41a' }}
                  suffix="只"
                />
              </Card>
            </Col>
            <Col span={4}>
              <Card size="small">
                <Statistic 
                  title={<Text>最高连板</Text>}
                  value={levels[0] || 0}
                  suffix="板"
                  valueStyle={{ color: levels[0] >= 5 ? '#cf1322' : '#666' }}
                />
              </Card>
            </Col>
            <Col span={4}>
              <Card size="small">
                <Statistic 
                  title={<Text>连板股数</Text>}
                  value={Object.values(ladderData.ladder || {}).flat().length}
                  suffix="只"
                />
              </Card>
            </Col>
          </Row>

          {/* 连板天梯 */}
          <Spin spinning={loading}>
            {levels.length > 0 ? (
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                {levels.map(level => (
                  <Card 
                    key={level}
                    size="small"
                    title={
                      <Space>
                        <Tag color={getLevelColor(level)} style={{ fontSize: 14, padding: '2px 8px' }}>
                          {getLevelTitle(level)}
                        </Tag>
                        <Text type="secondary">
                          共 {ladderData.ladder[level].length} 只
                        </Text>
                      </Space>
                    }
                  >
                    <Table
                      dataSource={ladderData.ladder[level]}
                      columns={getColumns(level)}
                      rowKey="ts_code"
                      pagination={false}
                      size="small"
                      scroll={{ x: 800 }}
                    />
                  </Card>
                ))}
              </Space>
            ) : (
              <div style={{ textAlign: 'center', padding: '50px 0', color: '#999' }}>
                <Text>暂无连板数据，请确认已采集该日期的数据</Text>
              </div>
            )}
          </Spin>
        </Space>
      </Card>
    </div>
  );
}
