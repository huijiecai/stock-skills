"""API 接口测试"""
import pytest
from httpx import AsyncClient
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.mark.anyio
async def test_root():
    """测试根路由"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "龙头战法 Web 平台 API"
        assert data["version"] == "2.0.0"


@pytest.mark.anyio
async def test_health():
    """测试健康检查"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


# ==================== 股票 API 测试 ====================

@pytest.mark.anyio
async def test_stock_search():
    """测试股票搜索"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/stock/search?keyword=平安")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200


# ==================== 指数 API 测试 ====================

@pytest.mark.anyio
async def test_index_list():
    """测试指数列表"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/index/list")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200


# ==================== 概念 API 测试 ====================

@pytest.mark.anyio
async def test_concept_list():
    """测试概念列表"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/concept/list?page=1&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200


@pytest.mark.anyio
async def test_concept_search():
    """测试概念搜索"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/concept/search?keyword=AI")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200


# ==================== 市场 API 测试 ====================

@pytest.mark.anyio
async def test_market_snapshot():
    """测试市场快照"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/market/snapshot")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "limit_up_count" in data["data"]
        assert "limit_down_count" in data["data"]
        assert "seal_rate" in data["data"]


# ==================== 模拟看盘 API 测试 ====================

@pytest.mark.anyio
async def test_simulation_market_overview():
    """测试模拟看盘市场概览"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/simulation/market-overview")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "market_sentiment" in data["data"]


@pytest.mark.anyio
async def test_simulation_hot_stocks():
    """测试热门个股"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/simulation/hot-stocks?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200


# ==================== 账户 API 测试 ====================

@pytest.mark.anyio
async def test_account_info():
    """测试账户信息"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/account/info")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "account_name" in data["data"]


@pytest.mark.anyio
async def test_account_positions():
    """测试持仓列表"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/account/positions")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200


@pytest.mark.anyio
async def test_account_trades():
    """测试交易记录"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/account/trades?page=1&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200


# ==================== 数据采集 API 测试 ====================

@pytest.mark.anyio
async def test_collector_trigger_daily():
    """测试触发日线采集"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/collector/trigger/daily")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
