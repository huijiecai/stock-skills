import React from 'react';
import CountUp from 'react-countup';
import { MarketSnapshot } from '../../types';

interface MarketSentimentProps {
  data?: MarketSnapshot | null;
}

interface SentimentItem {
  label: string;
  value: number | string;
  type: 'up' | 'down' | 'warn' | 'normal';
}

/**
 * 市场情绪组件
 */
export const MarketSentiment: React.FC<MarketSentimentProps> = ({ data }) => {
  const safeData = data || {
    limit_up_count: 0,
    limit_down_count: 0,
    broken_board_count: 0,
    seal_rate: 0,
    date: ''
  };
  
  const items: SentimentItem[] = [
    { label: '涨停', value: safeData.limit_up_count || 0, type: 'up' },
    { label: '跌停', value: safeData.limit_down_count || 0, type: 'down' },
    { label: '炸板', value: safeData.broken_board_count || 0, type: 'warn' },
    { label: '封板率', value: `${safeData.seal_rate || 0}%`, type: 'normal' },
  ];

  if (safeData.max_continuous_board) {
    items.push({ 
      label: '最高连板', 
      value: `${safeData.max_continuous_board}板`, 
      type: 'warn' 
    });
  }

  return (
    <div className="sentiment-card">
      <div style={{ display: 'flex' }}>
        {items.map((item, idx) => (
          <div key={idx} className="sentiment-item">
            <div className="sentiment-label">{item.label}</div>
            <div className={`sentiment-value ${item.type}`}>
              {typeof item.value === 'number' ? (
                <CountUp end={item.value} duration={0.5} />
              ) : item.value}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default MarketSentiment;
