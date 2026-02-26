import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, Select, message, Popconfirm, Space, DatePicker, Radio } from 'antd';
import { PlusOutlined, DeleteOutlined, LineChartOutlined } from '@ant-design/icons';
import { stocksAPI } from '../services/api';
import IntradayChart from '../components/IntradayChart';
import dayjs from 'dayjs';

export default function StockPool() {
  const [loading, setLoading] = useState(false);
  const [stocks, setStocks] = useState([]);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [isChartVisible, setIsChartVisible] = useState(false);
  const [selectedStock, setSelectedStock] = useState(null);
  const [chartData, setChartData] = useState([]);
  const [chartLoading, setChartLoading] = useState(false);
  const [chartType, setChartType] = useState('intraday'); // intraday 或 daily
  const [selectedDate, setSelectedDate] = useState(dayjs());
  const [form] = Form.useForm();

  useEffect(() => {
    loadStocks();
  }, []);

  const loadStocks = async () => {
    setLoading(true);
    try {
      const res = await stocksAPI.getList();
      setStocks(res.data.stocks || []);
    } catch (error) {
      message.error('加载股票池失败');
    } finally {
      setLoading(false);
    }
  };

  const handleAdd = () => {
    setIsModalVisible(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      await stocksAPI.add(values);
      message.success('添加成功');
      setIsModalVisible(false);
      form.resetFields();
      loadStocks();
    } catch (error) {
      message.error(error.response?.data?.detail || '添加失败');
    }
  };

  const handleDelete = async (code) => {
    try {
      await stocksAPI.delete(code);
      message.success('删除成功');
      loadStocks();
    } catch (error) {
      message.error('删除失败');
    }
  };

  const handleViewChart = async (stock) => {
    setSelectedStock(stock);
    setIsChartVisible(true);
    await loadChartData(stock, selectedDate.format('YYYY-MM-DD'), chartType);
  };

  const loadChartData = async (stock, date, type) => {
    setChartLoading(true);
    try {
      if (type === 'intraday') {
        // 获取分时数据
        const res = await stocksAPI.getIntraday(stock.code, date);
        setChartData(res.data.data || []);
      } else {
        // 日线数据暂不支持
        message.info('日线图功能开发中');
        setChartData([]);
      }
    } catch (error) {
      message.error('加载图表数据失败');
      setChartData([]);
    } finally {
      setChartLoading(false);
    }
  };

  const handleChartTypeChange = (e) => {
    const newType = e.target.value;
    setChartType(newType);
    if (selectedStock) {
      loadChartData(selectedStock, selectedDate.format('YYYY-MM-DD'), newType);
    }
  };

  const handleDateChange = (date) => {
    setSelectedDate(date);
    if (selectedStock) {
      loadChartData(selectedStock, date.format('YYYY-MM-DD'), chartType);
    }
  };

  const columns = [
    {
      title: '股票代码',
      dataIndex: 'code',
      key: 'code',
      width: 120,
    },
    {
      title: '股票名称',
      dataIndex: 'name',
      key: 'name',
      width: 150,
    },
    {
      title: '市场',
      dataIndex: 'market',
      key: 'market',
      width: 80,
      render: (market) => market === 'SZ' ? '深圳' : '上海',
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_, record) => (
        <Space>
          <Button 
            type="link" 
            icon={<LineChartOutlined />}
            onClick={() => handleViewChart(record)}
          >
            查看走势
          </Button>
          <Popconfirm
            title="确定删除这只股票吗？"
            onConfirm={() => handleDelete(record.code)}
            okText="确定"
            cancelText="取消"
          >
            <Button type="link" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>股票池管理（共 {stocks.length} 只）</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
          添加股票
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={stocks}
        rowKey="code"
        loading={loading}
        pagination={{
          pageSize: 20,
          showTotal: (total) => `共 ${total} 只股票`,
        }}
      />

      <Modal
        title="添加股票"
        open={isModalVisible}
        onOk={handleSubmit}
        onCancel={() => {
          setIsModalVisible(false);
          form.resetFields();
        }}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            label="股票代码"
            name="code"
            rules={[{ required: true, message: '请输入股票代码' }]}
          >
            <Input placeholder="例如：002342" />
          </Form.Item>
          <Form.Item
            label="股票名称"
            name="name"
            rules={[{ required: true, message: '请输入股票名称' }]}
          >
            <Input placeholder="例如：巨力索具" />
          </Form.Item>
          <Form.Item
            label="市场"
            name="market"
            rules={[{ required: true, message: '请选择市场' }]}
          >
            <Select>
              <Select.Option value="SZ">深圳</Select.Option>
              <Select.Option value="SH">上海</Select.Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      {/* 走势图弹窗 */}
      <Modal
        title={
          <Space>
            <span>个股走势</span>
            <Radio.Group value={chartType} onChange={handleChartTypeChange} size="small">
              <Radio.Button value="intraday">分时</Radio.Button>
              <Radio.Button value="daily">日线</Radio.Button>
            </Radio.Group>
            <DatePicker 
              value={selectedDate}
              onChange={handleDateChange}
              format="YYYY-MM-DD"
              size="small"
              allowClear={false}
            />
          </Space>
        }
        open={isChartVisible}
        onCancel={() => setIsChartVisible(false)}
        footer={null}
        width={900}
      >
        {chartLoading ? (
          <div style={{ textAlign: 'center', padding: '50px' }}>加载中...</div>
        ) : (
          selectedStock && (
            <IntradayChart 
              data={chartData}
              stockCode={selectedStock.code}
              stockName={selectedStock.name}
              date={selectedDate.format('YYYY-MM-DD')}
            />
          )
        )}
      </Modal>
    </div>
  );
}
