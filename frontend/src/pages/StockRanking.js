import React, { useState, useEffect } from 'react';
import { Card, Table, DatePicker, Spin, Typography, Pagination } from 'antd';
import { marketAPI } from '../services/api';
import dayjs from 'dayjs';

const { Title } = Typography;

const StockRanking = () => {
  const [loading, setLoading] = useState(false);
  const [date, setDate] = useState(null);
  const [sortField, setSortField] = useState('change_pct');
  const [sortOrder, setSortOrder] = useState('desc');
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
  }, [date, sortField, sortOrder, page]);

  const loadData = async () => {
    setLoading(true);
    try {
      const res = await marketAPI.getStockRanking({
        date,
        sort: sortField,
        order: sortOrder,
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

  // 表格排序变化
  const handleTableChange = (pagination, filters, sorter) => {
    console.log('Table sorter:', sorter); // 调试
    if (sorter && sorter.field) {
      setSortField(sorter.field);
      setSortOrder(sorter.order === 'ascend' ? 'asc' : 'desc');
      setPage(1);
    } else if (sorter && sorter.length > 0) {
      // 多列排序情况
      const first = sorter[0];
      setSortField(first.field);
      setSortOrder(first.order === 'ascend' ? 'asc' : 'desc');
      setPage(1);
    }
  };

  // 获取涨跌颜色
  const getChangeColor = (value) => {
    if (value > 0) return 'var(--color-up)';    // 涨 - 红色
    if (value < 0) return 'var(--color-down)';  // 跌 - 绿色
    return 'var(--text-muted)';                  // 平 - 灰色
  };

  const columns = [
    {
      title: '排名',
      width: 60,
      render: (_, __, idx) => (
        <span style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
          {(page - 1) * pageSize + idx + 1}
        </span>
      ),
    },
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
      render: (v, r) => (
        <span style={{ fontFamily: 'var(--font-mono)', color: getChangeColor(r.change_pct) }}>
          {v?.toFixed(2)}
        </span>
      ),
    },
    {
      title: '涨跌幅',
      dataIndex: 'change_pct',
      width: 100,
      align: 'right',
      sorter: true,
      sortOrder: sortField === 'change_pct' ? (sortOrder === 'asc' ? 'ascend' : 'descend') : null,
      render: (v) => (
        <span style={{ fontFamily: 'var(--font-mono)', color: getChangeColor(v), fontWeight: 500 }}>
          {v > 0 ? '+' : ''}{v?.toFixed(2)}%
        </span>
      ),
    },
    {
      title: '成交额',
      dataIndex: 'amount',
      width: 100,
      align: 'right',
      sorter: true,
      sortOrder: sortField === 'amount' ? (sortOrder === 'asc' ? 'ascend' : 'descend') : null,
      render: (v) => (
        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
          {(v / 1e8)?.toFixed(2)}亿
        </span>
      ),
    },
    {
      title: '成交量',
      dataIndex: 'volume',
      width: 90,
      align: 'right',
      render: (v) => (
        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
          {(v / 1e4)?.toFixed(0)}万
        </span>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      {/* 标题和日期选择 */}
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3} style={{ margin: 0, color: 'var(--text-primary)' }}>个股排行</Title>
        <DatePicker 
          value={date ? dayjs(date) : null}
          onChange={(d) => {
            setDate(d ? d.format('YYYY-MM-DD') : null);
            setPage(1);
          }}
          style={{ width: 160 }}
        />
      </div>

      <Card styles={{ body: { padding: 16 } }}>
        <Spin spinning={loading}>
          <Table
            columns={columns}
            dataSource={data}
            rowKey="stock_code"
            pagination={false}
            size="small"
            onChange={handleTableChange}
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
