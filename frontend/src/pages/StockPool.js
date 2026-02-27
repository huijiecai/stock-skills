import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, Select, message, Space, Tag, Tooltip, Radio, Statistic, Row, Col, Card } from 'antd';
import { PlusOutlined, LineChartOutlined, SearchOutlined, ReloadOutlined, FilterOutlined, ClearOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { stocksAPI } from '../services/api';

export default function StockPool() {
  const [loading, setLoading] = useState(false);
  const [stocks, setStocks] = useState([]);
  const [filteredStocks, setFilteredStocks] = useState([]);
  const [quotesMap, setQuotesMap] = useState({});
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [changeFilter, setChangeFilter] = useState('all'); // all, up, down, limit_up
  const [form] = Form.useForm();
  const navigate = useNavigate();

  useEffect(() => {
    loadStocks();
  }, []);

  useEffect(() => {
    // 搜索和筛选过滤
    let filtered = stocks;
    
    // 文本搜索
    if (searchText.trim()) {
      const text = searchText.toLowerCase();
      filtered = filtered.filter(stock => 
        stock.code.toLowerCase().includes(text) || 
        stock.name.toLowerCase().includes(text)
      );
    }
    
    // 涨跌幅筛选
    if (changeFilter !== 'all') {
      filtered = filtered.filter(stock => {
        const quote = quotesMap[stock.code];
        if (!quote) return false;
        
        if (changeFilter === 'up') return quote.change_percent > 0;
        if (changeFilter === 'down') return quote.change_percent < 0;
        if (changeFilter === 'limit_up') return quote.change_percent >= 0.095; // 接近涨停
        return true;
      });
    }
    
    setFilteredStocks(filtered);
  }, [searchText, changeFilter, stocks, quotesMap]);

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

  const handleClearFilters = () => {
    setSearchText('');
    setChangeFilter('all');
  };

  // 计算统计数据
  const getStatistics = () => {
    const upCount = stocks.filter(s => {
      const quote = quotesMap[s.code];
      return quote && quote.change_percent > 0;
    }).length;
    
    const downCount = stocks.filter(s => {
      const quote = quotesMap[s.code];
      return quote && quote.change_percent < 0;
    }).length;
    
    const limitUpCount = stocks.filter(s => {
      const quote = quotesMap[s.code];
      return quote && quote.change_percent >= 0.095;
    }).length;
    
    return { upCount, downCount, limitUpCount };
  };

  const stats = getStatistics();

  // 格式化数值（注释掉未使用的函数以避免警告）
  // const formatNumber = (num) => {
  //   if (num === null || num === undefined) return '-';
  //   if (num >= 100000000) {
  //     return (num / 100000000).toFixed(2) + '亿';
  //   }
  //   if (num >= 10000) {
  //     return (num / 10000).toFixed(2) + '万';
  //   }
  //   return num.toFixed(2);
  // };

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
        <Button 
          type="link" 
          onClick={() => handleViewDetail({ code })} 
          style={{ padding: 0, height: 'auto' }}
        >
          {code}
        </Button>
      ),
    },
    {
      title: '股票名称',
      dataIndex: 'name',
      key: 'name',
      width: 120,
      render: (name, record) => (
        <Button 
          type="link" 
          onClick={() => handleViewDetail(record)} 
          style={{ padding: 0, height: 'auto', fontWeight: 'bold' }}
        >
          {name}
        </Button>
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
      <div style={{ marginBottom: 16 }}>
        <h2>股票池管理</h2>
        
        {/* 统计信息 */}
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <Card size="small">
              <Statistic title="总股票数" value={stocks.length} suffix="只" />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic 
                title="上涨" 
                value={stats.upCount} 
                valueStyle={{ color: '#cf1322' }}
                suffix="只" 
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic 
                title="下跌" 
                value={stats.downCount}
                valueStyle={{ color: '#3f8600' }}
                suffix="只" 
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic 
                title="涨停" 
                value={stats.limitUpCount}
                valueStyle={{ color: '#cf1322' }}
                suffix="只" 
              />
            </Card>
          </Col>
        </Row>

        {/* 操作栏 */}
        <Space size="middle" style={{ width: '100%', justifyContent: 'space-between' }}>
          <Space>
            <Input
              placeholder="搜索股票代码或名称"
              prefix={<SearchOutlined />}
              value={searchText}
              onChange={handleSearch}
              style={{ width: 250 }}
              allowClear
            />
            <Radio.Group 
              value={changeFilter} 
              onChange={(e) => setChangeFilter(e.target.value)}
              buttonStyle="solid"
            >
              <Radio.Button value="all">
                全部 <Tag>{stocks.length}</Tag>
              </Radio.Button>
              <Radio.Button value="up">
                <span style={{ color: '#cf1322' }}>上涨 {stats.upCount}</span>
              </Radio.Button>
              <Radio.Button value="down">
                <span style={{ color: '#3f8600' }}>下跌 {stats.downCount}</span>
              </Radio.Button>
              <Radio.Button value="limit_up">
                <span style={{ color: '#cf1322' }}>涨停 {stats.limitUpCount}</span>
              </Radio.Button>
            </Radio.Group>
            <Tooltip title="清除筛选">
              <Button 
                icon={<ClearOutlined />} 
                onClick={handleClearFilters}
                disabled={searchText === '' && changeFilter === 'all'}
              >
                清除
              </Button>
            </Tooltip>
          </Space>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadStocks} loading={loading}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
              添加股票
            </Button>
          </Space>
        </Space>
        
        {filteredStocks.length < stocks.length && (
          <div style={{ marginTop: 8 }}>
            <Tag color="blue">
              <FilterOutlined /> 已筛选 {filteredStocks.length} / {stocks.length} 只股票
            </Tag>
          </div>
        )}
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
