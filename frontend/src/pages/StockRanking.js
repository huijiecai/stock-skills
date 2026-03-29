import React, { useState, useEffect } from 'react';
import { Card, Table, DatePicker, Tabs, Tag, Spin, Typography, Pagination } from 'antd';
import { marketAPI } from '../services/api';
import dayjs from 'dayjs';

const { Title } = Typography;

const StockRanking = () => {
  const [loading, setLoading] = useState(false);
  const [date, setDate] = useState(null); // 初始为null
  const [sortType, setSortType] = useState('change_pct');
  const [order, setOrder] = useState('desc');
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [data, setData] = useState([]);
  const [total, setTotal] = useState(0);

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
  }, [date, sortType, order, page]);

  const loadData = async () => {
    setLoading(true);
    try {
      const res = await marketAPI.getStockRanking({
        date,
        sort: sortType,
        order,
        page,
        page_size: pageSize,
      });
      if (res.code === 200) {
        setData(res.data.items || []);
        setTotal(res.data.total || 0);
      }
    } catch (error) {
      console.error('加载个股排行失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleTabChange = (key) => {
    const tabConfig = {
      up: { sort: 'change_pct', order: 'desc' },
      down: { sort: 'change_pct', order: 'asc' },
      amount: { sort: 'amount', order: 'desc' },
      turnover: { sort: 'turnover_rate', order: 'desc' },
    };
    const config = tabConfig[key] || { sort: 'change_pct', order: 'desc' };
    setSortType(config.sort);
    setOrder(config.order);
    setPage(1);
  };

  const columns = [
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
      title: '价格',
      dataIndex: 'close',
      width: 80,
      align: 'right',
      render: (v) => (
        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
          {v?.toFixed(2)}
        </span>
      ),
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
      title: '成交额',
      dataIndex: 'amount',
      width: 100,
      align: 'right',
      render: (v) => (
        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
          {(v / 1e8)?.toFixed(2)}亿
        </span>
      ),
    },
    {
      title: '换手率',
      dataIndex: 'turnover_rate',
      width: 80,
      align: 'right',
      render: (v) => (
        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
          {v?.toFixed(2)}%
        </span>
      ),
    },
    {
      title: '所属概念',
      dataIndex: 'concepts',
      width: 200,
      render: (concepts) => (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {(concepts || []).slice(0, 3).map((c, idx) => (
            <Tag key={idx} style={{ margin: 0, fontSize: 11 }}>{c}</Tag>
          ))}
        </div>
      ),
    },
  ];

  const tabItems = [
    { key: 'up', label: '涨幅榜' },
    { key: 'down', label: '跌幅榜' },
    { key: 'amount', label: '成交额' },
    { key: 'turnover', label: '换手率' },
  ];

  return (
    <div style={{ padding: 24 }}>
      {/* 标题和日期选择 */}
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3} style={{ margin: 0, color: 'var(--text-primary)' }}>个股排行</Title>
        <DatePicker 
          value={dayjs(date)} 
          onChange={(d) => setDate(d.format('YYYY-MM-DD'))}
          style={{ width: 160 }}
        />
      </div>

      <Card bodyStyle={{ padding: 16 }}>
        {/* Tab 切换 */}
        <Tabs 
          defaultActiveKey="up" 
          items={tabItems}
          onChange={handleTabChange}
          style={{ marginBottom: 16 }}
        />

        {/* 表格 */}
        <Spin spinning={loading}>
          <Table
            columns={columns}
            dataSource={data}
            rowKey="stock_code"
            pagination={false}
            size="small"
          />
          {data.length === 0 && !loading && (
            <div className="empty-data">暂无数据</div>
          )}
        </Spin>

        {/* 分页 */}
        {total > pageSize && (
          <div style={{ marginTop: 16, textAlign: 'right' }}>
            <Pagination
              current={page}
              pageSize={pageSize}
              total={total}
              onChange={(p) => setPage(p)}
              showSizeChanger={false}
              showTotal={(total) => `共 ${total} 条`}
              style={{ color: 'var(--text-secondary)' }}
            />
          </div>
        )}
      </Card>
    </div>
  );
};

export default StockRanking;
