import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import { Layout, Menu } from 'antd';
import { DashboardOutlined, StockOutlined, AppstoreOutlined, BarChartOutlined, HistoryOutlined } from '@ant-design/icons';
import Dashboard from './pages/Dashboard';
import StockPool from './pages/StockPool';
import ConceptManage from './pages/ConceptManage';
import Analysis from './pages/Analysis';
import './App.css';

const { Header, Content, Sider } = Layout;

function App() {
  const menuItems = [
    {
      key: '/',
      icon: <DashboardOutlined />,
      label: <Link to="/">市场总览</Link>,
    },
    {
      key: '/stocks',
      icon: <StockOutlined />,
      label: <Link to="/stocks">股票池管理</Link>,
    },
    {
      key: '/concepts',
      icon: <AppstoreOutlined />,
      label: <Link to="/concepts">概念管理</Link>,
    },
    {
      key: '/analysis',
      icon: <BarChartOutlined />,
      label: <Link to="/analysis">龙头分析</Link>,
    },
  ];

  return (
    <Router>
      <Layout style={{ minHeight: '100vh' }}>
        <Header className="header">
          <div className="logo">
            <h1 style={{ color: '#fff', margin: 0 }}>龙头战法Web平台</h1>
          </div>
        </Header>
        <Layout>
          <Sider width={200} className="site-layout-background">
            <Menu
              mode="inline"
              defaultSelectedKeys={['/']}
              style={{ height: '100%', borderRight: 0 }}
              items={menuItems}
            />
          </Sider>
          <Layout style={{ padding: '24px' }}>
            <Content
              style={{
                padding: 24,
                margin: 0,
                minHeight: 280,
                background: '#fff',
              }}
            >
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/stocks" element={<StockPool />} />
                <Route path="/concepts" element={<ConceptManage />} />
                <Route path="/analysis" element={<Analysis />} />
              </Routes>
            </Content>
          </Layout>
        </Layout>
      </Layout>
    </Router>
  );
}

export default App;
