import React, { useState, useEffect } from 'react';
import { Card, Table, Tag, Spin, DatePicker, Typography, Tabs } from 'antd';
import { conceptAPI } from '../services/api';
import dayjs from 'dayjs';

const { Title } = Typography;

const ConceptRank = () => {
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState(dayjs().format('YYYY-MM-DD'));
  const [conceptList, setConceptList] = useState([]);
  const [page, setPage] = useState(1);

  useEffect(() => {
    loadData();
  }, [date, page]);

  const loadData = async () => {
    setLoading(true);
    try {
      const res = await conceptAPI.getRank(date, 'change_pct', 'desc', page, 50);
      if (res.code === 200) {
        setConceptList(res.data.items || []);
      }
    } catch (error) {
      console.error('加载数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const columns = [
    { title: '排名', dataIndex: 'rank', width: 60 },
    { 
      title: '概念名称', 
      dataIndex: 'concept_name', 
      width: 150,
      render: (v, r) => <a href={`/concept/${r.concept_code}`}>{v}</a>
    },
    { 
      title: '涨幅', 
      dataIndex: 'change_pct', 
      width: 100,
      render: (v) => (
        <Tag color={v >= 0 ? 'red' : 'green'}>
          {v >= 0 ? '+' : ''}{v?.toFixed(2)}%
        </Tag>
      )
    },
    { 
      title: '成交额', 
      dataIndex: 'amount', 
      width: 120,
      render: (v) => v > 100000000 ? `${(v / 100000000).toFixed(2)}亿` : `${(v / 10000).toFixed(0)}万`
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3} style={{ margin: 0 }}>概念板块排行</Title>
        <DatePicker 
          value={dayjs(date)} 
          onChange={(d) => setDate(d.format('YYYY-MM-DD'))}
          style={{ width: 200 }}
        />
      </div>

      <Spin spinning={loading}>
        <Table
          columns={columns}
          dataSource={conceptList}
          rowKey="concept_code"
          pagination={{
            current: page,
            pageSize: 50,
            total: conceptList.length,
            onChange: setPage,
          }}
          size="small"
        />
      </Spin>
    </div>
  );
};

export default ConceptRank;
