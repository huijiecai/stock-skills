import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ContinuousBoardLevel } from '../../types';

interface ContinuousBoardProps {
  ladder: ContinuousBoardLevel[];
  loading?: boolean;
}

/**
 * 连板天梯组件
 */
export const ContinuousBoard: React.FC<ContinuousBoardProps> = ({ 
  ladder, 
  loading = false 
}) => {
  const navigate = useNavigate();

  const getLevelStyle = (limitTimes: number) => {
    if (limitTimes >= 5) return 'high';
    if (limitTimes >= 3) return 'mid';
    return 'normal';
  };

  const handleStockClick = (code: string) => {
    navigate(`/stock/${code}`);
  };

  if (loading) {
    return <div className="loading">加载中...</div>;
  }

  if (!ladder || ladder.length === 0) {
    return <div className="empty-data">暂无连板数据</div>;
  }

  return (
    <div className="continuous-board">
      {ladder.map((level) => (
        <div 
          key={level.limit_times} 
          className={`ladder-level ${getLevelStyle(level.limit_times) === 'high' ? 'level-high' : ''}`}
        >
          <div className="ladder-header">
            <span className={`ladder-tag ${getLevelStyle(level.limit_times)}`}>
              {level.level}
            </span>
            <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
              共 {level.count} 只
            </span>
          </div>
          <div className="ladder-stocks">
            {level.stocks.map((stock) => (
              <div 
                key={stock.stock_code} 
                className="stock-row"
                onClick={() => handleStockClick(stock.stock_code)}
              >
                <span className="stock-code">{stock.stock_code}</span>
                <span className="stock-name">{stock.stock_name}</span>
                <span className="stock-change up">
                  +{stock.change_pct?.toFixed(2)}%
                </span>
                <span className="stock-time">{stock.first_time}</span>
                {stock.is_broken && (
                  <span className="stock-broken">炸板</span>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};

export default ContinuousBoard;
