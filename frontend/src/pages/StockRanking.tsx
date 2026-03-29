import React, { useState, useEffect, useCallback } from 'react';
import { Card, Select } from 'antd';
import { marketAPI } from '../services/api';
import { DateSelector, StockTable } from '../components';
import dayjs from 'dayjs';

const { Option } = Select;

type SortType = 'change_pct' | 'amount' | 'turnover_rate' | 'main_inflow';

const StockRanking: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState<string>('');
  const [sortType, setSortType] = useState<SortType>('change_pct');
  const [order, setOrder] = useState<'desc' | 'asc'>('desc');
  const [data, setData] = useState<any[]>([]);

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

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await marketAPI.getStockRanking({
        date,
        sort: sortType,
        order,
        page: 1,
        page_size: 50,
      });
      
      if (res.code === 200) {
        setData(res.data.items || []);
      }
    } catch (error) {
      console.error('加载个股排行失败:', error);
    } finally {
      setLoading(false);
    }
  }, [date, sortType, order]);

  useEffect(() => {
    if (date) loadData();
  }, [date, loadData]);

  const handleSortChange = (newSort: SortType) => {
    setSortType(newSort);
    if (newSort === 'change_pct') {
      setOrder(order === 'desc' ? 'asc' : 'desc');
    } else {
      setOrder('desc');
    }
  };

  const handleTableSort = (field: string, newOrder: 'asc' | 'desc') => {
    setSortType(field as SortType);
    setOrder(newOrder);
  };

  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0, color: 'var(--text-primary)' }}>个股排行</h2>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <span style={{ color: 'var(--text-secondary)' }}>排序:</span>
          <Select value={sortType} onChange={handleSortChange} style={{ width: 120 }}>
            <Option value="change_pct">涨跌幅</Option>
            <Option value="amount">成交额</Option>
            <Option value="turnover_rate">换手率</Option>
            <Option value="main_inflow">大单流入</Option>
          </Select>
          <Select value={order} onChange={(v) => setOrder(v as 'asc' | 'desc')} style={{ width: 100 }}>
            <Option value="desc">降序 ↓</Option>
            <Option value="asc">升序 ↑</Option>
          </Select>
          <DateSelector value={date} onChange={setDate} />
        </div>
      </div>

      <Card>
        <StockTable 
          data={data} 
          loading={loading} 
          showConcept={true}
          sortable={true}
          onSortChange={handleTableSort}
          currentSort={{ field: sortType, order }}
        />
      </Card>
    </div>
  );
};

export default StockRanking;
