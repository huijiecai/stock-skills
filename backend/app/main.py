from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from app.api import (
    stock_router,
    index_router,
    concept_router,
    market_router,
    collector_router,
    simulation_router,
    account_router,
)
from app.core.logger import setup_logging, get_logger
from app.core.config import settings
from app.scheduler import scheduler, init_jobs

# 加载环境变量
load_dotenv()

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    setup_logging(settings.LOG_LEVEL)
    logger.info("🚀 龙头战法Web平台启动中...")
    
    # 初始化定时任务
    init_jobs()
    scheduler.start()
    logger.info("✅ 定时任务调度器已启动")
    
    yield
    
    # 关闭时
    scheduler.shutdown()
    logger.info("👋 龙头战法Web平台已关闭")


app = FastAPI(
    title="龙头战法Web平台",
    description="支持龙头战法的数据可视化和分析平台",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(stock_router, prefix="/api")
app.include_router(index_router, prefix="/api")
app.include_router(concept_router, prefix="/api")
app.include_router(market_router, prefix="/api")
app.include_router(collector_router, prefix="/api")
app.include_router(simulation_router, prefix="/api")
app.include_router(account_router, prefix="/api")


@app.get("/")
async def root():
    return {
        "message": "龙头战法Web平台 API",
        "docs": "/docs",
        "version": "2.0.0",
        "features": [
            "股票行情",
            "指数行情",
            "概念板块",
            "涨跌停监控",
            "连板天梯",
            "模拟看盘",
            "账户管理",
        ]
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "scheduler_running": scheduler.running,
    }
