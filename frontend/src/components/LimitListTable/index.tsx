import React from 'react';
import { Table, Tag } from 'antd';
import { useNavigate } from 'react-router-dom';
import type { ColumnsType } from 'antd/es/table';
import { LimitUpStock } from '../../types';

interface LimitListTableProps {
  data: LimitUpStock[];
  loading?: boolean;
  type?: 'limit-up' | 'limit-down' | 'broken';
  pagination?: false | object;
}

/**
 * 涨跌停表格组件
 */
export const LimitListTable: React.FC<LimitListTableProps> = ({ 
  data, 
  loading = false,
  type = 'limit-up',
  pagination = false
}) => {
  const navigate = useNavigate();

  const columns: ColumnsType<LimitUpStock> = [
    { 
      title: '代码', 
      dataIndex: 'stock_code', 
      width: 80,
      render: (v: string) => (
        <a 
          onClick={(e) => {
            e.stopPropagation();
            navigate(`/stock/${v}`);
          }}
          style={{ color: 'var(--color-primary)', cursor: 'pointer' }}
        >
          {v}
        </a>
      )
    },
    { 
      title: '名称', 
      dataIndex: 'stock_name', 
      width: 80 
    },
    {
      title: '连板',
      dataIndex: 'limit_times',
      width: 60,
      render: (v: number) => {
        const color = v >= 5 ? '#FF5252' : v >= 3 ? '#FFA726' : '#26A69A';
        return (
          <Tag color={color}>
            {v > 1 ? `${v}板` : '首板'}
          </Tag>
        );
      }
    },
    {
      title: '首板时间',
      dataIndex: 'first_time',
      width: 80,
    },
    {
      title: '封单额',
      dataIndex: 'limit_amount',
      width: 90,
      render: (v: number) => v ? `${(v / 1e8).toFixed(2)}亿` : '-'
    },
    {
      title: '炸板',
      dataIndex: 'open_times',
      width: 60,
      render: (v: number, record: LimitUpStock) => {
        if (v === 0) return <Tag>-</Tag>;
        if (record.is_broken && !record.reseal_time) {
          return <Tag color="red">{v}次</Tag>;
        }
        return (
          <Tag color="orange" title={`炸板: ${record.broken_time || '-'}, 回封: ${record.reseal_time || '-'}`}>
            {v}次*
          </Tag>
        );
      }
    }
  ];

  return (
    <Table
      columns={columns}
      dataSource={data}
      rowKey="stock_code"
      loading={loading}
      pagination={pagination}
      size="small"
      onRow={(record) => ({
        onClick: () => navigate(`/stock/${record.stock_code}`),
        style: { cursor: 'pointer' }
      })}
    />
  );
};

export default LimitListTable;
