import React from 'react';
import { Table, Tag } from 'antd';
import { useNavigate } from 'react-router-dom';
import type { ColumnsType } from 'antd/es/table';
import { Position } from '../../types';

interface PositionTableProps {
  data: Position[];
  loading?: boolean;
}

/**
 * 持仓表格组件
 */
export const PositionTable: React.FC<PositionTableProps> = ({ 
  data, 
  loading = false 
}) => {
  const navigate = useNavigate();

  const columns: ColumnsType<Position> = [
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
      title: '数量',
      dataIndex: 'quantity',
      width: 80,
      render: (v: number) => v.toLocaleString()
    },
    {
      title: '可用',
      dataIndex: 'available',
      width: 80,
      render: (v: number) => v.toLocaleString()
    },
    {
      title: '成本价',
      dataIndex: 'cost_price',
      width: 80,
      render: (v: number) => v?.toFixed(2)
    },
    {
      title: '现价',
      dataIndex: 'current_price',
      width: 80,
      render: (v: number, record: Position) => {
        const color = v > record.cost_price 
          ? 'var(--color-up)' 
          : v < record.cost_price 
            ? 'var(--color-down)' 
            : 'var(--text-muted)';
        return <span style={{ color }}>{v?.toFixed(2)}</span>;
      }
    },
    {
      title: '市值',
      dataIndex: 'market_value',
      width: 100,
      render: (v: number) => `${(v / 1e4).toFixed(2)}万`
    },
    {
      title: '盈亏',
      dataIndex: 'profit',
      width: 100,
      render: (v: number) => {
        const color = v > 0 ? 'var(--color-up)' : v < 0 ? 'var(--color-down)' : 'var(--text-muted)';
        return (
          <span style={{ color }}>
            {v > 0 ? '+' : ''}{v?.toFixed(2)}
          </span>
        );
      }
    },
    {
      title: '收益率',
      dataIndex: 'profit_pct',
      width: 80,
      render: (v: number) => (
        <Tag color={v > 0 ? 'green' : v < 0 ? 'red' : 'default'}>
          {v > 0 ? '+' : ''}{v?.toFixed(2)}%
        </Tag>
      )
    }
  ];

  return (
    <Table
      columns={columns}
      dataSource={data}
      rowKey="stock_code"
      loading={loading}
      pagination={false}
      size="small"
      summary={(pageData) => {
        let totalMarketValue = 0;
        let totalProfit = 0;

        pageData.forEach(({ market_value, profit }) => {
          totalMarketValue += market_value;
          totalProfit += profit;
        });

        return (
          <Table.Summary.Row style={{ fontWeight: 600 }}>
            <Table.Summary.Cell index={0} colSpan={6}>合计</Table.Summary.Cell>
            <Table.Summary.Cell index={6}>
              {(totalMarketValue / 1e4).toFixed(2)}万
            </Table.Summary.Cell>
            <Table.Summary.Cell index={7}>
              <span style={{ 
                color: totalProfit > 0 ? 'var(--color-up)' : totalProfit < 0 ? 'var(--color-down)' : 'var(--text-muted)' 
              }}>
                {totalProfit > 0 ? '+' : ''}{totalProfit.toFixed(2)}
              </span>
            </Table.Summary.Cell>
            <Table.Summary.Cell index={8}>-</Table.Summary.Cell>
          </Table.Summary.Row>
        );
      }}
      onRow={(record) => ({
        onClick: () => navigate(`/stock/${record.stock_code}`),
        style: { cursor: 'pointer' }
      })}
    />
  );
};

export default PositionTable;
