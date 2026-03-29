import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import { Layout, Menu } from 'antd';
import { 
  DashboardOutlined, 
  StockOutlined, 
  AppstoreOutlined, 
  BarChartOutlined, 
  RobotOutlined, 
  FireOutlined, 
  TrophyOutlined, 
  FundOutlined,
  EyeOutlined,
  WalletOutlined,
} from '@ant-design/icons';

// 新页面
import DashboardNew from './pages/DashboardNew';
import LimitUp from './pages/LimitUp';
import Ladder from './pages/Ladder';
import ConceptRank from './pages/ConceptRank';
import Simulation from './pages/Simulation';
import Account from './pages/Account';

// 保留页面
import StockDetail from './pages/StockDetail';
import ErrorBoundary from './components/ErrorBoundary';
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
      key: '/limit-up',
      icon: <FireOutlined />,
      label: <Link to="/limit-up">涨跌停监控</Link>,
    },
    {
      key: '/ladder',
      icon: <TrophyOutlined />,
      label: <Link to="/ladder">连板天梯</Link>,
    },
    {
      key: '/concept-rank',
      icon: <FundOutlined />,
      label: <Link to="/concept-rank">板块排行</Link>,
    },
    {
      key: '/simulation',
      icon: <EyeOutlined />,
      label: <Link to="/simulation">模拟看盘</Link>,
    },
    {
      key: '/account',
      icon: <WalletOutlined />,
      label: <Link to="/account">我的账户</Link>,
    },
  ];

  return (
    <ErrorBoundary>
      <Router>
        <Layout style={{ minHeight: '100vh' }}>
          <Header className="header">
            <div className="logo">
              <h1 style={{ color: '#fff', margin: 0 }}>龙头战法 Web 平台</h1>
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
            <Layout style={{ padding: '0' }}>
              <Content
                style={{
                  margin: 0,
                  minHeight: 280,
                  background: '#f0f2f5',
                }}
              >
                <Routes>
                  <Route path="/" element={<DashboardNew />} />
                  <Route path="/limit-up" element={<LimitUp />} />
                  <Route path="/ladder" element={<Ladder />} />
                  <Route path="/concept-rank" element={<ConceptRank />} />
                  <Route path="/simulation" element={<Simulation />} />
                  <Route path="/account" element={<Account />} />
                  <Route path="/stock/:code" element={<StockDetail />} />
                </Routes>
              </Content>
            </Layout>
          </Layout>
        </Layout>
      </Router>
    </ErrorBoundary>
  );
}

export default App;
