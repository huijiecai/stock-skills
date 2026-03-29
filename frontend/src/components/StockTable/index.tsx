import React from 'react';
import { Table, Tag } from 'antd';
import { useNavigate } from 'react-router-dom';
import type { ColumnsType } from 'antd/es/table';

interface StockItem {
  stock_code: string;
  stock_name: string;
  close?: number;
  change_pct: number;
  amount?: number;
  turnover_rate?: number;
  main_inflow?: number;
  limit_times?: number;
  concept?: string;
}

interface StockTableProps {
  data: StockItem[];
  loading?: boolean;
  showConcept?: boolean;
  showLimitTimes?: boolean;
  pagination?: false | object;
  size?: 'small' | 'middle' | 'large';
  sortable?: boolean;
  onSortChange?: (field: string, order: 'asc' | 'desc') => void;
  currentSort?: { field: string; order: 'asc' | 'desc' };
}

/**
 * 个股表格组件
 */
export const StockTable: React.FC<StockTableProps> = ({ 
  data, 
  loading = false,
  showConcept = false,
  showLimitTimes = false,
  pagination = false,
  size = 'small',
  sortable = false,
  onSortChange,
  currentSort
}) => {
  const navigate = useNavigate();

  const columns: ColumnsType<StockItem> = [
    { 
      title: '代码', 
      dataIndex: 'stock_code', 
      width: 80,
      sorter: sortable,
      sortOrder: currentSort?.field === 'stock_code' ? (currentSort.order === 'asc' ? 'ascend' : 'descend') : undefined,
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
  ];

  if (showLimitTimes) {
    columns.push({
      title: '连板', 
      dataIndex: 'limit_times', 
      width: 60,
      render: (v: number) => v > 1 ? `${v}板` : '首板'
    });
  }

  columns.push({
    title: '涨幅', 
    dataIndex: 'change_pct', 
    width: 80,
    sorter: sortable,
    sortOrder: currentSort?.field === 'change_pct' ? (currentSort.order === 'asc' ? 'ascend' : 'descend') : undefined,
    render: (v: number) => {
      let color = 'default';
      if (v >= 9.9) color = 'red';
      else if (v > 0) color = 'red';
      else if (v < 0) color = 'green';
      
      return (
        <Tag color={color}>
          {v >= 0 ? '+' : ''}{v?.toFixed(2)}%
        </Tag>
      );
    }
  });

  if (data[0]?.close) {
    columns.push({
      title: '价格',
      dataIndex: 'close',
      width: 80,
      render: (v: number) => v?.toFixed(2)
    });
  }

  if (data[0]?.amount) {
    columns.push({
      title: '成交额',
      dataIndex: 'amount',
      width: 90,
      sorter: sortable,
      sortOrder: currentSort?.field === 'amount' ? (currentSort.order === 'asc' ? 'ascend' : 'descend') : undefined,
      render: (v: number) => `${(v / 1e8).toFixed(2)}亿`
    });
  }

  if (data[0]?.turnover_rate) {
    columns.push({
      title: '换手率',
      dataIndex: 'turnover_rate',
      width: 80,
      render: (v: number) => `${v?.toFixed(2)}%`
    });
  }

  if (data[0]?.main_inflow !== undefined) {
    columns.push({
      title: '大单流入',
      dataIndex: 'main_inflow',
      width: 90,
      render: (v: number) => {
        const color = v > 0 ? 'var(--color-up)' : v < 0 ? 'var(--color-down)' : 'var(--text-muted)';
        return (
          <span style={{ color }}>
            {v > 0 ? '+' : ''}{(v / 1e8).toFixed(2)}亿
          </span>
        );
      }
    });
  }

  if (showConcept && data[0]?.concept) {
    columns.push({
      title: '概念',
      dataIndex: 'concept',
      width: 100,
      render: (v: string) => <Tag>{v}</Tag>
    });
  }

  const handleTableChange = (pagination: any, filters: any, sorter: any) => {
    if (sortable && onSortChange && sorter && sorter.field) {
      const order = sorter.order === 'ascend' ? 'asc' : 'desc';
      onSortChange(sorter.field, order);
    }
  };

  return (
    <Table
      columns={columns}
      dataSource={data}
      rowKey="stock_code"
      loading={loading}
      pagination={pagination}
      size={size}
      onChange={handleTableChange}
      onRow={(record) => ({
        onClick: () => navigate(`/stock/${record.stock_code}`),
        style: { cursor: 'pointer' }
      })}
    />
  );
};

export default StockTable;
