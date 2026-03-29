import React, { useState } from 'react';
import { Card, Form, Input, Button, Descriptions, Tag, Alert, Spin, DatePicker, message } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { stockAPI, marketAPI } from '../services/api';
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
      
      // 获取股票信息和市场数据
      const [stockRes, marketRes] = await Promise.all([
        stockAPI.getInfo(values.code),
        marketAPI.getSnapshot(date),
      ]);
      
      if (stockRes.code === 200) {
        const stockData = stockRes.data;
        const marketData = marketRes.data;
        
        setAnalysisResult({
          success: true,
          stock_code: stockData.stock_code,
          stock_name: stockData.stock_name,
          date: date,
          market_phase: marketData.limit_up_count > 50 ? '主升' : marketData.limit_up_count < 10 ? '冰点' : '正常',
          market_sentiment: {
            limit_up_count: marketData.limit_up_count,
            limit_down_count: marketData.limit_down_count,
            max_streak: 0,
          },
          is_leader_candidate: false,
          popularity_rank: null,
          change_percent: 0,
          turnover: 0,
          concepts: [],
          suggestion: '请通过数据采集获取完整数据后进行分析',
        });
      } else {
        setAnalysisResult({ success: false, error: stockRes.message || '获取股票信息失败' });
      }
    } catch (error) {
      setAnalysisResult({ 
        success: false, 
        error: error.response?.data?.message || '分析失败，请检查股票代码是否正确' 
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
