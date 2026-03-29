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
                stock_code=stock_code,
                k_type=1,  # 日线
                start_date=date,
                end_date=date
            )
            if df is not None and len(df) > 0:
                await self._save_stock_daily(df)
                logger.info(f"采集股票日线 {stock_code} {date}: {len(df)} 条")
        except Exception as e:
            logger.error(f"采集股票日线失败 {stock_code}: {e}")
    
    async def collect_stock_daily_batch(self, date: str):
        """批量采集股票日线 - 需要先获取股票列表"""
        try:
            import adata
            # 获取股票列表（从概念成分股或指数成分股）
            stock_codes = await self._get_active_stock_codes()
            total = 0
            for stock_code in stock_codes[:100]:  # 限制采集前100只
                try:
                    df = adata.stock.market.get_market(
                        stock_code=stock_code,
                        k_type=1,  # 日线
                        start_date=date,
                        end_date=date
                    )
                    if df is not None and len(df) > 0:
                        await self._save_stock_daily(df)
                        total += len(df)
                except Exception as e:
                    logger.warning(f"采集股票 {stock_code} 失败: {e}")
            logger.info(f"批量采集股票日线 {date}: {total} 条")
        except Exception as e:
            logger.error(f"批量采集股票日线失败: {e}")
    
    async def _get_active_stock_codes(self) -> List[str]:
        """获取活跃股票代码列表"""
        # 常用活跃股票代码
        return [
            '000001', '000002', '000063', '000333', '000651',
            '000725', '000768', '000858', '002230', '002304',
            '002415', '002594', '002714', '003816', '300014',
            '300015', '300033', '300059', '300750', '600000',
            '600009', '600010', '600011', '600015', '600016',
            '600018', '600019', '600028', '600029', '600030',
            '600031', '600036', '600048', '600050', '600104',
            '600109', '600111', '600150', '600176', '600183',
            '600276', '600309', '600332', '600346', '600352',
            '600436', '600438', '600486', '600489', '600519',
            '600547', '600570', '600585', '600588', '600660',
            '600690', '600703', '600745', '600809', '600837',
            '600887', '600893', '600900', '600905', '600918',
            '600919', '600926', '600941', '601012', '601021',
            '601066', '601088', '601111', '601138', '601166',
            '601211', '601225', '601236', '601288', '601318',
            '601328', '601336', '601390', '601398', '601555',
            '601601', '601628', '601633', '601658', '601668',
            '601669', '601688', '601728', '601766', '601788',
            '601818', '601857', '601877', '601888', '601899',
            '601900', '601901', '601916', '601919', '601933',
            '601939', '601985', '601988', '601989', '603019',
            '603087', '601127', '601799', '603160', '603259',
            '603260', '603288', '603501', '603596', '603799',
            '603833', '603899', '603986', '688001', '688012',
            '688041', '688065', '688111', '688126', '688169',
            '688187', '688223', '688256', '688303', '688369',
            '688396', '688432', '688496', '688561', '688599',
        ]
    
    async def _save_stock_daily(self, df):
        """保存股票日线数据"""
        from datetime import datetime as dt
        async with AsyncSessionLocal() as session:
            for _, row in df.iterrows():
                try:
                    # 转换日期格式
                    trade_date = row.get("trade_date", "")
                    if isinstance(trade_date, str):
                        trade_date = dt.strptime(trade_date, "%Y-%m-%d").date()
                    
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
                        "trade_date": trade_date,
                        "stock_code": row.get("stock_code", ""),
                        "open_price": row.get("open", 0),
                        "close_price": row.get("close", 0),
                        "high_price": row.get("high", 0),
                        "low_price": row.get("low", 0),
                        "change_pct": row.get("change_pct", 0),
                        "volume": row.get("volume", 0),
                        "amount": row.get("amount", 0),
                        "turnover_rate": row.get("turnover_ratio", 0),
                    })
                except Exception as e:
                    logger.warning(f"保存股票日线失败: {e}")
            await session.commit()
    
    # ==================== 指数数据采集 ====================
    
    async def collect_index_daily(self, index_code: str, start_date: str, end_date: str):
        """采集指数日线 - 参考 fetch_adata_data.py"""
        try:
            import adata
            from datetime import datetime as dt
            
            # 参考 fetch_adata_data.py 的正确写法
            df = adata.stock.market.get_market_index(
                index_code=index_code,
                k_type=1,  # 日K
            )
            if df is None or df.empty:
                logger.info(f"采集指数日线 {index_code}: 0 条")
                return
            
            # 过滤到目标日期范围
            start = dt.strptime(start_date, "%Y-%m-%d").date()
            end = dt.strptime(end_date, "%Y-%m-%d").date()
            
            filtered_rows = []
            for _, row in df.iterrows():
                trade_date = row.get('trade_date', '')
                if isinstance(trade_date, str) and len(trade_date) >= 10:
                    row_date = dt.strptime(trade_date[:10], "%Y-%m-%d").date()
                    if start <= row_date <= end:
                        filtered_rows.append(row)
            
            if filtered_rows:
                import pandas as pd
                filtered_df = pd.DataFrame(filtered_rows)
                await self._save_index_daily(filtered_df)
                logger.info(f"采集指数日线 {index_code}: {len(filtered_df)} 条")
            else:
                logger.info(f"采集指数日线 {index_code}: 0 条（日期范围内无数据）")
        except Exception as e:
            logger.error(f"采集指数日线失败 {index_code}: {e}")
    
    async def collect_index_daily_batch(self, date: str):
        """批量采集指数日线"""
        index_codes = ["000001", "399001", "399006", "000688"]  # 上证、深证、创业板、科创50
        for code in index_codes:
            await self.collect_index_daily(code, date, date)
    
    async def _save_index_daily(self, df):
        """保存指数日线数据"""
        from datetime import datetime as dt
        async with AsyncSessionLocal() as session:
            for _, row in df.iterrows():
                try:
                    # 转换日期格式
                    trade_date = row.get("trade_date", "")
                    if isinstance(trade_date, str) and len(trade_date) >= 10:
                        trade_date = dt.strptime(trade_date[:10], "%Y-%m-%d").date()
                    
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
                        "trade_date": trade_date,
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
            df = adata.stock.market.get_market_min(
                code=stock_code,
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
                df = adata.stock.market.get_market_index_min(index_code=code)
                if df is not None and len(df) > 0:
                    await self._save_index_intraday(df, date)
        except Exception as e:
            logger.error(f"采集指数分时失败: {e}")
    
    async def _save_index_intraday(self, df, date: str = None):
        """保存指数分时数据"""
        async with AsyncSessionLocal() as session:
            for _, row in df.iterrows():
                try:
                    # 如果没有trade_date，使用传入的date
                    trade_date = row.get("trade_date", "") or date
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
                        "trade_date": trade_date,
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
        """采集概念板块列表 - 参考 fetch_adata_data.py"""
        try:
            import adata
            # 正确方法：all_concept_code_ths
            df = adata.stock.info.all_concept_code_ths()
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
                    # index_code 是概念代码（如 BK0612），name 是概念名称
                    await session.execute(text("""
                        INSERT INTO concept_info_east (concept_code, concept_name, component_count)
                        VALUES (:concept_code, :concept_name, :component_count)
                        ON CONFLICT (concept_code) DO UPDATE SET
                            concept_name = EXCLUDED.concept_name,
                            component_count = EXCLUDED.component_count
                    """), {
                        "concept_code": row.get("index_code", ""),  # BK0612 格式
                        "concept_name": row.get("name", ""),
                        "component_count": row.get("component_count", 0),
                    })
                except Exception as e:
                    logger.warning(f"保存概念板块失败: {e}")
            await session.commit()
    
    async def collect_concept_daily(self, date: str):
        """采集概念板块日线 - 参考 fetch_adata_data.py"""
        try:
            import adata
            from datetime import datetime as dt
            
            # 获取概念列表（只取前50个热点概念）
            async with AsyncSessionLocal() as session:
                result = await session.execute(text("SELECT concept_code FROM concept_info_east LIMIT 50"))
                concepts = [row[0] for row in result.fetchall()]
            
            if not concepts:
                logger.warning("概念列表为空，请先采集概念列表")
                return
            
            target_date = dt.strptime(date, "%Y-%m-%d").date()
            total = 0
            
            for concept_code in concepts:
                try:
                    # 同花顺概念用 get_market_concept_ths
                    df = adata.stock.market.get_market_concept_ths(
                        index_code=concept_code,
                        k_type=1,
                    )
                    if df is None or df.empty:
                        continue
                    
                    # 过滤到目标日期
                    filtered_rows = []
                    for _, row in df.iterrows():
                        trade_date = row.get('trade_date', '')
                        if isinstance(trade_date, str) and len(trade_date) >= 10:
                            row_date = dt.strptime(trade_date[:10], "%Y-%m-%d").date()
                            if row_date == target_date:
                                filtered_rows.append(row)
                    
                    if filtered_rows:
                        import pandas as pd
                        await self._save_concept_daily(pd.DataFrame(filtered_rows))
                        total += len(filtered_rows)
                except Exception as e:
                    logger.warning(f"采集概念 {concept_code} 失败: {e}")
            
            logger.info(f"采集概念板块日线: {total} 条")
        except Exception as e:
            logger.error(f"采集概念板块日线失败: {e}")
    
    async def _save_concept_daily(self, df):
        """保存概念板块日线"""
        from datetime import datetime as dt
        async with AsyncSessionLocal() as session:
            for _, row in df.iterrows():
                try:
                    # 转换日期格式
                    trade_date = row.get("trade_date", "")
                    if isinstance(trade_date, str) and len(trade_date) >= 10:
                        trade_date = dt.strptime(trade_date[:10], "%Y-%m-%d").date()
                    
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
                        "trade_date": trade_date,
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
                    df = adata.stock.info.concept_constituent_east(concept_code=concept_code)
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
        """采集涨跌停数据 - 参考 fetch_tushare_data.py"""
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        
        try:
            import tushare as ts
            import tushare.pro.client as _client
            
            # 设置自定义域名（高积分用户）
            tushare_domain = getattr(settings, 'TUSHARE_DOMAIN', 'http://tushare.xyz')
            _client.DataApi._DataApi__http_url = tushare_domain
            
            ts.set_token(self.tushare_token)
            pro = ts.pro_api()
            
            date_compact = date.replace("-", "")
            
            # 获取涨停数据 - 使用 limit_list_d
            df_up = pro.limit_list_d(trade_date=date_compact, limit_type='U')
            if df_up is not None and len(df_up) > 0:
                await self._save_limit_list(df_up, 'U')
                logger.info(f"采集涨停数据: {len(df_up)} 条")
            
            # 获取跌停数据
            df_down = pro.limit_list_d(trade_date=date_compact, limit_type='D')
            if df_down is not None and len(df_down) > 0:
                await self._save_limit_list(df_down, 'D')
                logger.info(f"采集跌停数据: {len(df_down)} 条")
            
        except Exception as e:
            logger.error(f"采集涨跌停数据失败: {e}")
    
    async def _save_limit_list(self, df, limit_type: str):
        """保存涨跌停数据"""
        from datetime import datetime as dt
        async with AsyncSessionLocal() as session:
            for _, row in df.iterrows():
                try:
                    # 转换日期格式 (tushare 返回 20260326 格式)
                    trade_date_str = str(row.get("trade_date", ""))
                    if len(trade_date_str) == 8:
                        trade_date = dt.strptime(trade_date_str, "%Y%m%d").date()
                    else:
                        trade_date = trade_date_str
                    
                    # 解析 first_time (格式: 09:25:00 或 092500)
                    first_time = row.get("first_time", None)
                    if first_time:
                        ft = str(first_time)
                        if len(ft) == 6:
                            first_time = f"{ft[:2]}:{ft[2:4]}:{ft[4:6]}"
                    
                    last_time = row.get("last_time", None)
                    if last_time:
                        lt = str(last_time)
                        if len(lt) == 6:
                            last_time = f"{lt[:2]}:{lt[2:4]}:{lt[4:6]}"
                    
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
                        "trade_date": trade_date,
                        "stock_code": row.get("ts_code", "").split(".")[0],
                        "stock_name": row.get("name", ""),
                        "limit_type": limit_type,
                        "close_price": row.get("close", 0),
                        "change_pct": row.get("pct_chg", 0),
                        "first_time": first_time,
                        "last_time": last_time,
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
