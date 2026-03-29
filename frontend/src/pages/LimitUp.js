import React, { useState, useEffect } from 'react';
import { Card, Table, DatePicker, Tabs, Tag, Spin, Typography, Tooltip } from 'antd';
import { marketAPI } from '../services/api';
import { MarketSentiment } from '../components/Cards';
import dayjs from 'dayjs';

const { Title } = Typography;

const LimitUp = () => {
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState(null); // 初始为null
  const [activeTab, setActiveTab] = useState('limit-up');
  const [limitUpList, setLimitUpList] = useState([]);
  const [limitDownList, setLimitDownList] = useState([]);
  const [brokenList, setBrokenList] = useState([]);
  const [statistics, setStatistics] = useState({});

  // 获取最近交易日
  useEffect(() => {
    const initDate = async () => {
      try {
        const res = await marketAPI.getLatestTradeDate();
        if (res.code === 200 && res.data?.date) {
          setDate(res.data.date);
        } else {
          setDate(dayjs().format('YYYY-MM-DD'));
        }
      } catch {
        setDate(dayjs().format('YYYY-MM-DD'));
      }
    };
    initDate();
  }, []);

  useEffect(() => {
    if (date) loadData();
  }, [date]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [upRes, downRes, statsRes] = await Promise.all([
        marketAPI.getLimitUp(date, 1, 100),
        marketAPI.getLimitDown(date, 1, 100),
        marketAPI.getStatistics(date),
      ]);
      
      if (upRes.code === 200) {
        setLimitUpList(upRes.data.items || []);
      }
      if (downRes.code === 200) {
        setLimitDownList(downRes.data.items || []);
      }
      if (statsRes.code === 200) {
        setStatistics(statsRes.data || {});
        setBrokenList(statsRes.data.broken_list || []);
      }
    } catch (error) {
      console.error('加载涨跌停数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const getColumns = (type) => [
    {
      title: '代码',
      dataIndex: 'stock_code',
      width: 80,
      render: (v) => (
        <a href={`/stock/${v}`} style={{ color: 'var(--color-primary)', fontFamily: 'var(--font-mono)' }}>
          {v}
        </a>
      ),
    },
    { 
      title: '名称', 
      dataIndex: 'stock_name', 
      width: 100,
      render: (v) => <span style={{ color: 'var(--text-primary)' }}>{v}</span>,
    },
    {
      title: '涨跌幅',
      dataIndex: 'change_pct',
      width: 90,
      align: 'right',
      render: (v) => {
        const color = v >= 0 ? 'var(--color-up)' : 'var(--color-down)';
        return (
          <span style={{ fontFamily: 'var(--font-mono)', color, fontWeight: 500 }}>
            {v >= 0 ? '+' : ''}{v?.toFixed(2)}%
          </span>
        );
      },
    },
    {
      title: '连板',
      dataIndex: 'limit_times',
      width: 70,
      render: (v) => {
        if (v > 1) {
          return <Tag color={v >= 5 ? 'gold' : v >= 3 ? 'orange' : 'blue'}>{v}板</Tag>;
        }
        return <span style={{ color: 'var(--text-muted)' }}>首板</span>;
      },
    },
    {
      title: '首封时间',
      dataIndex: 'first_time',
      width: 80,
      render: (v) => (
        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
          {v || '-'}
        </span>
      ),
    },
    {
      title: '封单额',
      dataIndex: 'limit_amount',
      width: 90,
      align: 'right',
      render: (v) => (
        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
          {(v / 1e8)?.toFixed(2)}亿
        </span>
      ),
    },
    {
      title: '炸板',
      dataIndex: 'open_times',
      width: 70,
      render: (v) => {
        if (v > 0) {
          return (
            <Tooltip title={`炸板 ${v} 次`}>
              <Tag color="orange">{v}次</Tag>
            </Tooltip>
          );
        }
        return <span style={{ color: 'var(--color-up)' }}>否</span>;
      },
    },
  ];

  const tabItems = [
    { 
      key: 'limit-up', 
      label: `涨停 (${limitUpList.length})`,
    },
    { 
      key: 'limit-down', 
      label: `跌停 (${limitDownList.length})`,
    },
  ];

  const getCurrentData = () => {
    switch (activeTab) {
      case 'limit-up':
        return limitUpList;
      case 'limit-down':
        return limitDownList;
      default:
        return [];
    }
  };

  return (
    <div style={{ padding: 24 }}>
      {/* 标题和日期选择 */}
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3} style={{ margin: 0, color: 'var(--text-primary)' }}>涨跌停</Title>
        <DatePicker 
          value={dayjs(date)} 
          onChange={(d) => setDate(d.format('YYYY-MM-DD'))}
          style={{ width: 160 }}
        />
      </div>

      <Spin spinning={loading}>
        {/* 市场统计 */}
        <div style={{ marginBottom: 20 }}>
          <MarketSentiment data={statistics} />
        </div>

        <Card bodyStyle={{ padding: 16 }}>
          {/* Tab 切换 */}
          <Tabs 
            activeKey={activeTab}
            items={tabItems}
            onChange={setActiveTab}
            style={{ marginBottom: 16 }}
          />

          {/* 表格 */}
          <Table
            columns={getColumns(activeTab)}
            dataSource={getCurrentData()}
            rowKey="stock_code"
            pagination={false}
            size="small"
          />
          {getCurrentData().length === 0 && !loading && (
            <div className="empty-data">
              暂无{activeTab === 'limit-up' ? '涨停' : '跌停'}数据
            </div>
          )}
        </Card>
      </Spin>
    </div>
  );
};

export default LimitUp;
