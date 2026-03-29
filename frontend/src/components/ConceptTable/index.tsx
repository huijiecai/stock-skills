import React from 'react';
import { Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ConceptRank } from '../../types';

interface ConceptTableProps {
  data: ConceptRank[];
  loading?: boolean;
  onConceptClick?: (code: string) => void;
  pagination?: false | object;
}

/**
 * 概念板块表格组件
 */
export const ConceptTable: React.FC<ConceptTableProps> = ({ 
  data, 
  loading = false,
  onConceptClick,
  pagination = false
}) => {
  const columns: ColumnsType<ConceptRank> = [
    { 
      title: '板块名称', 
      dataIndex: 'concept_name', 
      width: 120,
      render: (v: string, record: ConceptRank) => (
        <a 
          onClick={(e) => {
            e.stopPropagation();
            onConceptClick?.(record.concept_code);
          }}
          style={{ color: 'var(--color-primary)', cursor: 'pointer' }}
        >
          {v}
        </a>
      )
    },
    {
      title: '涨幅',
      dataIndex: 'change_pct',
      width: 80,
      render: (v: number) => (
        <Tag color={v > 0 ? 'green' : v < 0 ? 'red' : 'default'}>
          {v >= 0 ? '+' : ''}{v?.toFixed(2)}%
        </Tag>
      )
    },
    {
      title: '涨停家数',
      dataIndex: 'limit_up_count',
      width: 80,
      render: (v: number) => v > 0 ? <Tag color="red">{v}</Tag> : '-'
    },
    {
      title: '领涨股',
      dataIndex: 'leading_stock',
      width: 100,
      render: (v: string) => v || '-'
    }
  ];

  return (
    <Table
      columns={columns}
      dataSource={data}
      rowKey="concept_code"
      loading={loading}
      pagination={pagination}
      size="small"
      onRow={(record) => ({
        onClick: () => onConceptClick?.(record.concept_code),
        style: { cursor: 'pointer' }
      })}
    />
  );
};

export default ConceptTable;
