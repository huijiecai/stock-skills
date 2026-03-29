import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Statistic, Table, Tag, Spin, Button, Modal, Form, InputNumber, Input, message, Typography, Tabs, DatePicker } from 'antd';
import { ReloadOutlined, PlusOutlined, MinusOutlined } from '@ant-design/icons';
import { accountAPI } from '../services/api';
import dayjs from 'dayjs';

const { Title } = Typography;
const { TabPane } = Tabs;

const Account = () => {
  const [loading, setLoading] = useState(true);
  const [accountInfo, setAccountInfo] = useState(null);
  const [positions, setPositions] = useState([]);
  const [trades, setTrades] = useState([]);
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
        accountAPI.getTrades(null, null, 1, 20),
      ]);
      
      if (infoRes.code === 200) setAccountInfo(infoRes.data);
      if (posRes.code === 200) {
        setPositions(posRes.data.positions || []);
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

  const handleTrade = async (values) => {
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

  const posColumns = [
    { title: '代码', dataIndex: 'stock_code', width: 80 },
    { title: '名称', dataIndex: 'stock_name', width: 100 },
    { title: '持仓', dataIndex: 'quantity', width: 80 },
    { title: '成本', dataIndex: 'cost_price', width: 80, render: (v) => v?.toFixed(2) },
    { title: '现价', dataIndex: 'current_price', width: 80, render: (v) => v?.toFixed(2) },
    { 
      title: '市值', 
      dataIndex: 'market_value', 
      width: 100,
      render: (v) => v?.toLocaleString()
    },
    { 
      title: '盈亏', 
      dataIndex: 'profit', 
      width: 100,
      render: (v) => (
        <span style={{ color: v >= 0 ? 'red' : 'green' }}>
          {v >= 0 ? '+' : ''}{v?.toFixed(2)}
        </span>
      )
    },
    { 
      title: '盈亏%', 
      dataIndex: 'profit_pct', 
      width: 80,
      render: (v) => (
        <Tag color={v >= 0 ? 'red' : 'green'}>
          {v >= 0 ? '+' : ''}{v?.toFixed(2)}%
        </Tag>
      )
    },
  ];

  const tradeColumns = [
    { title: '时间', dataIndex: 'trade_time', width: 160 },
    { title: '代码', dataIndex: 'stock_code', width: 80 },
    { title: '名称', dataIndex: 'stock_name', width: 100 },
    { 
      title: '操作', 
      dataIndex: 'action', 
      width: 60,
      render: (v) => <Tag color={v === 'buy' ? 'red' : 'green'}>{v === 'buy' ? '买入' : '卖出'}</Tag>
    },
    { title: '价格', dataIndex: 'price', width: 80, render: (v) => v?.toFixed(2) },
    { title: '数量', dataIndex: 'quantity', width: 80 },
    { title: '金额', dataIndex: 'amount', width: 100, render: (v) => v?.toLocaleString() },
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
        {/* 账户概览 */}
        <Card style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            <Col span={4}>
              <Statistic title="总资产" value={accountInfo?.total_asset || 0} precision={2} />
            </Col>
            <Col span={4}>
              <Statistic title="可用资金" value={accountInfo?.available_cash || 0} precision={2} />
            </Col>
            <Col span={4}>
              <Statistic title="持仓市值" value={accountInfo?.market_value || 0} precision={2} />
            </Col>
            <Col span={4}>
              <Statistic
                title="总盈亏"
                value={accountInfo?.total_profit || 0}
                precision={2}
                valueStyle={{ color: (accountInfo?.total_profit || 0) >= 0 ? '#cf1322' : '#3f8600' }}
              />
            </Col>
            <Col span={4}>
              <Statistic
                title="收益率"
                value={accountInfo?.total_profit_pct || 0}
                precision={2}
                suffix="%"
                valueStyle={{ color: (accountInfo?.total_profit_pct || 0) >= 0 ? '#cf1322' : '#3f8600' }}
              />
            </Col>
          </Row>
        </Card>

        <Tabs defaultActiveKey="positions">
          <TabPane tab="持仓" key="positions">
            <Table
              columns={posColumns}
              dataSource={positions}
              rowKey="position_id"
              pagination={false}
              size="small"
              summary={() => (
                <Table.Summary.Row>
                  <Table.Summary.Cell index={0} colSpan={5}>合计</Table.Summary.Cell>
                  <Table.Summary.Cell index={1}>
                    {positions.reduce((sum, p) => sum + (p.market_value || 0), 0).toLocaleString()}
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={2} colSpan={2}>
                    <span style={{ color: positions.reduce((sum, p) => sum + (p.profit || 0), 0) >= 0 ? 'red' : 'green' }}>
                      {positions.reduce((sum, p) => sum + (p.profit || 0), 0).toFixed(2)}
                    </span>
                  </Table.Summary.Cell>
                </Table.Summary.Row>
              )}
            />
          </TabPane>
          <TabPane tab="交易记录" key="trades">
            <Table
              columns={tradeColumns}
              dataSource={trades}
              rowKey="trade_id"
              pagination={{ pageSize: 20 }}
              size="small"
            />
          </TabPane>
        </Tabs>
      </Spin>

      {/* 交易弹窗 */}
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
