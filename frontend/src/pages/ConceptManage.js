import React, { useState, useEffect } from 'react';
import { Row, Col, Tree, Table, Button, Modal, Form, Input, Checkbox, message, Spin, Card, Space, Tag, Typography, Empty, Tooltip, Badge } from 'antd';
import { PlusOutlined, DeleteOutlined, AppstoreOutlined, BranchesOutlined, InfoCircleOutlined, SearchOutlined, DownloadOutlined } from '@ant-design/icons';
import { conceptsAPI } from '../services/api';

const { Title, Text, Paragraph } = Typography;
const { Search } = Input;

export default function ConceptManage() {
  const [loading, setLoading] = useState(true);
  const [concepts, setConcepts] = useState({});
  const [treeData, setTreeData] = useState([]);
  const [selectedConcept, setSelectedConcept] = useState(null);
  const [selectedConceptInfo, setSelectedConceptInfo] = useState(null);
  const [conceptStocks, setConceptStocks] = useState([]);
  const [filteredStocks, setFilteredStocks] = useState([]);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [treeSearchText, setTreeSearchText] = useState('');
  const [expandedKeys, setExpandedKeys] = useState([]);
  const [autoExpandParent, setAutoExpandParent] = useState(true);
  const [form] = Form.useForm();

  useEffect(() => {
    // 股票列表搜索过滤
    if (!searchText.trim()) {
      setFilteredStocks(conceptStocks);
    } else {
      const text = searchText.toLowerCase();
      const filtered = conceptStocks.filter(stock => 
        stock.stock_code.toLowerCase().includes(text) || 
        stock.stock_name?.toLowerCase().includes(text)
      );
      setFilteredStocks(filtered);
    }
  }, [searchText, conceptStocks]);

  // 概念树搜索
  useEffect(() => {
    if (treeSearchText) {
      const expandedKeys = [];
      const searchInTree = (data, parentKey = '') => {
        data.forEach(item => {
          if (item.title.toLowerCase().includes(treeSearchText.toLowerCase())) {
            if (parentKey) {
              expandedKeys.push(parentKey);
            }
          }
          if (item.children) {
            searchInTree(item.children, item.key);
          }
        });
      };
      searchInTree(treeData);
      setExpandedKeys(expandedKeys);
      setAutoExpandParent(true);
    } else {
      setExpandedKeys([]);
      setAutoExpandParent(false);
    }
  }, [treeSearchText, treeData]);

  useEffect(() => {
    loadConcepts();
  }, []);

  const loadConcepts = async () => {
    setLoading(true);
    try {
      const res = await conceptsAPI.getList();
      const conceptsData = res.data.data;
      setConcepts(conceptsData);
      
      // 转换为Tree组件需要的格式
      const formatted = Object.entries(conceptsData).map(([key, value]) => ({
        title: key,
        key: key,
        icon: <AppstoreOutlined />,
        description: value.description,
        children: Object.entries(value.subconcepts || {}).map(([subKey, subValue]) => ({
          title: subKey,
          key: subKey,
          icon: <BranchesOutlined />,
          conceptName: subKey,
          description: subValue.description,
        }))
      }));
      setTreeData(formatted);
    } catch (error) {
      message.error('加载概念失败');
    } finally {
      setLoading(false);
    }
  };

  const loadConceptStocks = async (conceptName) => {
    try {
      const res = await conceptsAPI.getStocks(conceptName);
      const stocks = res.data.stocks || [];
      setConceptStocks(stocks);
      setFilteredStocks(stocks);
    } catch (error) {
      message.error('加载股票列表失败');
    }
  };

  const handleExport = () => {
    if (!selectedConcept || conceptStocks.length === 0) {
      message.warning('没有可导出的数据');
      return;
    }
    
    // 构造CSV内容
    const headers = ['股票代码', '股票名称', '标的类型'];
    const rows = conceptStocks.map(stock => [
      stock.stock_code,
      stock.stock_name || '',
      stock.is_core ? '核心标的' : '相关标的'
    ]);
    
    const csvContent = [
      headers.join(','),
      ...rows.map(row => row.join(','))
    ].join('\n');
    
    // 创建下载链接
    const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `${selectedConcept}_股票列表.csv`;
    link.click();
    
    message.success('导出成功');
  };

  const handleSelect = (selectedKeys, info) => {
    if (selectedKeys.length > 0 && info.node.conceptName) {
      setSelectedConcept(info.node.conceptName);
      setSelectedConceptInfo(info.node);
      loadConceptStocks(info.node.conceptName);
    }
  };

  const handleAddStock = () => {
    if (!selectedConcept) {
      message.warning('请先选择一个概念');
      return;
    }
    setIsModalVisible(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      await conceptsAPI.addStock(selectedConcept, {
        stock_code: values.stock_code,
        is_core: values.is_core || false,
        note: selectedConcept,
      });
      message.success('添加成功');
      setIsModalVisible(false);
      form.resetFields();
      loadConceptStocks(selectedConcept);
    } catch (error) {
      message.error(error.response?.data?.detail || '添加失败');
    }
  };

  const handleRemove = async (stockCode) => {
    Modal.confirm({
      title: '确认移除',
      content: `确定要从 ${selectedConcept} 中移除股票 ${stockCode} 吗？`,
      onOk: async () => {
        try {
          await conceptsAPI.removeStock(selectedConcept, stockCode);
          message.success('移除成功');
          loadConceptStocks(selectedConcept);
        } catch (error) {
          message.error('移除失败');
        }
      },
    });
  };

  const columns = [
    {
      title: '股票代码',
      dataIndex: 'stock_code',
      key: 'stock_code',
      width: 120,
      render: (code) => <Text strong copyable>{code}</Text>,
    },
    {
      title: '股票名称',
      dataIndex: 'stock_name',
      key: 'stock_name',
      width: 150,
      render: (name) => <Text>{name || '-'}</Text>,
    },
    {
      title: '标签',
      dataIndex: 'is_core',
      key: 'is_core',
      width: 100,
      render: (isCore) => (
        <Tag color={isCore ? 'red' : 'blue'}>
          {isCore ? '核心标的' : '相关标的'}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_, record) => (
        <Button
          type="text"
          danger
          size="small"
          icon={<DeleteOutlined />}
          onClick={() => handleRemove(record.stock_code)}
        >
          移除
        </Button>
      ),
    },
  ];

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px' }}>
        <Spin size="large" tip="加载概念数据..." />
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <Title level={2}>
          <AppstoreOutlined style={{ marginRight: 8 }} />
          概念管理
        </Title>
        <Paragraph type="secondary">
          管理股票概念层级和股票归属关系
        </Paragraph>
      </div>

      <Row gutter={24}>
        {/* 左侧：概念树 */}
        <Col span={8}>
          <Card
            title={
              <Space>
                <BranchesOutlined />
                <span>概念层级树</span>
                <Badge count={Object.keys(concepts).length} showZero color="#1890ff" />
              </Space>
            }
            bordered={false}
            style={{ minHeight: 600 }}
          >
            <Search
              placeholder="搜索概念"
              value={treeSearchText}
              onChange={(e) => setTreeSearchText(e.target.value)}
              style={{ marginBottom: 12 }}
              allowClear
            />
            <Tree
              treeData={treeData}
              onSelect={handleSelect}
              showIcon
              style={{ fontSize: '14px' }}
              expandedKeys={expandedKeys}
              autoExpandParent={autoExpandParent}
              onExpand={(keys) => {
                setExpandedKeys(keys);
                setAutoExpandParent(false);
              }}
            />
          </Card>
        </Col>

        {/* 右侧：股票列表 */}
        <Col span={16}>
          <Card
            title={
              selectedConcept ? (
                <Space>
                  <BranchesOutlined />
                  <span>{selectedConcept}</span>
                  <Badge count={conceptStocks.length} showZero color="#52c41a" />
                </Space>
              ) : (
                <Space>
                  <InfoCircleOutlined />
                  <span>股票列表</span>
                </Space>
              )
            }
            bordered={false}
            style={{ minHeight: 600 }}
            extra={
              selectedConcept && (
                <Space>
                  <Search
                    placeholder="搜索股票"
                    value={searchText}
                    onChange={(e) => setSearchText(e.target.value)}
                    style={{ width: 200 }}
                    allowClear
                    size="small"
                  />
                  <Tooltip title="导出股票列表">
                    <Button
                      icon={<DownloadOutlined />}
                      onClick={handleExport}
                      size="small"
                    >
                      导出
                    </Button>
                  </Tooltip>
                  <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    onClick={handleAddStock}
                    size="small"
                  >
                    添加股票
                  </Button>
                </Space>
              )
            }
          >
            {selectedConcept ? (
              <>
                {selectedConceptInfo && (
                  <div style={{ 
                    marginBottom: 16, 
                    padding: 12, 
                    background: '#f5f5f5', 
                    borderRadius: 4 
                  }}>
                    <Text type="secondary">
                      <InfoCircleOutlined style={{ marginRight: 8 }} />
                      {selectedConceptInfo.description}
                    </Text>
                  </div>
                )}
                
                {filteredStocks.length > 0 ? (
                  <>
                    {filteredStocks.length < conceptStocks.length && (
                      <div style={{ marginBottom: 12 }}>
                        <Tag color="blue">
                          <SearchOutlined /> 已筛选 {filteredStocks.length} / {conceptStocks.length} 只股票
                        </Tag>
                      </div>
                    )}
                    <Table
                      columns={columns}
                      dataSource={filteredStocks}
                      rowKey="stock_code"
                      pagination={{
                        pageSize: 20,
                        showSizeChanger: false,
                        showTotal: (total) => `共 ${total} 只股票`,
                      }}
                      size="middle"
                    />
                  </>
                ) : (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={searchText ? "未找到匹配的股票" : "暂无股票，点击上方按钮添加"}
                  />
                )}
              </>
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="请从左侧概念树中选择一个概念"
                style={{ marginTop: 100 }}
              />
            )}
          </Card>
        </Col>
      </Row>

      {/* 添加股票对话框 */}
      <Modal
        title={
          <Space>
            <PlusOutlined />
            <span>添加股票到 {selectedConcept}</span>
          </Space>
        }
        open={isModalVisible}
        onOk={handleSubmit}
        onCancel={() => {
          setIsModalVisible(false);
          form.resetFields();
        }}
        okText="确定"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item
            label="股票代码"
            name="stock_code"
            rules={[
              { required: true, message: '请输入股票代码' },
              { pattern: /^\d{6}$/, message: '请输入6位数字股票代码' }
            ]}
          >
            <Input 
              placeholder="例如：002342" 
              maxLength={6}
              style={{ fontSize: '16px' }}
            />
          </Form.Item>
          <Form.Item name="is_core" valuePropName="checked">
            <Checkbox>
              <Space>
                <span>标记为核心标的</span>
                <Text type="secondary" style={{ fontSize: '12px' }}>
                  （核心标的优先级更高）
                </Text>
              </Space>
            </Checkbox>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
