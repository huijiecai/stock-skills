import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Spin, Button, Modal, Form, InputNumber, Input, message, Typography, Tabs } from 'antd';
import { ReloadOutlined, PlusOutlined } from '@ant-design/icons';
import { accountAPI } from '../services/api';
import { AccountInfo, PositionTable } from '../components';
import type { AccountInfo as AccountInfoType, Position, TradeRecord } from '../types';

const { Title } = Typography;
const { TabPane } = Tabs;

const Account: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [accountInfo, setAccountInfo] = useState<AccountInfoType | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [trades, setTrades] = useState<TradeRecord[]>([]);
  const [tradeModalVisible, setTradeModalVisible] = useState(false);
  const [form] = Form.useForm();

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [infoRes, posRes, tradeRes] = await Promise.all([
        accountAPI.getInfo(),
        accountAPI.getPositions(),
        accountAPI.getTrades(undefined, undefined, 1, 20),
      ]);
      
      if (infoRes.code === 200) setAccountInfo(infoRes.data);
      if (posRes.code === 200) {
        setPositions(posRes.data.items || []);
      }
      if (tradeRes.code === 200) setTrades(tradeRes.data.items || []);
    } catch (error) {
      console.error('加载数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdatePrices = async () => {
    try {
      const res = await accountAPI.updatePositionPrices();
      if (res.code === 200) {
        message.success('持仓价格已更新');
        loadData();
      }
    } catch (error) {
      message.error('更新失败');
    }
  };

  const handleTrade = async (values: any) => {
    try {
      const res = await accountAPI.executeTrade(
        values.stock_code,
        values.action,
        values.price,
        values.quantity,
        values.reason
      );
      if (res.code === 200) {
        message.success(`${values.action === 'buy' ? '买入' : '卖出'}成功`);
        setTradeModalVisible(false);
        form.resetFields();
        loadData();
      } else {
        message.error(res.message);
      }
    } catch (error) {
      message.error('交易失败');
    }
  };

  const tradeColumns = [
    { title: '时间', dataIndex: 'trade_time', width: 160 },
    { title: '代码', dataIndex: 'stock_code', width: 80 },
    { title: '名称', dataIndex: 'stock_name', width: 100 },
    { 
      title: '操作', 
      dataIndex: 'action', 
      width: 60,
      render: (v: string) => (
        <span style={{ color: v === 'buy' ? 'var(--color-up)' : 'var(--color-down)' }}>
          {v === 'buy' ? '买入' : '卖出'}
        </span>
      )
    },
    { title: '价格', dataIndex: 'price', width: 80, render: (v: number) => v?.toFixed(2) },
    { title: '数量', dataIndex: 'quantity', width: 80 },
    { title: '金额', dataIndex: 'amount', width: 100, render: (v: number) => v?.toLocaleString() },
    { title: '原因', dataIndex: 'reason', ellipsis: true },
  ];

  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3} style={{ margin: 0 }}>我的账户</Title>
        <div>
          <Button icon={<ReloadOutlined />} onClick={handleUpdatePrices} style={{ marginRight: 8 }}>
            更新价格
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setTradeModalVisible(true)}>
            交易
          </Button>
        </div>
      </div>

      <Spin spinning={loading}>
        <div style={{ marginBottom: 16 }}>
          <AccountInfo data={accountInfo} loading={loading} />
        </div>

        <Card>
          <Tabs defaultActiveKey="positions">
            <TabPane tab="持仓" key="positions">
              <PositionTable data={positions} loading={false} />
            </TabPane>
            <TabPane tab="交易记录" key="trades">
              <table className="trades-table">
                <thead>
                  <tr>
                    {tradeColumns.map(col => (
                      <th key={col.dataIndex} style={{ width: col.width }}>
                        {col.title}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {trades.map(trade => (
                    <tr key={trade.trade_id}>
                      <td>{trade.trade_time}</td>
                      <td>{trade.stock_code}</td>
                      <td>{trade.stock_name}</td>
                      <td style={{ color: trade.action === 'buy' ? 'var(--color-up)' : 'var(--color-down)' }}>
                        {trade.action === 'buy' ? '买入' : '卖出'}
                      </td>
                      <td>{trade.price?.toFixed(2)}</td>
                      <td>{trade.quantity}</td>
                      <td>{trade.amount?.toLocaleString()}</td>
                      <td>{trade.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {trades.length === 0 && <div className="empty-data">暂无交易记录</div>}
            </TabPane>
          </Tabs>
        </Card>
      </Spin>

      <Modal
        title="交易"
        open={tradeModalVisible}
        onCancel={() => setTradeModalVisible(false)}
        onOk={() => form.submit()}
      >
        <Form form={form} layout="vertical" onFinish={handleTrade}>
          <Form.Item name="action" label="操作" rules={[{ required: true }]}>
            <div>
              <Button 
                style={{ marginRight: 8 }} 
                type={form.getFieldValue('action') === 'buy' ? 'primary' : 'default'}
                danger
                onClick={() => form.setFieldValue('action', 'buy')}
              >
                买入
              </Button>
              <Button 
                type={form.getFieldValue('action') === 'sell' ? 'primary' : 'default'}
                onClick={() => form.setFieldValue('action', 'sell')}
              >
                卖出
              </Button>
            </div>
          </Form.Item>
          <Form.Item name="stock_code" label="股票代码" rules={[{ required: true }]}>
            <Input placeholder="请输入股票代码" />
          </Form.Item>
          <Form.Item name="price" label="价格" rules={[{ required: true }]}>
            <InputNumber min={0.01} step={0.01} style={{ width: '100%' }} placeholder="请输入价格" />
          </Form.Item>
          <Form.Item name="quantity" label="数量" rules={[{ required: true }]}>
            <InputNumber min={100} step={100} style={{ width: '100%' }} placeholder="请输入数量（100股起）" />
          </Form.Item>
          <Form.Item name="reason" label="原因">
            <Input.TextArea rows={2} placeholder="交易原因（可选）" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default Account;
