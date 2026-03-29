import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import { Layout, Menu } from 'antd';
import { 
  DashboardOutlined,
  StockOutlined,
  FundOutlined,
  FireOutlined,
  TrophyOutlined,
  WalletOutlined,
} from '@ant-design/icons';

// 页面组件
import DashboardNew from './pages/DashboardNew';
import StockRanking from './pages/StockRanking';
import ConceptRank from './pages/ConceptRank';
import Ladder from './pages/Ladder';
import LimitUp from './pages/LimitUp';
import StockDetail from './pages/StockDetail';
import Account from './pages/Account';

// 样式
import './styles/dark-theme.css';

// 错误边界
import ErrorBoundary from './components/ErrorBoundary';

const { Header, Content, Sider } = Layout;

const menuItems = [
  {
    key: '/',
    icon: <DashboardOutlined />,
    label: <Link to="/">市场总览</Link>,
  },
  {
    key: '/stock-ranking',
    icon: <StockOutlined />,
    label: <Link to="/stock-ranking">个股排行</Link>,
  },
  {
    key: '/concept-rank',
    icon: <FundOutlined />,
    label: <Link to="/concept-rank">板块排行</Link>,
  },
  {
    key: '/ladder',
    icon: <TrophyOutlined />,
    label: <Link to="/ladder">连板天梯</Link>,
  },
  {
    key: '/limit-up',
    icon: <FireOutlined />,
    label: <Link to="/limit-up">涨跌停</Link>,
  },
  {
    key: '/account',
    icon: <WalletOutlined />,
    label: <Link to="/account">我的账户</Link>,
  },
];

const AppContent = () => {
  const location = useLocation();
  const selectedKey = '/' + location.pathname.split('/')[1] || '/';

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header className="header">
        <div className="logo">
          <h1>龙头战法 Web 平台</h1>
        </div>
      </Header>
      <Layout>
        <Sider width={180} className="site-layout-background">
          <Menu
            mode="inline"
            selectedKeys={[selectedKey]}
            style={{ height: '100%', borderRight: 0 }}
            items={menuItems}
          />
        </Sider>
        <Layout style={{ padding: '0' }}>
          <Content style={{ margin: 0, minHeight: 280 }}>
            <Routes>
              <Route path="/" element={<DashboardNew />} />
              <Route path="/stock-ranking" element={<StockRanking />} />
              <Route path="/concept-rank" element={<ConceptRank />} />
              <Route path="/ladder" element={<Ladder />} />
              <Route path="/limit-up" element={<LimitUp />} />
              <Route path="/stock/:code" element={<StockDetail />} />
              <Route path="/account" element={<Account />} />
            </Routes>
          </Content>
        </Layout>
      </Layout>
    </Layout>
  );
};

function App() {
  return (
    <ErrorBoundary>
      <Router>
        <AppContent />
      </Router>
    </ErrorBoundary>
  );
}

export default App;
