import React, { useState, useEffect } from 'react';
import { Card, Table, Tag, Spin, DatePicker, Space, Typography, message, Input, Tooltip, Badge } from 'antd';
import { FireOutlined, CalendarOutlined, LeftOutlined, RightOutlined, ReloadOutlined, SearchOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { thsAPI } from '../services/api';
import dayjs from 'dayjs';

const { Title, Text } = Typography;
const { Search } = Input;

export default function HotRank() {
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState(dayjs().format('YYYY-MM-DD'));
  const [hotRank, setHotRank] = useState([]);
  const [searchText, setSearchText] = useState('');

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date]);

  const loadData = async () => {
    setLoading(true);
    try {
      const res = await thsAPI.getHotRank(date, null, 100);
      setHotRank(res.data || []);
    } catch (error) {
      console.error('加载热榜数据失败:', error);
      message.error('加载热榜数据失败，请重试');
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

  // 过滤数据
  const filteredData = hotRank.filter(item => 
    !searchText || 
    item.ts_name?.toLowerCase().includes(searchText.toLowerCase()) ||
    item.ts_code?.toLowerCase().includes(searchText.toLowerCase()) ||
    item.concept?.toLowerCase().includes(searchText.toLowerCase())
  );

  const columns = [
    {
      title: '排名',
      dataIndex: 'rank',
      key: 'rank',
      width: 70,
      fixed: 'left',
      render: (rank) => {
        let color = '#999';
        let bgColor = '#f5f5f5';
        if (rank === 1) { color = '#fff'; bgColor = '#cf1322'; }
        else if (rank === 2) { color = '#fff'; bgColor = '#fa8c16'; }
        else if (rank === 3) { color = '#fff'; bgColor = '#faad14'; }
        else if (rank <= 10) { color = '#cf1322'; bgColor = '#fff1f0'; }
        else if (rank <= 30) { color = '#fa8c16'; bgColor = '#fff7e6'; }
        return (
          <Tag color={bgColor} style={{ color, fontWeight: 'bold', border: 'none' }}>
            {rank}
          </Tag>
        );
      },
    },
    {
      title: '股票代码',
      dataIndex: 'ts_code',
      key: 'ts_code',
      width: 110,
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
      render: (name) => <Text strong>{name}</Text>,
    },
    {
      title: '热度值',
      dataIndex: 'hot',
      key: 'hot',
      width: 100,
      align: 'right',
      render: (hot) => {
        const hotNum = parseFloat(hot) || 0;
        let color = '#999';
        if (hotNum > 100000) color = '#cf1322';
        else if (hotNum > 50000) color = '#fa8c16';
        else if (hotNum > 20000) color = '#52c41a';
        return <Text style={{ color, fontWeight: 'bold' }}>{hotNum.toLocaleString()}</Text>;
      },
      sorter: (a, b) => (parseFloat(a.hot) || 0) - (parseFloat(b.hot) || 0),
      defaultSortOrder: 'descend',
    },
    {
      title: '涨跌幅',
      dataIndex: 'pct_change',
      key: 'pct_change',
      width: 90,
      align: 'right',
      render: (pct) => {
        const num = parseFloat(pct) || 0;
        const color = num >= 0 ? '#cf1322' : '#52c41a';
        const icon = num >= 0 ? '↑' : '↓';
        return (
          <Text style={{ color, fontWeight: 'bold' }}>
            {icon} {num.toFixed(2)}%
          </Text>
        );
      },
      sorter: (a, b) => (parseFloat(a.pct_change) || 0) - (parseFloat(b.pct_change) || 0),
    },
    {
      title: '现价',
      dataIndex: 'current_price',
      key: 'current_price',
      width: 80,
      align: 'right',
      render: (price) => <Text>{parseFloat(price || 0).toFixed(2)}</Text>,
    },
    {
      title: '概念标签',
      dataIndex: 'concept',
      key: 'concept',
      width: 200,
      render: (concept) => {
        if (!concept) return '-';
        let concepts = [];
        try {
          concepts = JSON.parse(concept.replace(/'/g, '"'));
        } catch {
          concepts = [concept];
        }
        return (
          <Space size={[0, 4]} wrap>
            {concepts.slice(0, 3).map((c, i) => (
              <Tag key={i} color="blue" style={{ margin: 0 }}>{c}</Tag>
            ))}
            {concepts.length > 3 && (
              <Tooltip title={concepts.slice(3).join(', ')}>
                <Tag color="default">+{concepts.length - 3}</Tag>
              </Tooltip>
            )}
          </Space>
        );
      },
    },
    {
      title: '上榜解读',
      dataIndex: 'rank_reason',
      key: 'rank_reason',
      ellipsis: true,
      render: (reason) => (
        <Tooltip title={reason}>
          <Text type="secondary">{reason || '-'}</Text>
        </Tooltip>
      ),
    },
  ];

  return (
    <div style={{ padding: '24px' }}>
      <Card>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          {/* 标题和日期导航 */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Title level={3} style={{ margin: 0 }}>
              <FireOutlined style={{ color: '#cf1322', marginRight: 8 }} />
              个股热榜
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

          {/* 搜索框 */}
          <Search
            placeholder="搜索股票名称、代码或概念..."
            allowClear
            enterButton={<SearchOutlined />}
            style={{ width: 300 }}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />

          {/* 统计信息 */}
          <Space>
            <Text type="secondary">
              共 <Text strong>{hotRank.length}</Text> 只股票上榜
            </Text>
            <Text type="secondary">|</Text>
            <Text type="secondary">
              涨停 <Text strong style={{ color: '#cf1322' }}>{hotRank.filter(s => parseFloat(s.pct_change) >= 9.5).length}</Text> 只
            </Text>
            <Text type="secondary">|</Text>
            <Text type="secondary">
              下跌 <Text strong style={{ color: '#52c41a' }}>{hotRank.filter(s => parseFloat(s.pct_change) < 0).length}</Text> 只
            </Text>
          </Space>

          {/* 表格 */}
          <Spin spinning={loading}>
            <Table
              dataSource={filteredData}
              columns={columns}
              rowKey="ts_code"
              scroll={{ x: 1000 }}
              pagination={{
                pageSize: 30,
                showSizeChanger: true,
                showTotal: (total) => `共 ${total} 条`,
              }}
              size="small"
            />
          </Spin>
        </Space>
      </Card>
    </div>
  );
}
