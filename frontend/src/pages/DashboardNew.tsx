import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Spin, Typography } from 'antd';
import { marketAPI, indexAPI } from '../services/api';
import { 
  IndexCard, 
  MarketSentiment, 
  DateSelector, 
  ChartPanel,
  LimitListTable
} from '../components';
import dayjs from 'dayjs';
import type { MarketSnapshot, LimitUpStock } from '../types';

const { Title } = Typography;

const INDEX_MAP: Record<string, string> = {
  '000001': '上证指数',
  '399001': '深证成指',
  '399006': '创业板指',
};

const DashboardNew: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState<string>('');
  const [snapshot, setSnapshot] = useState<MarketSnapshot | null>(null);
  const [limitUpList, setLimitUpList] = useState<LimitUpStock[]>([]);
  const [indexData, setIndexData] = useState<Record<string, any>>({});
  const [activeIndex, setActiveIndex] = useState('000001');
  const [chartType, setChartType] = useState<'intraday' | 'daily'>('intraday');

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
      const [snapshotRes, limitUpRes] = await Promise.all([
        marketAPI.getSnapshot(date),
        marketAPI.getLimitUp(date, 1, 10),
      ]);
      
      if (snapshotRes.code === 200) {
        setSnapshot(snapshotRes.data);
        
        if (snapshotRes.data?.indices && snapshotRes.data.indices.length > 0) {
          const firstIndex = snapshotRes.data.indices[0];
          setActiveIndex(firstIndex.index_code);
          loadIndexChart(firstIndex.index_code);
        }
      }
      if (limitUpRes.code === 200) {
        setLimitUpList(limitUpRes.data.items || []);
      }
    } catch (error) {
      console.error('加载数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadIndexChart = async (code: string) => {
    try {
      if (chartType === 'intraday') {
        const res = await indexAPI.getIntraday(code, date);
        if (res.code === 200) {
          setIndexData(prev => ({
            ...prev,
            [code]: { ...prev[code], intraday: res.data || [] }
          }));
        }
      } else {
        const res = await indexAPI.getDaily(code, 60);
        if (res.code === 200) {
          setIndexData(prev => ({
            ...prev,
            [code]: { ...prev[code], daily: res.data?.items || [] }
          }));
        }
      }
    } catch (error) {
      console.error('加载指数图表失败:', error);
    }
  };

  const handleIndexClick = (code: string) => {
    setActiveIndex(code);
    loadIndexChart(code);
  };

  const handleChartTypeChange = (type: 'intraday' | 'daily') => {
    setChartType(type);
    loadIndexChart(activeIndex);
  };

  const currentData = chartType === 'intraday' 
    ? indexData[activeIndex]?.intraday || []
    : indexData[activeIndex]?.daily || [];
  
  const currentIndex = snapshot?.indices?.find(i => i.index_code === activeIndex);
  const preClose = currentIndex?.pre_close || (indexData[activeIndex]?.intraday?.[0]?.price) || 0;

  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3} style={{ margin: 0, color: 'var(--text-primary)' }}>市场总览</Title>
        <DateSelector value={date} onChange={setDate} />
      </div>

      <Spin spinning={loading}>
        <Row gutter={16} style={{ marginBottom: 20 }}>
          {(snapshot?.indices || []).map((idx) => (
            <Col span={6} key={idx.index_code}>
              <IndexCard
                code={idx.index_code}
                name={INDEX_MAP[idx.index_code] || idx.index_name}
                close={idx.close}
                changePct={idx.change_pct}
                amount={idx.amount}
                active={activeIndex === idx.index_code}
                onClick={() => handleIndexClick(idx.index_code)}
              />
            </Col>
          ))}
        </Row>

        <div style={{ marginBottom: 20 }}>
          <MarketSentiment data={snapshot} />
        </div>

        <Card 
          style={{ marginBottom: 20 }}
          bodyStyle={{ padding: '16px 16px 4px 16px' }}
        >
          <div style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 12 }}>
            {INDEX_MAP[activeIndex] || '指数'} · {date}
          </div>
          <ChartPanel
            type={chartType}
            data={currentData}
            preClose={preClose}
            name={INDEX_MAP[activeIndex]}
            height={320}
            onTypeChange={handleChartTypeChange}
          />
        </Card>

        <Card 
          title={<span style={{ color: 'var(--text-primary)' }}>涨停热榜 (Top 10)</span>}
          extra={<a href="/limit-up" style={{ color: 'var(--color-primary)' }}>查看更多 →</a>}
        >
          <LimitListTable
            data={limitUpList}
            loading={false}
            type="limit-up"
          />
          {limitUpList.length === 0 && !loading && (
            <div className="empty-data">暂无涨停数据</div>
          )}
        </Card>
      </Spin>
    </div>
  );
};

export default DashboardNew;
