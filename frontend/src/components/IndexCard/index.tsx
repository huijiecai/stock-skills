import React from 'react';
import CountUp from 'react-countup';

interface IndexCardProps {
  code: string;
  name: string;
  close: number;
  changePct: number;
  amount?: number;
  onClick?: () => void;
  active?: boolean;
}

/**
 * 指数卡片组件
 */
export const IndexCard: React.FC<IndexCardProps> = ({ 
  code, 
  name, 
  close, 
  changePct, 
  amount,
  onClick,
  active = false
}) => {
  const getChangeColor = (v: number) => {
    if (v > 0) return 'var(--color-up)';
    if (v < 0) return 'var(--color-down)';
    return 'var(--text-muted)';
  };
  
  const color = getChangeColor(changePct);
  
  return (
    <div 
      className={`index-card ${changePct > 0 ? 'up' : changePct < 0 ? 'down' : 'flat'}`}
      style={{
        background: 'var(--bg-card)',
        border: active ? `1px solid ${color}` : '1px solid var(--border-color)',
        borderRadius: 8,
        padding: '16px 20px',
        cursor: 'pointer',
        transition: 'all 0.3s ease',
        boxShadow: active ? (changePct > 0 ? 'var(--glow-up)' : changePct < 0 ? 'var(--glow-down)' : 'none') : 'none'
      }}
      onClick={onClick}
    >
      <div className="index-name">{name}</div>
      <div className="index-value" style={{ color }}>
        <CountUp end={close} duration={0.5} decimals={2} separator="," />
      </div>
      <div className={`index-change ${changePct > 0 ? 'up' : changePct < 0 ? 'down' : 'flat'}`}>
        {changePct > 0 ? '+' : ''}{changePct?.toFixed(2)}%
      </div>
      {amount && (
        <div className="index-amount">成交: {(amount / 1e8).toFixed(0)}亿</div>
      )}
    </div>
  );
};

export default IndexCard;
