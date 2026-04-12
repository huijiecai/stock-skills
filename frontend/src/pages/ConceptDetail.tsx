import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Table, Tag, Spin, Typography, Breadcrumb, Button } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { conceptAPI } from '../services/api';
import type { ConceptComponentItem } from '../types';

const { Title, Text } = Typography;

const ConceptDetail: React.FC = () => {
  const { code } = useParams<{ code: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [conceptName, setConceptName] = useState('');
  const [components, setComponents] = useState<ConceptComponentItem[]>([]);

  useEffect(() => {
    if (code) loadConceptData();
  }, [code]);

  const loadConceptData = async () => {
    if (!code) return;
    
    setLoading(true);
    try {
      const res = await conceptAPI.getComponents(code);
      if (res.code === 200 && res.data) {
        setConceptName(res.data.concept_code || code);
        setComponents(res.data.items || []);
      }
    } catch (error) {
      console.error('加载板块数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const columns = [
    {
      title: '排名',
      key: 'rank',
      width: 80,
      render: (_: any, __: any, index: number) => index + 1,
    },
    {
      title: '股票代码',
      dataIndex: 'stock_code',
      key: 'stock_code',
      width: 120,
      render: (code: string) => (
        <Button type="link" onClick={() => navigate(`/stock/${code}`)}>
          {code}
        </Button>
      ),
    },
    {
      title: '股票名称',
      dataIndex: 'stock_name',
      key: 'stock_name',
      width: 120,
    },
    {
      title: '核心',
      dataIndex: 'is_core',
      key: 'is_core',
      width: 80,
      render: (isCore: boolean) => (
        isCore ? <Tag color="red">核心</Tag> : <Tag>普通</Tag>
      ),
    },
    {
      title: '入选原因',
      dataIndex: 'reason',
      key: 'reason',
      ellipsis: true,
    },
  ];

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px' }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div style={{ padding: 24 }}>
      <Breadcrumb style={{ marginBottom: 16 }}>
        <Breadcrumb.Item>
          <span onClick={() => navigate('/concept-rank')} style={{ cursor: 'pointer' }}>
            板块排行
          </span>
        </Breadcrumb.Item>
        <Breadcrumb.Item>{conceptName}</Breadcrumb.Item>
      </Breadcrumb>

      <Button 
        icon={<ArrowLeftOutlined />} 
        onClick={() => navigate('/concept-rank')}
        style={{ marginBottom: 16 }}
      >
        返回板块列表
      </Button>

      <Card title={`板块详情 - ${conceptName}`} style={{ marginBottom: 16 }}>
        <Text>成分股数量: {components.length} 只</Text>
      </Card>

      <Card title="成分股列表">
        <Table
          columns={columns}
          dataSource={components}
          rowKey="stock_code"
          pagination={{ pageSize: 20 }}
          size="small"
        />
      </Card>
    </div>
  );
};

export default ConceptDetail;
