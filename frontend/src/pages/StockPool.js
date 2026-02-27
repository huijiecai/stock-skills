import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, Select, message, Space } from 'antd';
import { PlusOutlined, LineChartOutlined, SearchOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { stocksAPI } from '../services/api';

export default function StockPool() {
  const [loading, setLoading] = useState(false);
  const [stocks, setStocks] = useState([]);
  const [filteredStocks, setFilteredStocks] = useState([]);
  const [quotesMap, setQuotesMap] = useState({});
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [form] = Form.useForm();
  const navigate = useNavigate();

  useEffect(() => {
    loadStocks();
  }, []);

  useEffect(() => {
    // 搜索过滤
    if (!searchText.trim()) {
      setFilteredStocks(stocks);
    } else {
      const text = searchText.toLowerCase();
      const filtered = stocks.filter(stock => 
        stock.code.toLowerCase().includes(text) || 
        stock.name.toLowerCase().includes(text)
      );
      setFilteredStocks(filtered);
    }
  }, [searchText, stocks]);

  const loadStocks = async () => {
    setLoading(true);
    try {
      // 获取股票列表
      const res = await stocksAPI.getList();
      const stockList = res.data.stocks || [];
      setStocks(stockList);
      setFilteredStocks(stockList);

      // 批量获取行情
      if (stockList.length > 0) {
        const codes = stockList.map(s => s.code);
        const quotesRes = await stocksAPI.batchQuote(codes);
        
        // 转换为 Map 方便查询
        const map = {};
        (quotesRes.data.data || []).forEach(quote => {
          map[quote.code] = quote;
        });
        setQuotesMap(map);
      }
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

  const handleViewDetail = (stock) => {
    // 跳转到详情页
    navigate(`/stocks/${stock.code}`);
  };

  const handleSearch = (e) => {
    setSearchText(e.target.value);
  };

  // 格式化数值
  const formatNumber = (num) => {
    if (num === null || num === undefined) return '-';
    if (num >= 100000000) {
      return (num / 100000000).toFixed(2) + '亿';
    }
    if (num >= 10000) {
      return (num / 10000).toFixed(2) + '万';
    }
    return num.toFixed(2);
  };

  // 渲染涨跌幅
  const renderChangePercent = (value) => {
    if (value === null || value === undefined) return '-';
    const color = value >= 0 ? '#f5222d' : '#52c41a';
    const prefix = value >= 0 ? '+' : '';
    return <span style={{ color, fontWeight: 'bold' }}>{prefix}{(value * 100).toFixed(2)}%</span>;
  };

  // 渲染涨跌额
  const renderChange = (value) => {
    if (value === null || value === undefined) return '-';
    const color = value >= 0 ? '#f5222d' : '#52c41a';
    const prefix = value >= 0 ? '+' : '';
    return <span style={{ color }}>{prefix}{value.toFixed(2)}</span>;
  };

  // 渲染价格
  const renderPrice = (value) => {
    if (value === null || value === undefined) return '-';
    return value.toFixed(2);
  };

  const columns = [
    {
      title: '股票代码',
      dataIndex: 'code',
      key: 'code',
      width: 100,
      render: (code) => (
        <a onClick={() => handleViewDetail({ code })} style={{ color: '#1890ff', cursor: 'pointer' }}>
          {code}
        </a>
      ),
    },
    {
      title: '股票名称',
      dataIndex: 'name',
      key: 'name',
      width: 120,
      render: (name, record) => (
        <a onClick={() => handleViewDetail(record)} style={{ color: '#1890ff', cursor: 'pointer', fontWeight: 'bold' }}>
          {name}
        </a>
      ),
    },
    {
      title: '最新价',
      key: 'price',
      width: 100,
      align: 'right',
      render: (_, record) => {
        const quote = quotesMap[record.code];
        return quote ? renderPrice(quote.price) : '-';
      },
    },
    {
      title: '涨跌幅',
      key: 'change_percent',
      width: 100,
      align: 'right',
      render: (_, record) => {
        const quote = quotesMap[record.code];
        return quote ? renderChangePercent(quote.change_percent) : '-';
      },
      sorter: (a, b) => {
        const aQuote = quotesMap[a.code];
        const bQuote = quotesMap[b.code];
        return (aQuote?.change_percent || 0) - (bQuote?.change_percent || 0);
      },
    },
    {
      title: '涨跌额',
      key: 'change',
      width: 100,
      align: 'right',
      render: (_, record) => {
        const quote = quotesMap[record.code];
        return quote ? renderChange(quote.change) : '-';
      },
    },
    /* 隐藏成交量和成交额列，优先显示涨跌额
    {
      title: '成交量',
      key: 'volume',
      width: 120,
      align: 'right',
      render: (_, record) => {
        const quote = quotesMap[record.code];
        return quote ? formatNumber(quote.volume) : '-';
      },
    },
    {
      title: '成交额',
      key: 'turnover',
      width: 120,
      align: 'right',
      render: (_, record) => {
        const quote = quotesMap[record.code];
        return quote ? formatNumber(quote.turnover) : '-';
      },
    },
    {
      title: '市场',
      dataIndex: 'market',
      key: 'market',
      width: 80,
      render: (market) => market === 'SZ' ? '深圳' : '上海',
    },
    */
    {
      title: '操作',
      key: 'action',
      width: 100,
      fixed: 'right',
      render: (_, record) => (
        <Button 
          type="link" 
          icon={<LineChartOutlined />}
          onClick={() => handleViewDetail(record)}
        >
          详情
        </Button>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>股票池管理（共 {stocks.length} 只 {filteredStocks.length < stocks.length && `/ 已筛选 ${filteredStocks.length} 只`}）</h2>
        <Space>
          <Input
            placeholder="搜索股票代码或名称"
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={handleSearch}
            style={{ width: 250 }}
            allowClear
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
            添加股票
          </Button>
        </Space>
      </div>

      <Table
        columns={columns}
        dataSource={filteredStocks}
        rowKey="code"
        loading={loading}
        pagination={{
          pageSize: 10,
          showTotal: (total) => `共 ${total} 只股票`,
          showSizeChanger: true,
          pageSizeOptions: ['10', '20', '50', '100'],
        }}
        scroll={{ x: 800 }}
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
    </div>
  );
}
