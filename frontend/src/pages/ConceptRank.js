import React, { useState, useEffect } from 'react';
import { Card, Table, Spin, DatePicker, Typography, Pagination } from 'antd';
import { conceptAPI } from '../services/api';
import dayjs from 'dayjs';

const { Title } = Typography;

const ConceptRank = () => {
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState(dayjs().format('YYYY-MM-DD'));
  const [conceptList, setConceptList] = useState([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 50;

  useEffect(() => {
    loadData();
  }, [date, page]);

  const loadData = async () => {
    setLoading(true);
    try {
      const res = await conceptAPI.getRank(date, 'change_pct', 'desc', page, pageSize);
      if (res.code === 200) {
        setConceptList(res.data.items || []);
        setTotal(res.data.total || 0);
      }
    } catch (error) {
      console.error('加载数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const columns = [
    {
      title: '排名',
      dataIndex: 'rank',
      width: 60,
      render: (v, _, idx) => (
        <span style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
          {(page - 1) * pageSize + idx + 1}
        </span>
      ),
    },
    {
      title: '概念名称',
      dataIndex: 'concept_name',
      width: 150,
      render: (v, r) => (
        <a 
          href={`/concept/${r.concept_code}`} 
          style={{ color: 'var(--color-primary)' }}
        >
          {v}
        </a>
      ),
    },
    {
      title: '涨幅',
      dataIndex: 'change_pct',
      width: 100,
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
      width: 120,
      align: 'right',
      render: (v) => (
        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
          {v > 100000000 ? `${(v / 100000000).toFixed(2)}亿` : `${(v / 10000).toFixed(0)}万`}
        </span>
      ),
    },
    {
      title: '涨停家数',
      dataIndex: 'limit_up_count',
      width: 100,
      align: 'center',
      render: (v) => (
        <span style={{ color: v > 0 ? 'var(--color-up)' : 'var(--text-muted)' }}>
          {v || 0}
        </span>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3} style={{ margin: 0, color: 'var(--text-primary)' }}>板块排行</Title>
        <DatePicker 
          value={dayjs(date)} 
          onChange={(d) => setDate(d.format('YYYY-MM-DD'))}
          style={{ width: 160 }}
        />
      </div>

      <Card bodyStyle={{ padding: 16 }}>
        <Spin spinning={loading}>
          <Table
            columns={columns}
            dataSource={conceptList}
            rowKey="concept_code"
            pagination={false}
            size="small"
          />
          {conceptList.length === 0 && !loading && (
            <div className="empty-data">暂无板块数据</div>
          )}
        </Spin>

        {total > pageSize && (
          <div style={{ marginTop: 16, textAlign: 'right' }}>
            <Pagination
              current={page}
              pageSize={pageSize}
              total={total}
              onChange={(p) => setPage(p)}
              showSizeChanger={false}
              showTotal={(total) => `共 ${total} 条`}
            />
          </div>
        )}
      </Card>
    </div>
  );
};

export default ConceptRank;
