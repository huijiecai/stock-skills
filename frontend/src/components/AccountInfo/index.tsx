import React from 'react';
import { Card, Row, Col, Statistic } from 'antd';
import { AccountInfo as AccountInfoType } from '../../types';

interface AccountInfoProps {
  data: AccountInfoType | null;
  loading?: boolean;
}

/**
 * 账户信息组件
 */
export const AccountInfo: React.FC<AccountInfoProps> = ({ data, loading = false }) => {
  if (!data) {
    return <div className="empty-data">暂无账户信息</div>;
  }

  const getProfitColor = (value: number) => {
    if (value > 0) return 'var(--color-up)';
    if (value < 0) return 'var(--color-down)';
    return 'var(--text-muted)';
  };

  return (
    <Card loading={loading}>
      <Row gutter={[16, 16]}>
        <Col span={6}>
          <Statistic 
            title="总资产" 
            value={data.total_asset} 
            precision={2}
            suffix="元"
          />
        </Col>
        <Col span={6}>
          <Statistic 
            title="可用资金" 
            value={data.available_cash} 
            precision={2}
            suffix="元"
          />
        </Col>
        <Col span={6}>
          <Statistic 
            title="持仓市值" 
            value={data.market_value} 
            precision={2}
            suffix="元"
          />
        </Col>
        <Col span={6}>
          <Statistic 
            title="累计收益" 
            value={data.total_profit} 
            precision={2}
            suffix="元"
            valueStyle={{ color: getProfitColor(data.total_profit) }}
            prefix={data.total_profit > 0 ? '+' : ''}
          />
        </Col>
      </Row>
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={24}>
          <div style={{ textAlign: 'center' }}>
            <span style={{ color: 'var(--text-secondary)' }}>累计收益率: </span>
            <span 
              style={{ 
                fontSize: 20, 
                fontWeight: 600,
                color: getProfitColor(data.total_profit)
              }}
            >
              {data.total_profit_pct > 0 ? '+' : ''}{data.total_profit_pct?.toFixed(2)}%
            </span>
          </div>
        </Col>
      </Row>
    </Card>
  );
};

export default AccountInfo;
