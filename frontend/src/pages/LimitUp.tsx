import React, { useState, useEffect } from 'react';
import { Card, Tabs, Spin } from 'antd';
import { marketAPI } from '../services/api';
import { DateSelector, LimitListTable } from '../components';
import dayjs from 'dayjs';
import type { LimitUpStock } from '../types';

const { TabPane } = Tabs;

const LimitUp: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState<string>('');
  const [activeTab, setActiveTab] = useState<'up' | 'down' | 'broken'>('up');
  const [limitUpList, setLimitUpList] = useState<LimitUpStock[]>([]);
  const [limitDownList, setLimitDownList] = useState<LimitUpStock[]>([]);
  const [brokenList, setBrokenList] = useState<LimitUpStock[]>([]);

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
      const [upRes, downRes, brokenRes] = await Promise.all([
        marketAPI.getLimitUp(date, 1, 100),
        marketAPI.getLimitDown(date, 1, 100),
        marketAPI.getBrokenBoard(date, 1, 100),
      ]);
      
      if (upRes.code === 200) {
        setLimitUpList(upRes.data.items || []);
      }
      if (downRes.code === 200) {
        setLimitDownList(downRes.data.items || []);
      }
      if (brokenRes.code === 200) {
        setBrokenList(brokenRes.data.items || []);
      }
    } catch (error) {
      console.error('加载涨跌停数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0, color: 'var(--text-primary)' }}>涨跌停</h2>
        <DateSelector value={date} onChange={setDate} />
      </div>

      <Spin spinning={loading}>
        <Card>
          <Tabs activeKey={activeTab} onChange={(key) => setActiveTab(key as any)}>
            <TabPane tab={`涨停 (${limitUpList.length})`} key="up">
              <LimitListTable data={limitUpList} loading={false} type="limit-up" />
            </TabPane>
            <TabPane tab={`跌停 (${limitDownList.length})`} key="down">
              <LimitListTable data={limitDownList} loading={false} type="limit-down" />
            </TabPane>
            <TabPane tab={`炸板 (${brokenList.length})`} key="broken">
              <LimitListTable data={brokenList} loading={false} type="broken" />
            </TabPane>
          </Tabs>
        </Card>
      </Spin>
    </div>
  );
};

export default LimitUp;
