import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Portfolio from './pages/Portfolio'
import Report from './pages/Report'
import Market from './pages/Market'
import StockDetail from './pages/StockDetail'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="/portfolio" element={<Portfolio />} />
          <Route path="/report" element={<Report />} />
          <Route path="/market" element={<Market />} />
          <Route path="/stock/:code" element={<StockDetail />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
