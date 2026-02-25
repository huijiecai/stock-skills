from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import market, stocks, concepts, analysis

app = FastAPI(
    title="龙头战法Web平台",
    description="支持龙头战法的数据可视化和分析平台",
    version="1.0.0"
)

# CORS配置（本地开发）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(market.router, prefix="/api/market", tags=["market"])
app.include_router(stocks.router, prefix="/api/stocks", tags=["stocks"])
app.include_router(concepts.router, prefix="/api/concepts", tags=["concepts"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])

@app.get("/")
async def root():
    return {
        "message": "龙头战法Web平台API",
        "docs": "/docs",
        "version": "1.0.0"
    }

@app.get("/health")
async def health():
    return {"status": "ok"}
