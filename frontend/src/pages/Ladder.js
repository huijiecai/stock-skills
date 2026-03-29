import React, { useState, useEffect } from 'react';
import { Card, DatePicker, Spin, Typography, Row, Col } from 'antd';
import { marketAPI } from '../services/api';
import { LadderCard, MarketSentiment } from '../components/Cards';
import dayjs from 'dayjs';

const { Title } = Typography;

const Ladder = () => {
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState(null); // 初始为null
  const [ladder, setLadder] = useState([]);
  const [statistics, setStatistics] = useState({});

  // 获取最近交易日
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
      const [ladderRes, statsRes] = await Promise.all([
        marketAPI.getContinuousBoard(date),
        marketAPI.getStatistics(date),
      ]);
      
      if (ladderRes.code === 200) {
        setLadder(ladderRes.data.ladder || []);
      }
      if (statsRes.code === 200) {
        setStatistics(statsRes.data || {});
      }
    } catch (error) {
      console.error('加载连板天梯失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleStockClick = (code) => {
    window.location.href = `/stock/${code}`;
  };

  return (
    <div style={{ padding: 24 }}>
      {/* 标题和日期选择 */}
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3} style={{ margin: 0, color: 'var(--text-primary)' }}>连板天梯</Title>
        <DatePicker 
          value={dayjs(date)} 
          onChange={(d) => setDate(d.format('YYYY-MM-DD'))}
          style={{ width: 160 }}
        />
      </div>

      <Spin spinning={loading}>
        {/* 市场统计 */}
        <div style={{ marginBottom: 20 }}>
          <MarketSentiment data={statistics} />
        </div>

        {/* 连板天梯 */}
        {ladder.length > 0 ? (
          <Row gutter={[16, 16]}>
            {ladder.map((level) => (
              <Col span={12} key={level.limit_times}>
                <LadderCard
                  level={level.limit_times}
                  count={level.count}
                  stocks={level.stocks}
                  onStockClick={handleStockClick}
                />
              </Col>
            ))}
          </Row>
        ) : (
          !loading && (
            <Card>
              <div className="empty-data">暂无连板数据</div>
            </Card>
          )
        )}
      </Spin>
    </div>
  );
};

export default Ladder;
