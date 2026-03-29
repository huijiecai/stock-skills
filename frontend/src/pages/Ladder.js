import React, { useState, useEffect } from 'react';
import { DatePicker, Spin, Typography, Tooltip } from 'antd';
import { marketAPI } from '../services/api';
import dayjs from 'dayjs';
import './Ladder.css';

const { Title, Text } = Typography;

const Ladder = () => {
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState(null);
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

  // 市场统计数据
  const statItems = [
    { label: '涨停', value: statistics.limit_up_count || 0, color: 'up' },
    { label: '跌停', value: statistics.limit_down_count || 0, color: 'down' },
    { label: '炸板', value: statistics.broken_board_count || 0, color: 'warn' },
    { label: '封板率', value: `${statistics.seal_rate || 0}%`, color: 'normal' },
  ];

  return (
    <div className="ladder-page">
      {/* 标题栏 */}
      <div className="ladder-header">
        <Title level={3} className="ladder-title">连板天梯</Title>
        <DatePicker 
          value={date ? dayjs(date) : null}
          onChange={(d) => setDate(d ? d.format('YYYY-MM-DD') : null)}
          style={{ width: 140 }}
        />
      </div>

      <Spin spinning={loading}>
        {/* 市场统计卡片 */}
        <div className="stat-cards">
          {statItems.map((item, idx) => (
            <div key={idx} className={`stat-card stat-card-${item.color}`}>
              <div className="stat-value">{item.value}</div>
              <div className="stat-label">{item.label}</div>
            </div>
          ))}
        </div>

        {/* 连板天梯列表 */}
        <div className="ladder-list">
          {ladder.length > 0 ? (
            ladder.map((level) => (
              <div key={level.limit_times} className="ladder-level">
                {/* 左侧：连板数和数量 */}
                <div className="ladder-level-left">
                  <div className={`ladder-level-num ${level.limit_times >= 3 ? 'high' : ''}`}>
                    {level.limit_times}板
                  </div>
                  <div className="ladder-level-count">
                    <span className="count-num">{level.count}</span>
                    <span className="count-unit">只</span>
                  </div>
                </div>
                
                {/* 右侧：股票列表 */}
                <div className="ladder-stocks">
                  {level.stocks?.slice(0, 10).map((stock, idx) => (
                    <Tooltip key={idx} title={stock.stock_name}>
                      <span 
                        className="stock-tag"
                        onClick={() => handleStockClick(stock.stock_code)}
                      >
                        {stock.stock_name}
                      </span>
                    </Tooltip>
                  ))}
                  {level.stocks?.length > 10 && (
                    <span className="stock-more">+{level.stocks.length - 10}</span>
                  )}
                </div>
              </div>
            ))
          ) : (
            !loading && (
              <div className="empty-ladder">
                <Text type="secondary">暂无连板数据</Text>
              </div>
            )
          )}
        </div>
      </Spin>
    </div>
  );
};

export default Ladder;
