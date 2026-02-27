import React, { useState, useRef, useEffect } from 'react';
import { Card, Input, Button, List, Typography, Space, Tag, Spin, Alert, Dropdown, Menu } from 'antd';
import { SendOutlined, RobotOutlined, UserOutlined, ReloadOutlined, ThunderboltOutlined, HistoryOutlined, DownloadOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';

const { Title, Text } = Typography;
const { TextArea } = Input;

// 快捷指令模板
const QUICK_COMMANDS = [
  { key: '1', label: '今天市场情绪怎么样？', icon: '📊' },
  { key: '2', label: '帮我分析002342', icon: '🔍' },
  { key: '3', label: '当前有哪些热门概念？', icon: '🔥' },
  { key: '4', label: '今天涨停的股票有哪些？', icon: '📈' },
  { key: '5', label: '分析一下半导体板块', icon: '💻' },
  { key: '6', label: '龙头战法的核心要点是什么？', icon: '🎯' },
];

export default function ChatAnalysis() {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  // 从localStorage加载历史记录
  useEffect(() => {
    const savedMessages = localStorage.getItem('chatHistory');
    if (savedMessages) {
      try {
        setMessages(JSON.parse(savedMessages));
      } catch (e) {
        console.error('加载历史记录失败:', e);
      }
    }
  }, []);

  // 保存历史记录到localStorage
  useEffect(() => {
    if (messages.length > 0) {
      localStorage.setItem('chatHistory', JSON.stringify(messages));
    }
  }, [messages]);

  // 自动滚动到底部
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // 发送消息
  const handleSend = async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage = {
      role: 'user',
      content: inputValue.trim(),
      timestamp: new Date().toLocaleTimeString()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    try {
      // 准备请求数据
      const requestData = {
        messages: [...messages, userMessage].map(msg => ({
          role: msg.role,
          content: msg.content
        }))
      };

      // 调用后端 SSE 接口
      const response = await fetch('http://localhost:8000/api/chat/analyze', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestData)
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      // 创建助手消息
      const assistantMessage = {
        role: 'assistant',
        content: '',
        timestamp: new Date().toLocaleTimeString()
      };
      setMessages(prev => [...prev, assistantMessage]);

      // 处理 SSE 流
      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            try {
              const parsed = JSON.parse(data);

              if (parsed.type === 'content') {
                // 更新助手消息内容
                setMessages(prev => {
                  const newMessages = [...prev];
                  const lastMsg = newMessages[newMessages.length - 1];
                  if (lastMsg.role === 'assistant') {
                    lastMsg.content += parsed.content;
                  }
                  return newMessages;
                });
              } else if (parsed.type === 'error') {
                // 错误处理
                setMessages(prev => {
                  const newMessages = [...prev];
                  const lastMsg = newMessages[newMessages.length - 1];
                  if (lastMsg.role === 'assistant') {
                    lastMsg.content = `❌ 错误: ${parsed.content}`;
                    lastMsg.isError = true;
                  }
                  return newMessages;
                });
              } else if (parsed.type === 'done') {
                // 完成
                break;
              }
            } catch (e) {
              console.error('解析SSE数据失败:', e);
            }
          }
        }
      }
    } catch (error) {
      console.error('发送消息失败:', error);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `❌ 发生错误: ${error.message}`,
        timestamp: new Date().toLocaleTimeString(),
        isError: true
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  // 清空对话
  const handleClear = () => {
    setMessages([]);
    localStorage.removeItem('chatHistory');
  };

  // 导出对话记录
  const handleExport = () => {
    if (messages.length === 0) {
      return;
    }
    
    const exportContent = messages.map(msg => {
      return `[${msg.timestamp}] ${msg.role === 'user' ? '用户' : 'AI助手'}:\n${msg.content}\n`;
    }).join('\n---\n\n');
    
    const blob = new Blob([exportContent], { type: 'text/plain;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `对话记录_${new Date().toISOString().slice(0, 10)}.txt`;
    link.click();
  };

  // 使用快捷指令
  const handleQuickCommand = ({ key }) => {
    const command = QUICK_COMMANDS.find(cmd => cmd.key === key);
    if (command) {
      setInputValue(command.label);
    }
  };

  const quickCommandMenu = (
    <Menu onClick={handleQuickCommand}>
      {QUICK_COMMANDS.map(cmd => (
        <Menu.Item key={cmd.key} icon={<span>{cmd.icon}</span>}>
          {cmd.label}
        </Menu.Item>
      ))}
    </Menu>
  );

  // 按Enter发送（Shift+Enter换行）
  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div style={{ height: 'calc(100vh - 120px)', display: 'flex', flexDirection: 'column' }}>
      {/* 标题栏 */}
      <Card
        style={{ marginBottom: 16 }}
        bodyStyle={{ padding: '16px 24px' }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Space>
            <RobotOutlined style={{ fontSize: 24, color: '#1890ff' }} />
            <Title level={3} style={{ margin: 0 }}>龙头战法智能分析</Title>
            <Tag color="green">AI助手</Tag>
            {messages.length > 0 && (
              <Tag color="blue">
                <HistoryOutlined /> {messages.length}条对话
              </Tag>
            )}
          </Space>
          <Space>
            <Dropdown overlay={quickCommandMenu} placement="bottomRight">
              <Button icon={<ThunderboltOutlined />}>快捷指令</Button>
            </Dropdown>
            {messages.length > 0 && (
              <Button icon={<DownloadOutlined />} onClick={handleExport}>
                导出
              </Button>
            )}
            <Button icon={<ReloadOutlined />} onClick={handleClear}>清空对话</Button>
          </Space>
        </div>
      </Card>

      {/* 消息列表 */}
      <Card
        style={{ flex: 1, marginBottom: 16, overflow: 'hidden' }}
        bodyStyle={{ height: '100%', overflow: 'auto', padding: 24 }}
      >
        {messages.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '60px 0', color: '#999' }}>
            <RobotOutlined style={{ fontSize: 64, marginBottom: 16 }} />
            <Title level={4} style={{ color: '#999' }}>开始对话</Title>
            <Text type="secondary">
              你可以问我关于股票分析、龙头战法、市场情绪等问题
            </Text>
            <div style={{ marginTop: 24 }}>
              <Text type="secondary">快捷指令：</Text>
              <div style={{ marginTop: 12 }}>
                {QUICK_COMMANDS.slice(0, 3).map(cmd => (
                  <Tag 
                    key={cmd.key}
                    style={{ margin: 4, cursor: 'pointer', padding: '4px 12px', fontSize: '14px' }} 
                    onClick={() => setInputValue(cmd.label)}
                  >
                    {cmd.icon} {cmd.label}
                  </Tag>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <List
            dataSource={messages}
            renderItem={(msg) => (
              <List.Item
                style={{
                  border: 'none',
                  padding: '12px 0',
                  justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start'
                }}
              >
                <div style={{
                  maxWidth: '80%',
                  display: 'flex',
                  gap: 12,
                  flexDirection: msg.role === 'user' ? 'row-reverse' : 'row'
                }}>
                  {/* 头像 */}
                  <div style={{
                    width: 40,
                    height: 40,
                    borderRadius: '50%',
                    background: msg.role === 'user' ? '#1890ff' : '#52c41a',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0
                  }}>
                    {msg.role === 'user' ? (
                      <UserOutlined style={{ color: 'white', fontSize: 20 }} />
                    ) : (
                      <RobotOutlined style={{ color: 'white', fontSize: 20 }} />
                    )}
                  </div>

                  {/* 消息内容 */}
                  <div style={{ flex: 1 }}>
                    <div style={{
                      background: msg.role === 'user' ? '#e6f7ff' : (msg.isError ? '#fff2e8' : '#f6ffed'),
                      padding: '12px 16px',
                      borderRadius: 8,
                      border: `1px solid ${msg.role === 'user' ? '#91d5ff' : (msg.isError ? '#ffbb96' : '#b7eb8f')}`
                    }}>
                      {msg.role === 'assistant' ? (
                        <ReactMarkdown>{msg.content || '思考中...'}</ReactMarkdown>
                      ) : (
                        <Text>{msg.content}</Text>
                      )}
                    </div>
                    <div style={{
                      marginTop: 4,
                      fontSize: 12,
                      color: '#999',
                      textAlign: msg.role === 'user' ? 'right' : 'left'
                    }}>
                      {msg.timestamp}
                    </div>
                  </div>
                </div>
              </List.Item>
            )}
          />
        )}
        <div ref={messagesEndRef} />
      </Card>

      {/* 输入框 */}
      <Card bodyStyle={{ padding: 16 }}>
        {isLoading && (
          <Alert
            message={
              <Space>
                <Spin size="small" />
                <Text>AI正在思考中...</Text>
              </Space>
            }
            type="info"
            showIcon={false}
            style={{ marginBottom: 12 }}
          />
        )}
        <Space.Compact style={{ width: '100%' }}>
          <TextArea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="输入你的问题... (Enter发送，Shift+Enter换行)"
            autoSize={{ minRows: 1, maxRows: 4 }}
            disabled={isLoading}
            style={{ flex: 1 }}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            disabled={!inputValue.trim() || isLoading}
            size="large"
          >
            发送
          </Button>
        </Space.Compact>
      </Card>
    </div>
  );
}
