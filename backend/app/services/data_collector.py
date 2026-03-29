"""数据采集服务"""
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json

from sqlalchemy import text
from app.core.database import AsyncSessionLocal, engine
from app.core.logger import get_logger
from app.core.config import settings

logger = get_logger(__name__)


class DataCollector:
    """数据采集器"""
    
    def __init__(self):
        self.tushare_token = settings.TUSHARE_TOKEN
    
    # ==================== 日线数据采集 ====================
    
    async def collect_all_daily(self):
        """采集所有日线数据（股票+指数）"""
        today = datetime.now().strftime("%Y-%m-%d")
        await self.collect_stock_daily_batch(today)
        await self.collect_index_daily_batch(today)
    
    async def collect_stock_daily(self, stock_code: str, date: str):
        """采集单只股票日线"""
        try:
            import adata
            df = adata.stock.market.get_market(
                code=stock_code,
                k_type=0,  # 日线
                start_date=date.replace("-", ""),
                end_date=date.replace("-", "")
            )
            if df is not None and len(df) > 0:
                await self._save_stock_daily(df)
                logger.info(f"采集股票日线 {stock_code} {date}: {len(df)} 条")
        except Exception as e:
            logger.error(f"采集股票日线失败 {stock_code}: {e}")
    
    async def collect_stock_daily_batch(self, date: str):
        """批量采集股票日线"""
        try:
            import adata
            df = adata.stock.market.get_market(
                k_type=0,
                start_date=date.replace("-", ""),
                end_date=date.replace("-", "")
            )
            if df is not None and len(df) > 0:
                await self._save_stock_daily(df)
                logger.info(f"批量采集股票日线 {date}: {len(df)} 条")
        except Exception as e:
            logger.error(f"批量采集股票日线失败: {e}")
    
    async def _save_stock_daily(self, df):
        """保存股票日线数据"""
        async with AsyncSessionLocal() as session:
            for _, row in df.iterrows():
                try:
                    await session.execute(text("""
                        INSERT INTO stock_daily (trade_date, stock_code, open_price, close_price, 
                            high_price, low_price, change_pct, volume, amount, turnover_rate)
                        VALUES (:trade_date, :stock_code, :open_price, :close_price,
                            :high_price, :low_price, :change_pct, :volume, :amount, :turnover_rate)
                        ON CONFLICT (trade_date, stock_code) DO UPDATE SET
                            open_price = EXCLUDED.open_price,
                            close_price = EXCLUDED.close_price,
                            high_price = EXCLUDED.high_price,
                            low_price = EXCLUDED.low_price,
                            change_pct = EXCLUDED.change_pct,
                            volume = EXCLUDED.volume,
                            amount = EXCLUDED.amount,
                            turnover_rate = EXCLUDED.turnover_rate
                    """), {
                        "trade_date": row.get("trade_date", ""),
                        "stock_code": row.get("stock_code", ""),
                        "open_price": row.get("open", 0),
                        "close_price": row.get("close", 0),
                        "high_price": row.get("high", 0),
                        "low_price": row.get("low", 0),
                        "change_pct": row.get("change_pct", 0),
                        "volume": row.get("volume", 0),
                        "amount": row.get("amount", 0),
                        "turnover_rate": row.get("turnover_rate", 0),
                    })
                except Exception as e:
                    logger.warning(f"保存股票日线失败: {e}")
            await session.commit()
    
    # ==================== 指数数据采集 ====================
    
    async def collect_index_daily(self, index_code: str, start_date: str, end_date: str):
        """采集指数日线"""
        try:
            import adata
            df = adata.stock.index.get_index(
                index_code=index_code,
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", "")
            )
            if df is not None and len(df) > 0:
                await self._save_index_daily(df)
                logger.info(f"采集指数日线 {index_code}: {len(df)} 条")
        except Exception as e:
            logger.error(f"采集指数日线失败 {index_code}: {e}")
    
    async def collect_index_daily_batch(self, date: str):
        """批量采集指数日线"""
        index_codes = ["000001", "399001", "399006", "000688"]  # 上证、深证、创业板、科创50
        for code in index_codes:
            await self.collect_index_daily(code, date, date)
    
    async def _save_index_daily(self, df):
        """保存指数日线数据"""
        async with AsyncSessionLocal() as session:
            for _, row in df.iterrows():
                try:
                    await session.execute(text("""
                        INSERT INTO index_daily (trade_date, index_code, index_name, open_price, close_price,
                            high_price, low_price, change_pct, volume, amount)
                        VALUES (:trade_date, :index_code, :index_name, :open_price, :close_price,
                            :high_price, :low_price, :change_pct, :volume, :amount)
                        ON CONFLICT (trade_date, index_code) DO UPDATE SET
                            open_price = EXCLUDED.open_price,
                            close_price = EXCLUDED.close_price,
                            high_price = EXCLUDED.high_price,
                            low_price = EXCLUDED.low_price,
                            change_pct = EXCLUDED.change_pct,
                            volume = EXCLUDED.volume,
                            amount = EXCLUDED.amount
                    """), {
                        "trade_date": row.get("trade_date", ""),
                        "index_code": row.get("index_code", ""),
                        "index_name": row.get("index_name", ""),
                        "open_price": row.get("open", 0),
                        "close_price": row.get("close", 0),
                        "high_price": row.get("high", 0),
                        "low_price": row.get("low", 0),
                        "change_pct": row.get("change_pct", 0),
                        "volume": row.get("volume", 0),
                        "amount": row.get("amount", 0),
                    })
                except Exception as e:
                    logger.warning(f"保存指数日线失败: {e}")
            await session.commit()
    
    # ==================== 分时数据采集 ====================
    
    async def collect_all_intraday(self):
        """采集所有分时数据"""
        today = datetime.now().strftime("%Y-%m-%d")
        await self.collect_stock_intraday_batch(today)
        await self.collect_index_intraday_batch(today)
    
    async def collect_stock_intraday(self, stock_code: str, date: str):
        """采集股票分时"""
        try:
            import adata
            df = adata.stock.market.get_market(
                code=stock_code,
                k_type=1,  # 分时
                start_date=date.replace("-", ""),
                end_date=date.replace("-", "")
            )
            if df is not None and len(df) > 0:
                await self._save_stock_intraday(df)
                logger.info(f"采集股票分时 {stock_code}: {len(df)} 条")
        except Exception as e:
            logger.error(f"采集股票分时失败 {stock_code}: {e}")
    
    async def collect_stock_intraday_batch(self, date: str):
        """批量采集股票分时"""
        # 从数据库获取活跃股票列表
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("""
                SELECT DISTINCT stock_code FROM stock_daily 
                WHERE trade_date = :date 
                ORDER BY amount DESC LIMIT 100
            """), {"date": date})
            stocks = [row[0] for row in result.fetchall()]
        
        for stock_code in stocks[:20]:  # 只采集前20只活跃股票
            await self.collect_stock_intraday(stock_code, date)
    
    async def _save_stock_intraday(self, df):
        """保存股票分时数据"""
        async with AsyncSessionLocal() as session:
            for _, row in df.iterrows():
                try:
                    await session.execute(text("""
                        INSERT INTO stock_intraday (trade_date, stock_code, trade_time, price, 
                            change_pct, volume, amount, avg_price)
                        VALUES (:trade_date, :stock_code, :trade_time, :price,
                            :change_pct, :volume, :amount, :avg_price)
                        ON CONFLICT (trade_date, stock_code, trade_time) DO UPDATE SET
                            price = EXCLUDED.price,
                            change_pct = EXCLUDED.change_pct,
                            volume = EXCLUDED.volume,
                            amount = EXCLUDED.amount,
                            avg_price = EXCLUDED.avg_price
                    """), {
                        "trade_date": row.get("trade_date", ""),
                        "stock_code": row.get("stock_code", ""),
                        "trade_time": row.get("trade_time", "00:00:00"),
                        "price": row.get("price", 0),
                        "change_pct": row.get("change_pct", 0),
                        "volume": row.get("volume", 0),
                        "amount": row.get("amount", 0),
                        "avg_price": row.get("avg_price", 0),
                    })
                except Exception as e:
                    logger.warning(f"保存股票分时失败: {e}")
            await session.commit()
    
    async def collect_index_intraday_batch(self, date: str):
        """批量采集指数分时"""
        try:
            import adata
            index_codes = ["000001", "399001", "399006", "000688"]
            for code in index_codes:
                df = adata.stock.index.get_index(
                    index_code=code,
                    index_min=True,
                    start_date=date.replace("-", ""),
                    end_date=date.replace("-", "")
                )
                if df is not None and len(df) > 0:
                    await self._save_index_intraday(df)
        except Exception as e:
            logger.error(f"采集指数分时失败: {e}")
    
    async def _save_index_intraday(self, df):
        """保存指数分时数据"""
        async with AsyncSessionLocal() as session:
            for _, row in df.iterrows():
                try:
                    await session.execute(text("""
                        INSERT INTO index_intraday (trade_date, index_code, trade_time, price,
                            change_pct, volume, amount)
                        VALUES (:trade_date, :index_code, :trade_time, :price,
                            :change_pct, :volume, :amount)
                        ON CONFLICT (trade_date, index_code, trade_time) DO UPDATE SET
                            price = EXCLUDED.price,
                            change_pct = EXCLUDED.change_pct,
                            volume = EXCLUDED.volume,
                            amount = EXCLUDED.amount
                    """), {
                        "trade_date": row.get("trade_date", ""),
                        "index_code": row.get("index_code", ""),
                        "trade_time": row.get("trade_time", "00:00:00"),
                        "price": row.get("price", 0),
                        "change_pct": row.get("change_pct", 0),
                        "volume": row.get("volume", 0),
                        "amount": row.get("amount", 0),
                    })
                except Exception as e:
                    logger.warning(f"保存指数分时失败: {e}")
            await session.commit()
    
    # ==================== 概念板块数据采集 ====================
    
    async def collect_concepts(self):
        """采集概念板块数据"""
        today = datetime.now().strftime("%Y-%m-%d")
        await self.collect_concept_list()
        await self.collect_concept_daily(today)
    
    async def collect_concept_list(self):
        """采集概念板块列表"""
        try:
            import adata
            df = adata.stock.info.get_concept()
            if df is not None and len(df) > 0:
                await self._save_concept_list(df)
                logger.info(f"采集概念板块列表: {len(df)} 条")
        except Exception as e:
            logger.error(f"采集概念板块列表失败: {e}")
    
    async def _save_concept_list(self, df):
        """保存概念板块列表"""
        async with AsyncSessionLocal() as session:
            for _, row in df.iterrows():
                try:
                    await session.execute(text("""
                        INSERT INTO concept_info_east (concept_code, concept_name, component_count)
                        VALUES (:concept_code, :concept_name, :component_count)
                        ON CONFLICT (concept_code) DO UPDATE SET
                            concept_name = EXCLUDED.concept_name,
                            component_count = EXCLUDED.component_count
                    """), {
                        "concept_code": row.get("concept_code", ""),
                        "concept_name": row.get("concept_name", ""),
                        "component_count": row.get("component_count", 0),
                    })
                except Exception as e:
                    logger.warning(f"保存概念板块失败: {e}")
            await session.commit()
    
    async def collect_concept_daily(self, date: str):
        """采集概念板块日线"""
        try:
            import adata
            df = adata.stock.info.get_concept_line_east()
            if df is not None and len(df) > 0:
                await self._save_concept_daily(df)
                logger.info(f"采集概念板块日线: {len(df)} 条")
        except Exception as e:
            logger.error(f"采集概念板块日线失败: {e}")
    
    async def _save_concept_daily(self, df):
        """保存概念板块日线"""
        async with AsyncSessionLocal() as session:
            for _, row in df.iterrows():
                try:
                    await session.execute(text("""
                        INSERT INTO concept_daily_east (trade_date, concept_code, open_price, close_price,
                            high_price, low_price, change_pct, volume, amount)
                        VALUES (:trade_date, :concept_code, :open_price, :close_price,
                            :high_price, :low_price, :change_pct, :volume, :amount)
                        ON CONFLICT (trade_date, concept_code) DO UPDATE SET
                            open_price = EXCLUDED.open_price,
                            close_price = EXCLUDED.close_price,
                            high_price = EXCLUDED.high_price,
                            low_price = EXCLUDED.low_price,
                            change_pct = EXCLUDED.change_pct,
                            volume = EXCLUDED.volume,
                            amount = EXCLUDED.amount
                    """), {
                        "trade_date": row.get("trade_date", ""),
                        "concept_code": row.get("concept_code", ""),
                        "open_price": row.get("open", 0),
                        "close_price": row.get("close", 0),
                        "high_price": row.get("high", 0),
                        "low_price": row.get("low", 0),
                        "change_pct": row.get("change_pct", 0),
                        "volume": row.get("volume", 0),
                        "amount": row.get("amount", 0),
                    })
                except Exception as e:
                    logger.warning(f"保存概念日线失败: {e}")
            await session.commit()
    
    async def update_concept_mapping(self):
        """更新概念成分股映射"""
        try:
            import adata
            # 获取概念列表
            async with AsyncSessionLocal() as session:
                result = await session.execute(text("SELECT concept_code FROM concept_info_east"))
                concepts = [row[0] for row in result.fetchall()]
            
            for concept_code in concepts[:50]:  # 只更新前50个概念
                try:
                    df = adata.stock.info.get_concept_constituent_east(concept_code=concept_code)
                    if df is not None and len(df) > 0:
                        await self._save_concept_mapping(concept_code, df)
                except Exception as e:
                    logger.warning(f"更新概念映射失败 {concept_code}: {e}")
            
            logger.info(f"概念成分股映射更新完成")
        except Exception as e:
            logger.error(f"更新概念成分股映射失败: {e}")
    
    async def _save_concept_mapping(self, concept_code: str, df):
        """保存概念成分股映射"""
        async with AsyncSessionLocal() as session:
            for _, row in df.iterrows():
                try:
                    await session.execute(text("""
                        INSERT INTO stock_concept_mapping_east (stock_code, concept_code, is_core, reason)
                        VALUES (:stock_code, :concept_code, :is_core, :reason)
                        ON CONFLICT (stock_code, concept_code) DO UPDATE SET
                            is_core = EXCLUDED.is_core,
                            reason = EXCLUDED.reason
                    """), {
                        "stock_code": row.get("stock_code", ""),
                        "concept_code": concept_code,
                        "is_core": row.get("is_core", False),
                        "reason": row.get("reason", ""),
                    })
                except Exception as e:
                    logger.warning(f"保存概念映射失败: {e}")
            await session.commit()
    
    # ==================== 涨跌停数据采集 ====================
    
    async def collect_limit_list(self, date: str = None):
        """采集涨跌停数据"""
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        
        try:
            import tushare as ts
            ts.set_token(self.tushare_token)
            pro = ts.pro_api()
            
            # 获取涨停数据
            df_up = pro.limit_list(trade_date=date.replace("-", ""), limit_type='U')
            if df_up is not None and len(df_up) > 0:
                await self._save_limit_list(df_up, 'U')
                logger.info(f"采集涨停数据: {len(df_up)} 条")
            
            # 获取跌停数据
            df_down = pro.limit_list(trade_date=date.replace("-", ""), limit_type='D')
            if df_down is not None and len(df_down) > 0:
                await self._save_limit_list(df_down, 'D')
                logger.info(f"采集跌停数据: {len(df_down)} 条")
            
        except Exception as e:
            logger.error(f"采集涨跌停数据失败: {e}")
    
    async def _save_limit_list(self, df, limit_type: str):
        """保存涨跌停数据"""
        async with AsyncSessionLocal() as session:
            for _, row in df.iterrows():
                try:
                    await session.execute(text("""
                        INSERT INTO limit_list (trade_date, stock_code, stock_name, limit_type,
                            close_price, change_pct, first_time, last_time, open_times, limit_times,
                            limit_amount, is_broken, broken_time, reseal_time)
                        VALUES (:trade_date, :stock_code, :stock_name, :limit_type,
                            :close_price, :change_pct, :first_time, :last_time, :open_times, :limit_times,
                            :limit_amount, :is_broken, :broken_time, :reseal_time)
                        ON CONFLICT (trade_date, stock_code, limit_type) DO UPDATE SET
                            close_price = EXCLUDED.close_price,
                            change_pct = EXCLUDED.change_pct,
                            first_time = EXCLUDED.first_time,
                            last_time = EXCLUDED.last_time,
                            open_times = EXCLUDED.open_times,
                            limit_times = EXCLUDED.limit_times,
                            limit_amount = EXCLUDED.limit_amount,
                            is_broken = EXCLUDED.is_broken,
                            broken_time = EXCLUDED.broken_time,
                            reseal_time = EXCLUDED.reseal_time
                    """), {
                        "trade_date": row.get("trade_date", ""),
                        "stock_code": row.get("ts_code", "").split(".")[0],
                        "stock_name": row.get("name", ""),
                        "limit_type": limit_type,
                        "close_price": row.get("close", 0),
                        "change_pct": row.get("pct_chg", 0),
                        "first_time": row.get("first_time", None),
                        "last_time": row.get("last_time", None),
                        "open_times": row.get("open_times", 0),
                        "limit_times": row.get("limit_times", 1),
                        "limit_amount": row.get("limit_amount", 0),
                        "is_broken": row.get("open_times", 0) > 0,
                        "broken_time": None,
                        "reseal_time": None,
                    })
                except Exception as e:
                    logger.warning(f"保存涨跌停数据失败: {e}")
            await session.commit()


# 单例
data_collector = DataCollector()
