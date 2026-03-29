import React, { useState, useEffect } from 'react';
import { Card, Spin } from 'antd';
import { marketAPI } from '../services/api';
import { DateSelector, ContinuousBoard } from '../components';
import dayjs from 'dayjs';
import type { ContinuousBoard as ContinuousBoardType } from '../types';
import './Ladder.css';

const Ladder: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState<string>('');
  const [ladderData, setLadderData] = useState<ContinuousBoardType | null>(null);

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
  }, [date]);

  const loadData = async () => {
    setLoading(true);
    try {
      const res = await marketAPI.getContinuousBoard(date);
      if (res.code === 200) {
        setLadderData(res.data);
      }
    } catch (error) {
      console.error('加载连板天梯失败:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0, color: 'var(--text-primary)' }}>连板天梯</h2>
        <DateSelector value={date} onChange={setDate} />
      </div>

      <Spin spinning={loading}>
        <Card>
          {ladderData && (
            <ContinuousBoard ladder={ladderData.ladder} loading={loading} />
          )}
          {!ladderData && !loading && (
            <div className="empty-data">暂无连板数据</div>
          )}
        </Card>
      </Spin>
    </div>
  );
};

export default Ladder;
