import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Spin, DatePicker, Table, Tag, Typography } from 'antd';
import { marketAPI, indexAPI } from '../services/api';
import { IndexCard, MarketSentiment } from '../components/Cards';
import { IntradayChart, KLineChart } from '../components/Charts';
import dayjs from 'dayjs';

const { Title } = Typography;

// 指数代码映射
const INDEX_MAP = {
  '000001': '上证指数',
  '399001': '深证成指',
  '399006': '创业板指',
};

const Dashboard = () => {
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState(dayjs().format('YYYY-MM-DD'));
  const [snapshot, setSnapshot] = useState(null);
  const [limitUpList, setLimitUpList] = useState([]);
  const [indexData, setIndexData] = useState({});
  const [activeIndex, setActiveIndex] = useState('000001');
  const [chartType, setChartType] = useState('intraday'); // 'intraday' | 'daily'

  useEffect(() => {
    loadData();
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
        
        // 加载主要指数数据
        if (snapshotRes.data?.indices?.length > 0) {
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

  const loadIndexChart = async (code) => {
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
        const res = await indexAPI.getDaily(code, date, 60);
        if (res.code === 200) {
          setIndexData(prev => ({
            ...prev,
            [code]: { ...prev[code], daily: res.data || [] }
          }));
        }
      }
    } catch (error) {
      console.error('加载指数图表失败:', error);
    }
  };

  const handleIndexClick = (code) => {
    setActiveIndex(code);
    loadIndexChart(code);
  };

  const handleChartTypeChange = (type) => {
    setChartType(type);
    loadIndexChart(activeIndex);
  };

  // 热榜表格列配置
  const columns = [
    { 
      title: '代码', 
      dataIndex: 'stock_code', 
      width: 80,
      render: (v) => <a href={`/stock/${v}`} style={{ color: 'var(--color-primary)' }}>{v}</a>
    },
    { title: '名称', dataIndex: 'stock_name', width: 80 },
    { 
      title: '涨幅', 
      dataIndex: 'change_pct', 
      width: 80,
      render: (v) => <Tag color="red">{v >= 0 ? '+' : ''}{v?.toFixed(2)}%</Tag>
    },
    { 
      title: '连板', 
      dataIndex: 'limit_times', 
      width: 60, 
      render: (v) => v > 1 ? `${v}板` : '首板'
    },
    { title: '首封', dataIndex: 'first_time', width: 70 },
    { 
      title: '炸板', 
      dataIndex: 'open_times', 
      width: 60,
      render: (v) => v > 0 ? <Tag color="orange">{v}次</Tag> : '-'
    },
  ];

  // 准备图表数据
  const currentIntraday = indexData[activeIndex]?.intraday || [];
  const currentDaily = indexData[activeIndex]?.daily || [];
  const currentIndex = snapshot?.indices?.find(i => i.index_code === activeIndex);
  const preClose = currentIndex?.pre_close || currentIntraday[0]?.price || 0;

  return (
    <div style={{ padding: 24 }}>
      {/* 日期选择器 */}
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3} style={{ margin: 0, color: 'var(--text-primary)' }}>市场总览</Title>
        <DatePicker 
          value={dayjs(date)} 
          onChange={(d) => setDate(d.format('YYYY-MM-DD'))}
          style={{ width: 160 }}
        />
      </div>

      <Spin spinning={loading}>
        {/* 三大指数卡片 */}
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

        {/* 市场情绪 */}
        <div style={{ marginBottom: 20 }}>
          <MarketSentiment data={snapshot} />
        </div>

        {/* 指数图表 */}
        <Card 
          style={{ marginBottom: 20 }}
          bodyStyle={{ padding: '16px 16px 4px 16px' }}
        >
          <div className="chart-container" style={{ border: 'none', padding: 0, background: 'transparent' }}>
            <div className="chart-header" style={{ marginBottom: 12 }}>
              <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
                {INDEX_MAP[activeIndex] || '指数'} · {date}
              </div>
              <div className="chart-tabs">
                <span 
                  className={`chart-tab ${chartType === 'intraday' ? 'active' : ''}`}
                  onClick={() => handleChartTypeChange('intraday')}
                >
                  分时
                </span>
                <span 
                  className={`chart-tab ${chartType === 'daily' ? 'active' : ''}`}
                  onClick={() => handleChartTypeChange('daily')}
                >
                  日K
                </span>
              </div>
            </div>
          </div>
          {chartType === 'intraday' ? (
            <IntradayChart 
              data={currentIntraday} 
              preClose={preClose}
              height={320}
            />
          ) : (
            <KLineChart 
              data={currentDaily}
              maLines={[
                { key: 'ma5', color: '#fff' },
                { key: 'ma10', color: '#FFA726' },
                { key: 'ma20', color: '#9C27B0' },
              ]}
              height={320}
            />
          )}
        </Card>

        {/* 涨停热榜 */}
        <Card 
          title={<span style={{ color: 'var(--text-primary)' }}>涨停热榜 (Top 10)</span>}
          extra={<a href="/limit-up" style={{ color: 'var(--color-primary)' }}>查看更多 →</a>}
        >
          <Table
            columns={columns}
            dataSource={limitUpList}
            rowKey="stock_code"
            pagination={false}
            size="small"
          />
          {limitUpList.length === 0 && !loading && (
            <div className="empty-data">暂无涨停数据</div>
          )}
        </Card>
      </Spin>
    </div>
  );
};

export default Dashboard;
