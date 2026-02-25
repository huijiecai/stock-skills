import React, { useState } from 'react';
import { Card, Form, Input, Button, Descriptions, Tag, Alert, Spin, DatePicker } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { analysisAPI } from '../services/api';
import dayjs from 'dayjs';

export default function Analysis() {
  const [loading, setLoading] = useState(false);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [form] = Form.useForm();

  const handleAnalyze = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);
      
      const date = values.date ? dayjs(values.date).format('YYYY-MM-DD') : dayjs().format('YYYY-MM-DD');
      const res = await analysisAPI.analyzeStock(values.code, date);
      
      if (res.data.success) {
        setAnalysisResult(res.data);
      } else {
        setAnalysisResult({ success: false, error: res.data.error });
      }
    } catch (error) {
      setAnalysisResult({ 
        success: false, 
        error: error.response?.data?.detail || '分析失败' 
      });
    } finally {
      setLoading(false);
    }
  };

  const getPhaseColor = (phase) => {
    if (phase === '冰点') return 'blue';
    if (phase === '主升') return 'red';
    return 'default';
  };

  return (
    <div>
      <h2>龙头战法分析</h2>
      
      <Card style={{ marginBottom: 24 }}>
        <Form form={form} layout="inline">
          <Form.Item
            label="股票代码"
            name="code"
            rules={[{ required: true, message: '请输入股票代码' }]}
          >
            <Input placeholder="例如：002342" style={{ width: 150 }} />
          </Form.Item>
          <Form.Item label="分析日期" name="date">
            <DatePicker placeholder="默认今天" />
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              icon={<SearchOutlined />}
              onClick={handleAnalyze}
              loading={loading}
            >
              开始分析
            </Button>
          </Form.Item>
        </Form>
      </Card>

      {loading && (
        <div style={{ textAlign: 'center', padding: '100px' }}>
          <Spin size="large" />
        </div>
      )}

      {!loading && analysisResult && (
        <>
          {!analysisResult.success ? (
            <Alert
              message="分析失败"
              description={analysisResult.error}
              type="error"
              showIcon
            />
          ) : (
            <Card 
              title={`${analysisResult.stock_name} (${analysisResult.stock_code}) - ${analysisResult.date}`}
              extra={
                <Tag color={analysisResult.is_leader_candidate ? 'success' : 'warning'}>
                  {analysisResult.is_leader_candidate ? '✅ 符合龙头标准' : '⚠️ 不符合龙头标准'}
                </Tag>
              }
            >
              <Descriptions bordered column={2}>
                <Descriptions.Item label="市场阶段">
                  <Tag color={getPhaseColor(analysisResult.market_phase)}>
                    {analysisResult.market_phase}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="人气排名">
                  {analysisResult.popularity_rank ? (
                    <span style={{ color: analysisResult.popularity_rank <= 30 ? '#cf1322' : '#000' }}>
                      第 {analysisResult.popularity_rank} 名
                    </span>
                  ) : '未进入前100'}
                </Descriptions.Item>
                <Descriptions.Item label="涨跌幅">
                  <span style={{ color: analysisResult.change_percent >= 0 ? '#cf1322' : '#3f8600' }}>
                    {analysisResult.change_percent.toFixed(2)}%
                  </span>
                </Descriptions.Item>
                <Descriptions.Item label="成交额">
                  {(analysisResult.turnover / 100000000).toFixed(2)}亿
                </Descriptions.Item>
                <Descriptions.Item label="概念归属" span={2}>
                  {analysisResult.concepts && analysisResult.concepts.length > 0 ? (
                    analysisResult.concepts.map((c) => (
                      <Tag key={c.name} color={c.is_core ? 'red' : 'default'}>
                        {c.name} {c.is_core && '(核心)'}
                      </Tag>
                    ))
                  ) : '无'}
                </Descriptions.Item>
              </Descriptions>

              <div style={{ marginTop: 24 }}>
                <h3>市场情绪</h3>
                <Descriptions bordered column={3}>
                  <Descriptions.Item label="涨停家数">
                    {analysisResult.market_sentiment.limit_up_count}
                  </Descriptions.Item>
                  <Descriptions.Item label="跌停家数">
                    {analysisResult.market_sentiment.limit_down_count}
                  </Descriptions.Item>
                  <Descriptions.Item label="最高连板">
                    {analysisResult.market_sentiment.max_streak}板
                  </Descriptions.Item>
                </Descriptions>
              </div>

              <Alert
                style={{ marginTop: 24 }}
                message="操作建议"
                description={analysisResult.suggestion}
                type={analysisResult.is_leader_candidate ? 'success' : 'warning'}
                showIcon
              />
            </Card>
          )}
        </>
      )}
    </div>
  );
}
