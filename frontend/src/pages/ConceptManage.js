import React, { useState, useEffect } from 'react';
import { Row, Col, Tree, Table, Button, Modal, Form, Input, Checkbox, message, Spin } from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import { conceptsAPI } from '../services/api';

export default function ConceptManage() {
  const [loading, setLoading] = useState(true);
  const [concepts, setConcepts] = useState({});
  const [treeData, setTreeData] = useState([]);
  const [selectedConcept, setSelectedConcept] = useState(null);
  const [conceptStocks, setConceptStocks] = useState([]);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [form] = Form.useForm();

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
        children: Object.entries(value.subconcepts || {}).map(([subKey, subValue]) => ({
          title: `${subKey} - ${subValue.description}`,
          key: subKey,
          conceptName: subKey,
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
      setConceptStocks(res.data.stocks || []);
    } catch (error) {
      message.error('加载股票列表失败');
    }
  };

  const handleSelect = (selectedKeys, info) => {
    if (selectedKeys.length > 0 && info.node.conceptName) {
      setSelectedConcept(info.node.conceptName);
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
    try {
      await conceptsAPI.removeStock(selectedConcept, stockCode);
      message.success('移除成功');
      loadConceptStocks(selectedConcept);
    } catch (error) {
      message.error('移除失败');
    }
  };

  const columns = [
    {
      title: '股票代码',
      dataIndex: 'stock_code',
      key: 'stock_code',
      width: 120,
    },
    {
      title: '是否核心',
      dataIndex: 'is_core',
      key: 'is_core',
      width: 100,
      render: (isCore) => (isCore ? '核心' : '相关'),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_, record) => (
        <Button
          type="link"
          danger
          icon={<DeleteOutlined />}
          onClick={() => handleRemove(record.stock_code)}
        >
          移除
        </Button>
      ),
    },
  ];

  if (loading) {
    return <div style={{ textAlign: 'center', padding: '100px' }}><Spin size="large" /></div>;
  }

  return (
    <div>
      <h2>概念管理</h2>
      <Row gutter={24}>
        <Col span={8}>
          <div style={{ background: '#fff', padding: 16, minHeight: 600 }}>
            <h3>概念树</h3>
            <Tree
              treeData={treeData}
              onSelect={handleSelect}
              defaultExpandAll
            />
          </div>
        </Col>
        <Col span={16}>
          <div style={{ background: '#fff', padding: 16, minHeight: 600 }}>
            <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3>
                {selectedConcept ? `${selectedConcept} - 股票列表（${conceptStocks.length}只）` : '请选择概念'}
              </h3>
              {selectedConcept && (
                <Button type="primary" icon={<PlusOutlined />} onClick={handleAddStock}>
                  添加股票
                </Button>
              )}
            </div>
            {selectedConcept && (
              <Table
                columns={columns}
                dataSource={conceptStocks}
                rowKey="stock_code"
                pagination={false}
              />
            )}
          </div>
        </Col>
      </Row>

      <Modal
        title={`添加股票到 ${selectedConcept}`}
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
            name="stock_code"
            rules={[{ required: true, message: '请输入股票代码' }]}
          >
            <Input placeholder="例如：002342" />
          </Form.Item>
          <Form.Item name="is_core" valuePropName="checked">
            <Checkbox>核心标的</Checkbox>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
