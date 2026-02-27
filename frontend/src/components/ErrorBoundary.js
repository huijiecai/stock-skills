import React from 'react';
import { Result, Button } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';

/**
 * 错误边界组件
 * 捕获子组件的错误并显示友好的错误页面
 */
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    console.error('错误边界捕获到错误:', error, errorInfo);
    this.setState({
      error,
      errorInfo
    });
  }

  handleReload = () => {
    window.location.reload();
  };

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ 
          minHeight: '100vh', 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center',
          background: '#f0f2f5'
        }}>
          <Result
            status="error"
            title="页面出错了"
            subTitle="抱歉，页面遇到了一些问题。您可以尝试刷新页面或返回首页。"
            extra={[
              <Button type="primary" icon={<ReloadOutlined />} onClick={this.handleReload} key="reload">
                刷新页面
              </Button>,
              <Button onClick={this.handleReset} key="reset">
                重试
              </Button>,
              <Button type="link" href="/" key="home">
                返回首页
              </Button>
            ]}
          >
            {process.env.NODE_ENV === 'development' && this.state.error && (
              <div style={{ 
                textAlign: 'left', 
                background: '#fff', 
                padding: 16, 
                borderRadius: 4,
                marginTop: 24,
                maxWidth: 600,
                overflow: 'auto'
              }}>
                <details style={{ whiteSpace: 'pre-wrap' }}>
                  <summary style={{ cursor: 'pointer', fontWeight: 'bold', marginBottom: 8 }}>
                    错误详情（仅开发环境）
                  </summary>
                  <p style={{ color: '#cf1322', marginTop: 8 }}>
                    <strong>错误信息：</strong>
                    <br />
                    {this.state.error.toString()}
                  </p>
                  <p style={{ color: '#666', fontSize: 12 }}>
                    <strong>错误堆栈：</strong>
                    <br />
                    {this.state.errorInfo?.componentStack}
                  </p>
                </details>
              </div>
            )}
          </Result>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
