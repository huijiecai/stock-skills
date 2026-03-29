import React, { useState, useEffect } from 'react';
import { Card, Table, Tag, Tabs, Spin, DatePicker, Input, Typography } from 'antd';
import { marketAPI } from '../services/api';
import dayjs from 'dayjs';

const { Title } = Typography;
const { TabPane } = Tabs;

const LimitUp = () => {
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState(dayjs().format('YYYY-MM-DD'));
  const [limitUpList, setLimitUpList] = useState([]);
  const [limitDownList, setLimitDownList] = useState([]);
  const [brokenList, setBrokenList] = useState([]);
  const [activeTab, setActiveTab] = useState('up');

  useEffect(() => {
    loadData();
  }, [date]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [upRes, downRes, brokenRes] = await Promise.all([
        marketAPI.getLimitUp(date, 1, 100),
        marketAPI.getLimitDown(date, 1, 100),
        marketAPI.getBrokenBoard(date, 1, 100),
      ]);
      
      if (upRes.code === 200) setLimitUpList(upRes.data.items || []);
      if (downRes.code === 200) setLimitDownList(downRes.data.items || []);
      if (brokenRes.code === 200) setBrokenList(brokenRes.data.items || []);
    } catch (error) {
      console.error('加载数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const columns = [
    { title: '代码', dataIndex: 'stock_code', width: 80 },
    { title: '名称', dataIndex: 'stock_name', width: 100 },
    { 
      title: '涨幅', 
      dataIndex: 'change_pct', 
      width: 90,
      render: (v) => <Tag color={v >= 0 ? 'red' : 'green'}>{v?.toFixed(2)}%</Tag>
    },
    { title: '首封时间', dataIndex: 'first_time', width: 90 },
    { title: '末封时间', dataIndex: 'last_time', width: 90 },
    { title: '连板', dataIndex: 'limit_times', width: 60, render: (v) => v ? `${v}板` : '-' },
    { title: '炸板次数', dataIndex: 'open_times', width: 80 },
  ];

  const brokenColumns = [
    { title: '代码', dataIndex: 'stock_code', width: 80 },
    { title: '名称', dataIndex: 'stock_name', width: 100 },
    { 
      title: '涨幅', 
      dataIndex: 'change_pct', 
      width: 90,
      render: (v) => <Tag color="orange">{v?.toFixed(2)}%</Tag>
    },
    { title: '首封时间', dataIndex: 'first_time', width: 90 },
    { title: '炸板时间', dataIndex: 'broken_time', width: 90 },
    { title: '炸板次数', dataIndex: 'open_times', width: 80 },
  ];

  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3} style={{ margin: 0 }}>涨跌停监控</Title>
        <DatePicker 
          value={dayjs(date)} 
          onChange={(d) => setDate(d.format('YYYY-MM-DD'))}
          style={{ width: 200 }}
        />
      </div>

      <Spin spinning={loading}>
        <Tabs activeKey={activeTab} onChange={setActiveTab}>
          <TabPane tab={`涨停 (${limitUpList.length})`} key="up">
            <Table
              columns={columns}
              dataSource={limitUpList}
              rowKey="stock_code"
              pagination={{ pageSize: 20 }}
              size="small"
            />
          </TabPane>
          <TabPane tab={`跌停 (${limitDownList.length})`} key="down">
            <Table
              columns={columns}
              dataSource={limitDownList}
              rowKey="stock_code"
              pagination={{ pageSize: 20 }}
              size="small"
            />
          </TabPane>
          <TabPane tab={`炸板 (${brokenList.length})`} key="broken">
            <Table
              columns={brokenColumns}
              dataSource={brokenList}
              rowKey="stock_code"
              pagination={{ pageSize: 20 }}
              size="small"
            />
          </TabPane>
        </Tabs>
      </Spin>
    </div>
  );
};

export default LimitUp;
