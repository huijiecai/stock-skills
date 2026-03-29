"""配置管理模块"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """应用配置"""
    
    # 数据库配置
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/stock"
    POSTGRES_PASSWORD: str = "password"
    
    # Tushare API 配置
    TUSHARE_TOKEN: str = ""
    TUSHARE_DOMAIN: str = "http://tushare.xyz"
    
    # adata 缓存目录
    ADATA_CACHE_DIR: str = "/data/adata_cache"
    
    # 日志级别
    LOG_LEVEL: str = "INFO"
    
    # 服务配置
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    
    # 项目根目录
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent.parent
    
    @property
    def postgres_data_dir(self) -> Path:
        """PostgreSQL 数据目录"""
        return self.BASE_DIR / "data" / "postgres"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


settings = get_settings()
