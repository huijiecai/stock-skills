import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Card, Row, Col, Tag, Spin, Typography } from 'antd';
import { stockAPI } from '../services/api';
import { ChartPanel } from '../components';
import CountUp from 'react-countup';
import type { StockDaily } from '../types';

const { Title } = Typography;

const StockDetail: React.FC = () => {
  const { code } = useParams<{ code: string }>();
  const [loading, setLoading] = useState(true);
  const [stockInfo, setStockInfo] = useState<any>(null);
  const [dailyData, setDailyData] = useState<StockDaily[]>([]);
  const [chartType, setChartType] = useState<'intraday' | 'daily'>('daily');
  const [concepts, setConcepts] = useState<any[]>([]);

  useEffect(() => {
    if (code) loadStockData();
  }, [code]);

  const loadStockData = async () => {
    if (!code) return;
    
    setLoading(true);
    try {
      const [infoRes, dailyRes, conceptsRes] = await Promise.all([
        stockAPI.getInfo(code),
        stockAPI.getDaily(code, 60),
        stockAPI.getConcepts(code),
      ]);

      if (infoRes.code === 200) {
        setStockInfo(infoRes.data);
      }
      if (dailyRes.code === 200) {
        setDailyData(dailyRes.data?.items || []);
      }
      if (conceptsRes.code === 200) {
        setConcepts(conceptsRes.data?.concepts || []);
      }
    } catch (error) {
      console.error('加载股票数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!stockInfo) {
    return (
      <div style={{ padding: 24 }}>
        <div className="empty-data">股票不存在或暂无数据</div>
      </div>
    );
  }

  const latestDaily = dailyData[dailyData.length - 1];
  const currentPrice = latestDaily?.close || 0;
  const changePct = latestDaily?.change_pct || 0;
  const isUp = changePct >= 0;
  const preClose = dailyData[dailyData.length - 2]?.close || currentPrice;

  return (
    <div style={{ padding: 24 }}>
      <Card style={{ marginBottom: 20 }} bodyStyle={{ padding: 20 }}>
        <Row gutter={24}>
          <Col span={12}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
              <Title level={2} style={{ margin: 0, color: 'var(--text-primary)' }}>
                {stockInfo.stock_name}
              </Title>
              <span style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
                {code}
              </span>
            </div>
            <div style={{ marginTop: 16 }}>
              <span style={{ 
                fontSize: 36, 
                fontWeight: 600,
                fontFamily: 'var(--font-mono)',
                color: isUp ? 'var(--color-up)' : 'var(--color-down)'
              }}>
                <CountUp end={currentPrice} duration={0.5} decimals={2} />
              </span>
              <span style={{ 
                marginLeft: 12,
                fontSize: 18,
                fontFamily: 'var(--font-mono)',
                color: isUp ? 'var(--color-up)' : 'var(--color-down)'
              }}>
                {isUp ? '+' : ''}{changePct?.toFixed(2)}%
              </span>
            </div>
            <div style={{ marginTop: 8, color: 'var(--text-secondary)' }}>
              昨收: {preClose?.toFixed(2)} | 
              成交额: {(latestDaily?.amount / 1e8)?.toFixed(2)}亿 |
              换手率: {latestDaily?.turnover_rate?.toFixed(2)}%
            </div>
          </Col>
          <Col span={12}>
            <div style={{ textAlign: 'right' }}>
              <div style={{ color: 'var(--text-secondary)', marginBottom: 8 }}>所属概念</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'flex-end' }}>
                {concepts.map((c, idx) => (
                  <Tag 
                    key={idx}
                    style={{ 
                      background: c.is_core ? 'var(--color-primary-bg)' : 'var(--bg-tertiary)',
                      color: c.is_core ? 'var(--color-primary)' : 'var(--text-primary)',
                      border: c.is_core ? '1px solid var(--color-primary)' : 'none'
                    }}
                  >
                    {c.concept_name}
                    {c.is_core && <span style={{ marginLeft: 4, fontSize: 11 }}>(龙头)</span>}
                  </Tag>
                ))}
              </div>
            </div>
          </Col>
        </Row>
      </Card>

      <Card style={{ marginBottom: 20 }} bodyStyle={{ padding: 16 }}>
        <ChartPanel
          type={chartType}
          data={dailyData}
          preClose={preClose}
          name={stockInfo.stock_name}
          height={400}
          onTypeChange={setChartType}
        />
      </Card>
    </div>
  );
};

export default StockDetail;
