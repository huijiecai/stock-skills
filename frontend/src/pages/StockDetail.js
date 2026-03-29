import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Card, Row, Col, Tag, Spin, Typography } from 'antd';
import { stockAPI } from '../services/api';
import { KLineChart } from '../components/Charts';
import CountUp from 'react-countup';

const { Title } = Typography;

const StockDetail = () => {
  const { code } = useParams();
  const [loading, setLoading] = useState(true);
  const [stockInfo, setStockInfo] = useState(null);
  const [dailyData, setDailyData] = useState([]);
  const [chartType, setChartType] = useState('intraday');
  const [concepts, setConcepts] = useState([]);

  useEffect(() => {
    loadStockData();
  }, [code]);

  const loadStockData = async () => {
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
        setDailyData(dailyRes.data || []);
      }
      if (conceptsRes.code === 200) {
        setConcepts(conceptsRes.data || []);
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

  const isUp = (stockInfo.change_pct || 0) >= 0;
  const preClose = stockInfo.pre_close || dailyData[0]?.close || 0;

  return (
    <div style={{ padding: 24 }}>
      {/* 股票头部信息 */}
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
                <CountUp end={stockInfo.close} duration={0.5} decimals={2} />
              </span>
              <span style={{ 
                marginLeft: 12,
                fontSize: 18,
                fontFamily: 'var(--font-mono)',
                color: isUp ? 'var(--color-up)' : 'var(--color-down)'
              }}>
                {isUp ? '+' : ''}{stockInfo.change_pct?.toFixed(2)}%
              </span>
            </div>
            <div style={{ marginTop: 8, color: 'var(--text-secondary)' }}>
              昨收: {preClose?.toFixed(2)} | 
              成交额: {(stockInfo.amount / 1e8)?.toFixed(2)}亿 |
              换手率: {stockInfo.turnover_rate?.toFixed(2)}%
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

      {/* 图表区域 */}
      <Card style={{ marginBottom: 20 }} bodyStyle={{ padding: 16 }}>
        <div className="chart-container" style={{ border: 'none', padding: 0, background: 'transparent' }}>
          <div className="chart-header">
            <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
              {stockInfo.stock_name} · 图表
            </div>
            <div className="chart-tabs">
              <span 
                className={`chart-tab ${chartType === 'intraday' ? 'active' : ''}`}
                onClick={() => setChartType('intraday')}
              >
                分时
              </span>
              <span 
                className={`chart-tab ${chartType === 'daily' ? 'active' : ''}`}
                onClick={() => setChartType('daily')}
              >
                日K
              </span>
            </div>
          </div>
        </div>
        {chartType === 'daily' ? (
          <KLineChart 
            data={dailyData}
            maLines={[
              { key: 'ma5', color: '#fff' },
              { key: 'ma10', color: '#FFA726' },
              { key: 'ma20', color: '#9C27B0' },
            ]}
            height={400}
          />
        ) : (
          <div className="empty-data" style={{ padding: 60 }}>分时数据暂未加载，请查看日K图</div>
        )}
        {dailyData.length === 0 && (
          <div className="empty-data">暂无图表数据</div>
        )}
      </Card>
    </div>
  );
};

export default StockDetail;
