"""市场数据服务层"""
from datetime import datetime, timedelta, date as date_type
from typing import Optional, List, Dict
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.logger import get_logger

logger = get_logger(__name__)


class MarketService:
    """市场数据业务服务"""

    def _parse_date(self, date_str: str) -> date_type:
        """解析日期字符串为 date 对象"""
        return datetime.strptime(date_str, "%Y-%m-%d").date()

    async def _get_latest_trade_date(self, session) -> date_type:
        """获取最近交易日"""
        result = await session.execute(
            text("SELECT MAX(trade_date) FROM stock_daily")
        )
        latest = result.scalar()
        if latest:
            return latest
        result = await session.execute(
            text("SELECT MAX(trade_date) FROM limit_list")
        )
        latest = result.scalar()
        if latest:
            return latest
        return datetime.now().date()

    async def get_market_snapshot(self, date: Optional[str] = None) -> Dict:
        """获取市场快照"""
        async with AsyncSessionLocal() as session:
            if not date:
                query_date = await self._get_latest_trade_date(session)
            else:
                query_date = self._parse_date(date)
            # 统计涨停
            up_result = await session.execute(
                text("SELECT COUNT(*) FROM limit_list WHERE trade_date = :date AND limit_type = 'U'"),
                {"date": query_date}
            )
            limit_up_count = up_result.scalar() or 0

            # 统计跌停
            down_result = await session.execute(
                text("SELECT COUNT(*) FROM limit_list WHERE trade_date = :date AND limit_type = 'D'"),
                {"date": query_date}
            )
            limit_down_count = down_result.scalar() or 0

            # 统计炸板
            broken_result = await session.execute(
                text("SELECT COUNT(*) FROM limit_list WHERE trade_date = :date AND is_broken = TRUE"),
                {"date": query_date}
            )
            broken_board_count = broken_result.scalar() or 0

            # 计算封板率
            total_limit = limit_up_count + limit_down_count
            seal_rate = round((total_limit - broken_board_count) / total_limit * 100, 2) if total_limit > 0 else 0

            # 获取主要指数
            index_result = await session.execute(
                text("""
                    SELECT index_code, index_name, close_price, change_pct, amount
                    FROM index_daily 
                    WHERE trade_date = :date
                      AND index_code IN ('000001', '399001', '399006', '000688')
                """),
                {"date": query_date}
            )
            index_rows = index_result.fetchall()
            indices = []
            for row in index_rows:
                indices.append({
                    "index_code": row[0],
                    "index_name": row[1],
                    "close": float(row[2]) if row[2] else 0,
                    "change_pct": float(row[3]) if row[3] else 0,
                    "amount": float(row[4]) if row[4] else 0,
                })

            return {
                "date": date,
                "limit_up_count": limit_up_count,
                "limit_down_count": limit_down_count,
                "broken_board_count": broken_board_count,
                "seal_rate": seal_rate,
                "indices": indices,
            }

    async def get_latest_trade_date(self) -> Dict:
        """获取最近交易日"""
        async with AsyncSessionLocal() as session:
            # 从 stock_daily 表获取最近交易日
            result = await session.execute(
                text("SELECT MAX(trade_date) FROM stock_daily")
            )
            latest = result.scalar()
            if latest:
                return {"date": latest.strftime("%Y-%m-%d")}
            
            # 如果 stock_daily 没数据，从 limit_list 获取
            result = await session.execute(
                text("SELECT MAX(trade_date) FROM limit_list")
            )
            latest = result.scalar()
            if latest:
                return {"date": latest.strftime("%Y-%m-%d")}
            
            # 默认返回今天
            return {"date": datetime.now().strftime("%Y-%m-%d")}

    async def get_limit_up_list(
        self, 
        date: Optional[str] = None, 
        page: int = 1,
        page_size: int = 50
    ) -> Dict:
        """获取涨停股列表"""
        async with AsyncSessionLocal() as session:
            if not date:
                query_date = await self._get_latest_trade_date(session)
            else:
                query_date = self._parse_date(date)
    
            result = await session.execute(
                text("""
                    SELECT stock_code, stock_name, close_price, change_pct,
                           first_time, last_time, open_times, limit_times, is_broken
                    FROM limit_list 
                    WHERE trade_date = :date AND limit_type = 'U'
                    ORDER BY limit_times DESC, first_time
                    LIMIT :limit OFFSET :offset
                """),
                {"date": query_date, "limit": page_size, "offset": (page - 1) * page_size}
            )
            rows = result.fetchall()

            items = []
            for row in rows:
                items.append({
                    "stock_code": row[0],
                    "stock_name": row[1],
                    "close": float(row[2]) if row[2] else 0,
                    "change_pct": float(row[3]) if row[3] else 0,
                    "first_time": str(row[4])[:5] if row[4] else "--:--",
                    "last_time": str(row[5])[:5] if row[5] else "--:--",
                    "open_times": row[6],
                    "limit_times": row[7],
                    "is_broken": row[8],
                })

            return {"date": date or query_date.strftime("%Y-%m-%d"), "items": items}

    async def get_limit_down_list(
        self, 
        date: Optional[str] = None, 
        page: int = 1,
        page_size: int = 50
    ) -> Dict:
        """获取跌停股列表"""
        async with AsyncSessionLocal() as session:
            if not date:
                query_date = await self._get_latest_trade_date(session)
            else:
                query_date = self._parse_date(date)
    
            result = await session.execute(
                text("""
                    SELECT stock_code, stock_name, close_price, change_pct,
                           first_time, last_time, open_times, limit_times, is_broken
                    FROM limit_list 
                    WHERE trade_date = :date AND limit_type = 'D'
                    ORDER BY first_time
                    LIMIT :limit OFFSET :offset
                """),
                {"date": query_date, "limit": page_size, "offset": (page - 1) * page_size}
            )
            rows = result.fetchall()

            items = []
            for row in rows:
                items.append({
                    "stock_code": row[0],
                    "stock_name": row[1],
                    "close": float(row[2]) if row[2] else 0,
                    "change_pct": float(row[3]) if row[3] else 0,
                    "first_time": str(row[4])[:5] if row[4] else "--:--",
                    "last_time": str(row[5])[:5] if row[5] else "--:--",
                    "open_times": row[6],
                    "limit_times": row[7],
                    "is_broken": row[8],
                })

            return {"date": date or query_date.strftime("%Y-%m-%d"), "items": items}

    async def get_continuous_board(self, date: Optional[str] = None) -> Dict:
        """获取连板天梯"""
        async with AsyncSessionLocal() as session:
            if not date:
                query_date = await self._get_latest_trade_date(session)
            else:
                query_date = self._parse_date(date)

            # 按连板数分组（包含首板）
            result = await session.execute(
                text("""
                    SELECT limit_times, COUNT(*) as count,
                           array_agg(stock_code ORDER BY first_time) as stock_codes,
                           array_agg(stock_name ORDER BY first_time) as stock_names
                    FROM limit_list 
                    WHERE trade_date = :date AND limit_type = 'U'
                    GROUP BY limit_times
                    ORDER BY limit_times DESC
                """),
                {"date": query_date}
            )
            rows = result.fetchall()

            ladder = []
            for row in rows:
                limit_times = row[0]
                count = row[1]
                stock_codes = row[2] or []
                stock_names = row[3] or []

                stocks = []
                for i, code in enumerate(stock_codes):
                    stocks.append({
                        "stock_code": code,
                        "stock_name": stock_names[i] if i < len(stock_names) else "",
                    })

                ladder.append({
                    "level": f"{limit_times}板",
                    "limit_times": limit_times,
                    "count": count,
                    "stocks": stocks,
                })

            return {"date": date or query_date.strftime("%Y-%m-%d"), "ladder": ladder}

    async def get_broken_board_list(
        self, 
        date: Optional[str] = None, 
        page: int = 1, 
        page_size: int = 50
    ) -> Dict:
        """获取炸板股列表"""
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT stock_code, stock_name, close_price, change_pct,
                           first_time, broken_time, open_times
                    FROM limit_list 
                    WHERE trade_date = :date AND is_broken = TRUE
                    ORDER BY broken_time
                    LIMIT :limit OFFSET :offset
                """),
                {"date": date, "limit": page_size, "offset": (page - 1) * page_size}
            )
            rows = result.fetchall()

            items = []
            for row in rows:
                items.append({
                    "stock_code": row[0],
                    "stock_name": row[1],
                    "close": float(row[2]) if row[2] else 0,
                    "change_pct": float(row[3]) if row[3] else 0,
                    "first_time": str(row[4])[:5] if row[4] else "--:--",
                    "broken_time": str(row[5])[:5] if row[5] else "--:--",
                    "open_times": row[6],
                })

            return {"date": date, "items": items}

    async def get_stock_rank(
        self,
        date: Optional[str] = None,
        rank_type: str = "change_pct",
        direction: str = "up",
        page: int = 1,
        page_size: int = 50
    ) -> Dict:
        """获取个股排行"""
        order_sql = "DESC" if direction == "up" else "ASC"

        async with AsyncSessionLocal() as session:
            if not date:
                query_date = await self._get_latest_trade_date(session)
            else:
                query_date = self._parse_date(date)

            if rank_type == "change_pct":
                result = await session.execute(
                    text(f"""
                        SELECT sd.stock_code, si.stock_name, sd.close_price, sd.change_pct,
                               sd.volume, sd.amount
                        FROM stock_daily sd
                        LEFT JOIN stock_info si ON sd.stock_code = si.stock_code
                        WHERE sd.trade_date = :date
                        ORDER BY sd.change_pct {order_sql}
                        LIMIT :limit OFFSET :offset
                    """),
                    {"date": query_date, "limit": page_size, "offset": (page - 1) * page_size}
                )
            elif rank_type == "amount":
                result = await session.execute(
                    text(f"""
                        SELECT sd.stock_code, si.stock_name, sd.close_price, sd.change_pct,
                               sd.volume, sd.amount
                        FROM stock_daily sd
                        LEFT JOIN stock_info si ON sd.stock_code = si.stock_code
                        WHERE sd.trade_date = :date
                        ORDER BY sd.amount {order_sql}
                        LIMIT :limit OFFSET :offset
                    """),
                    {"date": query_date, "limit": page_size, "offset": (page - 1) * page_size}
                )
            else:  # capital_flow
                result = await session.execute(
                    text(f"""
                        SELECT cf.stock_code, si.stock_name, sd.close_price, sd.change_pct,
                               cf.main_net_inflow, cf.main_net_inflow_pct
                        FROM capital_flow cf
                        LEFT JOIN stock_info si ON cf.stock_code = si.stock_code
                        LEFT JOIN stock_daily sd ON cf.stock_code = sd.stock_code AND cf.trade_date = sd.trade_date
                        WHERE cf.trade_date = :date
                        ORDER BY cf.main_net_inflow {order_sql}
                        LIMIT :limit OFFSET :offset
                    """),
                    {"date": query_date, "limit": page_size, "offset": (page - 1) * page_size}
                )

            rows = result.fetchall()

            items = []
            for i, row in enumerate(rows, 1):
                items.append({
                    "rank": (page - 1) * page_size + i,
                    "stock_code": row[0],
                    "stock_name": row[1] or "",
                    "close": float(row[2]) if row[2] else 0,
                    "change_pct": float(row[3]) if row[3] else 0,
                    "volume": int(row[4]) if row[4] else 0,
                    "amount": float(row[5]) if row[5] else 0,
                })

            # 获取总数
            count_result = await session.execute(
                text("SELECT COUNT(*) FROM stock_daily WHERE trade_date = :date"),
                {"date": query_date}
            )
            total = count_result.scalar() or 0

            return {"date": str(query_date), "rank_type": rank_type, "items": items, "total": total}

    async def get_seal_rate_history(
        self, 
        start_date: Optional[str] = None, 
        end_date: Optional[str] = None
    ) -> Dict:
        """获取封板率历史"""
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT trade_date,
                           SUM(CASE WHEN limit_type = 'U' THEN 1 ELSE 0 END) as up_count,
                           SUM(CASE WHEN limit_type = 'D' THEN 1 ELSE 0 END) as down_count,
                           SUM(CASE WHEN is_broken = TRUE THEN 1 ELSE 0 END) as broken_count
                    FROM limit_list
                    WHERE trade_date BETWEEN :start_date AND :end_date
                    GROUP BY trade_date
                    ORDER BY trade_date
                """),
                {"start_date": start_date, "end_date": end_date}
            )
            rows = result.fetchall()

            items = []
            for row in rows:
                total = row[1] + row[2]
                seal_rate = round((total - row[3]) / total * 100, 2) if total > 0 else 0
                items.append({
                    "date": str(row[0]),
                    "limit_up_count": row[1],
                    "limit_down_count": row[2],
                    "broken_count": row[3],
                    "seal_rate": seal_rate,
                })

            return {"items": items}

    async def get_limit_times_history(
        self,
        stock_code: str,
        limit_type: str = "U",
        limit: int = 30
    ) -> Dict:
        """获取个股连板次数历史"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT trade_date, limit_times, is_broken, first_time, last_time
                    FROM limit_list
                    WHERE stock_code = :stock_code AND limit_type = :limit_type
                    ORDER BY trade_date DESC
                    LIMIT :limit
                """),
                {"stock_code": stock_code, "limit_type": limit_type, "limit": limit}
            )
            rows = result.fetchall()

            items = []
            for row in rows:
                items.append({
                    "date": str(row[0]),
                    "limit_times": row[1],
                    "is_broken": row[2],
                    "first_time": str(row[3])[:5] if row[3] else "--:--",
                    "last_time": str(row[4])[:5] if row[4] else "--:--",
                })

            return {"stock_code": stock_code, "items": items}

    async def get_limit_up_distribution(self, date: Optional[str] = None) -> Dict:
        """
        获取涨停方向分布
        
        统计各概念下涨停股的数量，用于判断市场热点方向
        
        Args:
            date: 日期，默认最近交易日
            
        Returns:
            概念涨停分布列表，按涨停数量降序排序
        """
        async with AsyncSessionLocal() as session:
            if not date:
                query_date = await self._get_latest_trade_date(session)
            else:
                query_date = self._parse_date(date)
            
            # 关联查询：涨停股 + 概念映射 + 概念信息
            result = await session.execute(
                text("""
                    SELECT 
                        ci.concept_code,
                        ci.concept_name,
                        COUNT(DISTINCT ll.stock_code) as limit_up_count,
                        ARRAY_AGG(DISTINCT ll.stock_code) as stocks
                    FROM limit_list ll
                    JOIN stock_concept_mapping_east scm ON ll.stock_code = scm.stock_code
                    JOIN concept_info_east ci ON scm.concept_code = ci.concept_code
                    WHERE ll.trade_date = :date AND ll.limit_type = 'U'
                    GROUP BY ci.concept_code, ci.concept_name
                    HAVING COUNT(DISTINCT ll.stock_code) > 0
                    ORDER BY limit_up_count DESC, ci.concept_name
                """),
                {"date": query_date}
            )
            
            items = []
            for row in result.fetchall():
                items.append({
                    "concept_code": row[0],
                    "concept_name": row[1],
                    "limit_up_count": row[2],
                    "stocks": row[3] if row[3] else [],
                })
            
            return {
                "date": date or query_date.strftime("%Y-%m-%d"),
                "items": items,
            }


# 单例
market_service = MarketService()
