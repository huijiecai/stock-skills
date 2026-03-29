import React, { useState, useEffect } from 'react';
import { Card, Table, Spin, Pagination, Typography } from 'antd';
import { conceptAPI } from '../services/api';
import { DateSelector } from '../components';
import dayjs from 'dayjs';
import type { ConceptRank as ConceptRankType } from '../types';
import type { SortOrder } from 'antd/es/table/interface';

const { Title } = Typography;

const ConceptRank: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState<string>('');
  const [conceptList, setConceptList] = useState<ConceptRankType[]>([]);
  const [page, setPage] = useState(1);
  const [sortField, setSortField] = useState('change_pct');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [total, setTotal] = useState(0);
  const pageSize = 50;

  useEffect(() => {
    if (date) loadData();
  }, [page, sortField, sortOrder, date]);

  useEffect(() => {
    const initDate = async () => {
      try {
        const res = await conceptAPI.getRank(undefined, 'change_pct', 'desc', 1, 1);
        if (res.code === 200 && res.data) {
          setDate(dayjs().format('YYYY-MM-DD'));
        } else {
          setDate(dayjs().format('YYYY-MM-DD'));
        }
      } catch {
        setDate(dayjs().format('YYYY-MM-DD'));
      }
    };
    initDate();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const res = await conceptAPI.getRank(
        date, 
        sortField, 
        sortOrder, 
        page, 
        pageSize
      );
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

  const handleTableChange = (pagination: any, filters: any, sorter: any) => {
    if (sorter && sorter.field) {
      setSortField(sorter.field);
      setSortOrder(sorter.order === 'ascend' ? 'asc' : 'desc');
      setPage(1);
    }
  };

  const getChangeColor = (value: number) => {
    if (value > 0) return 'var(--color-up)';
    if (value < 0) return 'var(--color-down)';
    return 'var(--text-muted)';
  };

  const columns = [
    {
      title: '排名',
      width: 60,
      render: (_: any, __: any, idx: number) => (
        <span style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
          {(page - 1) * pageSize + idx + 1}
        </span>
      ),
    },
    {
      title: '概念名称',
      dataIndex: 'concept_name',
      width: 150,
      render: (v: string, r: ConceptRankType) => (
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
      align: 'right' as const,
      sorter: true,
      sortOrder: sortField === 'change_pct' ? (sortOrder === 'asc' ? ('ascend' as SortOrder) : ('descend' as SortOrder)) : undefined,
      render: (v: number) => (
        <span style={{ fontFamily: 'var(--font-mono)', color: getChangeColor(v), fontWeight: 500 }}>
          {v > 0 ? '+' : ''}{v?.toFixed(2)}%
        </span>
      ),
    },
    {
      title: '涨停家数',
      dataIndex: 'limit_up_count',
      width: 100,
      align: 'center' as const,
      render: (v: number) => (
        <span style={{ color: v > 0 ? 'var(--color-up)' : 'var(--text-muted)', fontWeight: v > 0 ? 500 : 400 }}>
          {v || 0}
        </span>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3} style={{ margin: 0, color: 'var(--text-primary)' }}>板块排行</Title>
        <DateSelector value={date} onChange={setDate} />
      </div>

      <Card>
        <Spin spinning={loading}>
          <Table
            columns={columns}
            dataSource={conceptList}
            rowKey="concept_code"
            pagination={false}
            size="small"
            onChange={handleTableChange}
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
