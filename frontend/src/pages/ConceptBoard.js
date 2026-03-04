import React, { useState, useEffect } from 'react';
import { Card, Table, Tag, Spin, DatePicker, Space, Typography, message, Input, Modal, Drawer, Badge, Tooltip, Row, Col, Statistic } from 'antd';
import { AppstoreOutlined, CalendarOutlined, LeftOutlined, RightOutlined, ReloadOutlined, SearchOutlined, TeamOutlined, LineChartOutlined, RiseOutlined, FallOutlined } from '@ant-design/icons';
import { thsAPI } from '../services/api';
import dayjs from 'dayjs';

const { Title, Text } = Typography;
const { Search } = Input;

export default function ConceptBoard() {
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState(dayjs().format('YYYY-MM-DD'));
  const [concepts, setConcepts] = useState([]);
  const [conceptDaily, setConceptDaily] = useState([]);
  const [searchText, setSearchText] = useState('');
  
  // 概念详情抽屉
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [selectedConcept, setSelectedConcept] = useState(null);
  const [members, setMembers] = useState([]);
  const [membersLoading, setMembersLoading] = useState(false);

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date]);

  const loadData = async () => {
    setLoading(true);
    try {
      // 加载概念日行情
      const dailyRes = await thsAPI.getConceptDaily({ trade_date: date, limit: 200 });
      setConceptDaily(dailyRes.data || []);
      
      // 加载概念列表（如果日行情为空）
      if (!dailyRes.data || dailyRes.data.length === 0) {
        const conceptsRes = await thsAPI.getConcepts(null, 200);
        setConcepts(conceptsRes.data || []);
      }
    } catch (error) {
      console.error('加载概念数据失败:', error);
      message.error('加载概念数据失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  // 加载概念成分股
  const loadMembers = async (conceptCode) => {
    setMembersLoading(true);
    try {
      const res = await thsAPI.getConceptMembers(conceptCode);
      setMembers(res.data || []);
    } catch (error) {
      console.error('加载成分股失败:', error);
      message.error('加载成分股失败');
    } finally {
      setMembersLoading(false);
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

  // 查看概念详情
  const showConceptDetail = (concept) => {
    setSelectedConcept(concept);
    setDrawerVisible(true);
    loadMembers(concept.concept_code || concept.ts_code);
  };

  // 过滤数据
  const filteredData = conceptDaily.length > 0 
    ? conceptDaily.filter(item => 
        !searchText || 
        item.concept_name?.toLowerCase().includes(searchText.toLowerCase()) ||
        item.concept_code?.toLowerCase().includes(searchText.toLowerCase())
      )
    : concepts.filter(item => 
        !searchText || 
        item.name?.toLowerCase().includes(searchText.toLowerCase()) ||
        item.ts_code?.toLowerCase().includes(searchText.toLowerCase())
      );

  // 概念日行情列配置
  const dailyColumns = [
    {
      title: '排名',
      key: 'rank',
      width: 60,
      render: (_, __, index) => {
        const color = index < 3 ? '#cf1322' : index < 10 ? '#fa8c16' : '#999';
        return <Tag color={color}>{index + 1}</Tag>;
      },
    },
    {
      title: '概念名称',
      dataIndex: 'concept_name',
      key: 'concept_name',
      width: 150,
      render: (name, record) => (
        <a onClick={() => showConceptDetail(record)}>
          <Text strong>{name}</Text>
        </a>
      ),
    },
    {
      title: '概念代码',
      dataIndex: 'concept_code',
      key: 'concept_code',
      width: 110,
      render: (code) => <Text copyable style={{ fontFamily: 'monospace' }}>{code}</Text>,
    },
    {
      title: '涨跌幅',
      dataIndex: 'pct_change',
      key: 'pct_change',
      width: 90,
      align: 'right',
      sorter: (a, b) => (parseFloat(a.pct_change) || 0) - (parseFloat(b.pct_change) || 0),
      defaultSortOrder: 'descend',
      render: (pct) => {
        const num = parseFloat(pct) || 0;
        const color = num >= 0 ? '#cf1322' : '#52c41a';
        return <Text style={{ color, fontWeight: 'bold' }}>{num >= 0 ? '+' : ''}{num.toFixed(2)}%</Text>;
      },
    },
    {
      title: '开盘',
      dataIndex: 'open',
      key: 'open',
      width: 80,
      align: 'right',
      render: (val) => parseFloat(val || 0).toFixed(2),
    },
    {
      title: '收盘',
      dataIndex: 'close',
      key: 'close',
      width: 80,
      align: 'right',
      render: (val) => parseFloat(val || 0).toFixed(2),
    },
    {
      title: '最高',
      dataIndex: 'high',
      key: 'high',
      width: 80,
      align: 'right',
      render: (val) => parseFloat(val || 0).toFixed(2),
    },
    {
      title: '最低',
      dataIndex: 'low',
      key: 'low',
      width: 80,
      align: 'right',
      render: (val) => parseFloat(val || 0).toFixed(2),
    },
    {
      title: '换手率',
      dataIndex: 'turnover_rate',
      key: 'turnover_rate',
      width: 80,
      align: 'right',
      render: (rate) => `${parseFloat(rate || 0).toFixed(2)}%`,
    },
    {
      title: '总市值',
      dataIndex: 'total_mv',
      key: 'total_mv',
      width: 90,
      align: 'right',
      render: (mv) => {
        const num = parseFloat(mv) || 0;
        return <Text>{num.toFixed(0)}亿</Text>;
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_, record) => (
        <Space>
          <Tooltip title="查看成分股">
            <TeamOutlined 
              onClick={() => showConceptDetail(record)}
              style={{ cursor: 'pointer', color: '#1890ff' }}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  // 概念列表列配置
  const conceptColumns = [
    {
      title: '概念名称',
      dataIndex: 'name',
      key: 'name',
      width: 200,
      render: (name, record) => (
        <a onClick={() => showConceptDetail(record)}>
          <Text strong>{name}</Text>
        </a>
      ),
    },
    {
      title: '概念代码',
      dataIndex: 'ts_code',
      key: 'ts_code',
      width: 120,
      render: (code) => <Text copyable style={{ fontFamily: 'monospace' }}>{code}</Text>,
    },
    {
      title: '成分股数量',
      dataIndex: 'component_count',
      key: 'component_count',
      width: 100,
      align: 'right',
      sorter: (a, b) => (a.component_count || 0) - (b.component_count || 0),
    },
    {
      title: '发布日期',
      dataIndex: 'list_date',
      key: 'list_date',
      width: 100,
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_, record) => (
        <TeamOutlined 
          onClick={() => showConceptDetail(record)}
          style={{ cursor: 'pointer', color: '#1890ff' }}
        />
      ),
    },
  ];

  // 成分股列配置
  const memberColumns = [
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
      render: (name) => <Text strong>{name}</Text>,
    },
  ];

  // 统计信息
  const upCount = conceptDaily.filter(c => parseFloat(c.pct_change) > 0).length;
  const downCount = conceptDaily.filter(c => parseFloat(c.pct_change) < 0).length;
  const avgChange = conceptDaily.length > 0 
    ? conceptDaily.reduce((sum, c) => sum + (parseFloat(c.pct_change) || 0), 0) / conceptDaily.length 
    : 0;

  return (
    <div style={{ padding: '24px' }}>
      <Card>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          {/* 标题和日期导航 */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Title level={3} style={{ margin: 0 }}>
              <AppstoreOutlined style={{ color: '#1890ff', marginRight: 8 }} />
              概念板块
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
          {conceptDaily.length > 0 && (
            <Row gutter={16}>
              <Col span={6}>
                <Card size="small">
                  <Statistic 
                    title="板块总数"
                    value={conceptDaily.length}
                    suffix="个"
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small" style={{ background: '#fff1f0' }}>
                  <Statistic 
                    title={<Text style={{ color: '#cf1322' }}>上涨板块</Text>}
                    value={upCount}
                    prefix={<RiseOutlined />}
                    valueStyle={{ color: '#cf1322' }}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small" style={{ background: '#f6ffed' }}>
                  <Statistic 
                    title={<Text style={{ color: '#52c41a' }}>下跌板块</Text>}
                    value={downCount}
                    prefix={<FallOutlined />}
                    valueStyle={{ color: '#52c41a' }}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic 
                    title="平均涨幅"
                    value={avgChange.toFixed(2)}
                    suffix="%"
                    valueStyle={{ color: avgChange >= 0 ? '#cf1322' : '#52c41a' }}
                  />
                </Card>
              </Col>
            </Row>
          )}

          {/* 搜索框 */}
          <Search
            placeholder="搜索概念名称或代码..."
            allowClear
            enterButton={<SearchOutlined />}
            style={{ width: 300 }}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />

          {/* 表格 */}
          <Spin spinning={loading}>
            <Table
              dataSource={filteredData}
              columns={conceptDaily.length > 0 ? dailyColumns : conceptColumns}
              rowKey={conceptDaily.length > 0 ? 'concept_code' : 'ts_code'}
              scroll={{ x: 1200 }}
              pagination={{
                pageSize: 50,
                showSizeChanger: true,
                showTotal: (total) => `共 ${total} 条`,
              }}
              size="small"
            />
          </Spin>
        </Space>
      </Card>

      {/* 成分股抽屉 */}
      <Drawer
        title={
          <Space>
            <TeamOutlined />
            {selectedConcept?.concept_name || selectedConcept?.name} - 成分股
          </Space>
        }
        placement="right"
        width={500}
        onClose={() => setDrawerVisible(false)}
        open={drawerVisible}
      >
        <Spin spinning={membersLoading}>
          <Table
            dataSource={members}
            columns={memberColumns}
            rowKey="stock_code"
            pagination={{ pageSize: 20 }}
            size="small"
          />
        </Spin>
      </Drawer>
    </div>
  );
}
