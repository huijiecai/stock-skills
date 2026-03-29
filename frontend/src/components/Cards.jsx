import React from 'react';
import CountUp from 'react-countup';

/**
 * 统计卡片组件 - 带发光效果
 */
export const StatCard = ({ 
  title, 
  value, 
  suffix = '', 
  prefix = '',
  type = 'normal', // 'up' | 'down' | 'warn' | 'normal'
  icon = null,
  onClick = null
}) => {
  const typeColors = {
    up: { color: '#26A69A', glow: '0 0 20px rgba(38, 166, 154, 0.3)' },
    down: { color: '#EF5350', glow: '0 0 20px rgba(239, 83, 80, 0.3)' },
    warn: { color: '#FFA726', glow: '0 0 20px rgba(255, 167, 38, 0.3)' },
    normal: { color: '#D1D4DC', glow: 'none' }
  };

  const { color, glow } = typeColors[type] || typeColors.normal;

  return (
    <div 
      className="stat-card"
      style={{
        background: 'var(--bg-card)',
        border: `1px solid ${type === 'normal' ? 'var(--border-color)' : color}`,
        borderRadius: 8,
        padding: '16px 20px',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'all 0.3s ease',
        boxShadow: type !== 'normal' ? glow : 'none'
      }}
      onClick={onClick}
    >
      <div style={{ 
        color: 'var(--text-secondary)', 
        fontSize: 13,
        marginBottom: 8,
        display: 'flex',
        alignItems: 'center',
        gap: 8
      }}>
        {icon}
        {title}
      </div>
      <div style={{ 
        fontSize: 24, 
        fontWeight: 600,
        fontFamily: 'var(--font-mono)',
        color: color
      }}>
        {prefix}
        {typeof value === 'number' ? (
          <CountUp end={value} duration={0.5} separator="," />
        ) : value}
        {suffix}
      </div>
    </div>
  );
};

/**
 * 指数卡片组件
 */
export const IndexCard = ({ 
  code, 
  name, 
  close, 
  changePct, 
  amount,
  onClick,
  active = false
}) => {
  const isUp = changePct >= 0;
  
  return (
    <div 
      className={`index-card ${isUp ? 'up' : 'down'}`}
      style={{
        background: 'var(--bg-card)',
        border: active ? `1px solid ${isUp ? '#26A69A' : '#EF5350'}` : '1px solid var(--border-color)',
        borderRadius: 8,
        padding: '16px 20px',
        cursor: 'pointer',
        transition: 'all 0.3s ease',
        boxShadow: active ? (isUp ? 'var(--glow-up)' : 'var(--glow-down)') : 'none'
      }}
      onClick={onClick}
    >
      <div className="index-name">{name}</div>
      <div className="index-value" style={{ color: isUp ? '#26A69A' : '#EF5350' }}>
        <CountUp end={close} duration={0.5} decimals={2} separator="," />
      </div>
      <div className={`index-change ${isUp ? 'up' : 'down'}`}>
        {isUp ? '+' : ''}{changePct?.toFixed(2)}%
      </div>
      {amount && (
        <div className="index-amount">成交: {(amount / 1e8).toFixed(0)}亿</div>
      )}
    </div>
  );
};

/**
 * 市场情绪组件
 */
export const MarketSentiment = ({ data = {} }) => {
  const items = [
    { label: '涨停', value: data.limit_up_count || 0, type: 'up' },
    { label: '跌停', value: data.limit_down_count || 0, type: 'down' },
    { label: '炸板', value: data.broken_board_count || 0, type: 'warn' },
    { label: '封板率', value: `${data.seal_rate || 0}%`, type: 'normal' },
  ];

  if (data.max_continuous_board) {
    items.push({ label: '最高连板', value: `${data.max_continuous_board}板`, type: 'warn' });
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

/**
 * 连板天梯卡片
 */
export const LadderCard = ({ level, count, stocks = [], onStockClick }) => {
  const getLevelStyle = () => {
    if (level >= 5) return 'high';
    if (level >= 3) return 'mid';
    return 'normal';
  };

  return (
    <div className={`ladder-level ${getLevelStyle() === 'high' ? 'level-high' : ''}`}>
      <div className="ladder-header">
        <span className={`ladder-tag ${getLevelStyle()}`}>
          {level}板
        </span>
        <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
          共 {count} 只
        </span>
      </div>
      <div>
        {stocks.map((stock, idx) => (
          <div 
            key={idx} 
            className="stock-row"
            onClick={() => onStockClick?.(stock.stock_code)}
          >
            <span className="stock-code">{stock.stock_code}</span>
            <span className="stock-name">{stock.stock_name}</span>
            <span className="stock-change up">
              +{stock.change_pct?.toFixed(2)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default { StatCard, IndexCard, MarketSentiment, LadderCard };
