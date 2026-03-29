"""模拟看盘服务层"""
from datetime import datetime, date as date_type
from typing import Optional, List, Dict
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.logger import get_logger

logger = get_logger(__name__)


class SimulationService:
    """模拟看盘业务服务"""

    def _parse_date(self, date_str: str) -> date_type:
        """解析日期字符串为 date 对象"""
        return datetime.strptime(date_str, "%Y-%m-%d").date()

    async def get_market_overview(self, date: Optional[str] = None) -> Dict:
        """获取市场概览"""
        if not date:
            query_date = datetime.now().date()
        else:
            query_date = self._parse_date(date)

        async with AsyncSessionLocal() as session:
            # 市场情绪
            up_result = await session.execute(
                text("SELECT COUNT(*) FROM limit_list WHERE trade_date = :date AND limit_type = 'U'"),
                {"date": query_date}
            )
            limit_up_count = up_result.scalar() or 0

            down_result = await session.execute(
                text("SELECT COUNT(*) FROM limit_list WHERE trade_date = :date AND limit_type = 'D'"),
                {"date": query_date}
            )
            limit_down_count = down_result.scalar() or 0

            broken_result = await session.execute(
                text("SELECT COUNT(*) FROM limit_list WHERE trade_date = :date AND is_broken = TRUE"),
                {"date": query_date}
            )
            broken_board_count = broken_result.scalar() or 0

            total_limit = limit_up_count + limit_down_count
            seal_rate = round((total_limit - broken_board_count) / total_limit * 100, 2) if total_limit > 0 else 0

            # 主要指数
            index_result = await session.execute(
                text("""
                    SELECT index_code, index_name, close_price, change_pct
                    FROM index_daily 
                    WHERE trade_date = :date
                      AND index_code IN ('000001', '399001', '399006', '000688')
                """),
                {"date": query_date}
            )
            indices = []
            for row in index_result.fetchall():
                indices.append({
                    "code": row[0],
                    "name": row[1],
                    "price": float(row[2]) if row[2] else 0,
                    "change_pct": float(row[3]) if row[3] else 0,
                })

            # 热门板块 (涨幅前5)
            concept_result = await session.execute(
                text("""
                    SELECT cd.concept_code, ci.concept_name, cd.change_pct
                    FROM concept_daily_east cd
                    JOIN concept_info_east ci ON cd.concept_code = ci.concept_code
                    WHERE cd.trade_date = :date
                    ORDER BY cd.change_pct DESC
                    LIMIT 5
                """),
                {"date": query_date}
            )
            hot_concepts = []
            for row in concept_result.fetchall():
                hot_concepts.append({
                    "code": row[0],
                    "name": row[1],
                    "change_pct": float(row[2]) if row[2] else 0,
                })

            return {
                "date": date or query_date.strftime("%Y-%m-%d"),
                "market_sentiment": {
                    "limit_up_count": limit_up_count,
                    "limit_down_count": limit_down_count,
                    "broken_board_count": broken_board_count,
                    "seal_rate": seal_rate,
                },
                "indices": indices,
                "hot_concepts": hot_concepts,
            }

    async def get_ladder_detail(self, date: Optional[str] = None) -> Dict:
        """获取连板天梯详情"""
        if not date:
            query_date = datetime.now().date()
        else:
            query_date = self._parse_date(date)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT limit_times, stock_code, stock_name, first_time, last_time,
                           is_broken, close_price, change_pct
                    FROM limit_list 
                    WHERE trade_date = :date AND limit_type = 'U'
                    ORDER BY limit_times DESC, first_time
                """),
                {"date": query_date}
            )
            rows = result.fetchall()

            # 按连板数分组
            ladder_map = {}
            for row in rows:
                limit_times = row[0]
                if limit_times not in ladder_map:
                    ladder_map[limit_times] = []

                ladder_map[limit_times].append({
                    "stock_code": row[1],
                    "stock_name": row[2],
                    "first_time": str(row[3])[:5] if row[3] else "--:--",
                    "last_time": str(row[4])[:5] if row[4] else "--:--",
                    "is_broken": row[5],
                    "close": float(row[6]) if row[6] else 0,
                    "change_pct": float(row[7]) if row[7] else 0,
                })

            # 转换为列表
            ladder = []
            for limit_times in sorted(ladder_map.keys(), reverse=True):
                ladder.append({
                    "level": f"{limit_times}板",
                    "limit_times": limit_times,
                    "count": len(ladder_map[limit_times]),
                    "stocks": ladder_map[limit_times],
                })

            return {"date": date or query_date.strftime("%Y-%m-%d"), "ladder": ladder}

    async def get_hot_stocks(self, date: Optional[str] = None, limit: int = 20) -> Dict:
        """获取热门个股（成交额最大）"""
        if not date:
            query_date = datetime.now().date()
        else:
            query_date = self._parse_date(date)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT sd.stock_code, si.stock_name, sd.close_price, sd.change_pct,
                           sd.volume, sd.amount
                    FROM stock_daily sd
                    LEFT JOIN stock_info si ON sd.stock_code = si.stock_code
                    WHERE sd.trade_date = :date
                    ORDER BY sd.amount DESC
                    LIMIT :limit
                """),
                {"date": query_date, "limit": limit}
            )
            rows = result.fetchall()

            items = []
            for i, row in enumerate(rows, 1):
                items.append({
                    "rank": i,
                    "stock_code": row[0],
                    "stock_name": row[1] or "",
                    "close": float(row[2]) if row[2] else 0,
                    "change_pct": float(row[3]) if row[3] else 0,
                    "volume": int(row[4]) if row[4] else 0,
                    "amount": float(row[5]) if row[5] else 0,
                })

            return {"date": date or query_date.strftime("%Y-%m-%d"), "items": items}

    async def get_capital_flow_rank(
        self, 
        date: Optional[str] = None, 
        direction: str = "in", 
        limit: int = 20
    ) -> Dict:
        """获取资金流向排行"""
        if not date:
            query_date = datetime.now().date()
        else:
            query_date = self._parse_date(date)

        order_sql = "DESC" if direction == "in" else "ASC"

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text(f"""
                    SELECT cf.stock_code, si.stock_name, sd.close_price, sd.change_pct,
                           cf.main_net_inflow, cf.main_net_inflow_pct
                    FROM capital_flow cf
                    LEFT JOIN stock_info si ON cf.stock_code = si.stock_code
                    LEFT JOIN stock_daily sd ON cf.stock_code = sd.stock_code AND cf.trade_date = sd.trade_date
                    WHERE cf.trade_date = :date
                    ORDER BY cf.main_net_inflow {order_sql}
                    LIMIT :limit
                """),
                {"date": query_date, "limit": limit}
            )
            rows = result.fetchall()

            items = []
            for i, row in enumerate(rows, 1):
                items.append({
                    "rank": i,
                    "stock_code": row[0],
                    "stock_name": row[1] or "",
                    "close": float(row[2]) if row[2] else 0,
                    "change_pct": float(row[3]) if row[3] else 0,
                    "main_net_inflow": float(row[4]) if row[4] else 0,
                    "main_net_inflow_pct": float(row[5]) if row[5] else 0,
                })

            return {
                "date": date or query_date.strftime("%Y-%m-%d"),
                "direction": direction, 
                "items": items
            }

    async def get_board_watch(self, date: Optional[str] = None) -> Dict:
        """获取涨停监控列表"""
        if not date:
            query_date = datetime.now().date()
        else:
            query_date = self._parse_date(date)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT stock_code, stock_name, close_price, change_pct,
                           first_time, last_time, open_times, limit_times, is_broken
                    FROM limit_list 
                    WHERE trade_date = :date AND limit_type = 'U'
                    ORDER BY is_broken, first_time
                """),
                {"date": query_date}
            )
            rows = result.fetchall()

            sealed = []
            broken = []

            for row in rows:
                stock = {
                    "stock_code": row[0],
                    "stock_name": row[1],
                    "close": float(row[2]) if row[2] else 0,
                    "change_pct": float(row[3]) if row[3] else 0,
                    "first_time": str(row[4])[:5] if row[4] else "--:--",
                    "last_time": str(row[5])[:5] if row[5] else "--:--",
                    "open_times": row[6],
                    "limit_times": row[7],
                }

                if row[8]:  # is_broken
                    broken.append(stock)
                else:
                    sealed.append(stock)

            return {
                "date": date,
                "sealed_count": len(sealed),
                "broken_count": len(broken),
                "sealed": sealed,
                "broken": broken,
            }

    async def get_market_snapshot_by_time(
        self, 
        time: str, 
        date: Optional[str] = None, 
        top_n: int = 10
    ) -> Dict:
        """
        全市场时间点快照
        
        Args:
            time: 时间点，如 "10:17"
            date: 日期，默认今日
            top_n: 返回涨幅榜前N名
            
        Returns:
            包含指数、市场情绪、涨幅榜、板块榜、涨停列表的完整快照
        """
        if not date:
            query_date = datetime.now().date()
        else:
            query_date = self._parse_date(date)
        
        # 解析时间
        time_obj = datetime.strptime(time, "%H:%M").time()
        
        async with AsyncSessionLocal() as session:
            # 1. 获取指数分时数据（截止到指定时间）
            index_result = await session.execute(
                text("""
                    SELECT DISTINCT ON (index_code) 
                           index_code, price, change_pct, volume, amount
                    FROM index_intraday
                    WHERE trade_date = :date AND trade_time <= :time
                    ORDER BY index_code, trade_time DESC
                """),
                {"date": query_date, "time": time_obj}
            )
            indices = {}
            for row in index_result.fetchall():
                indices[row[0]] = {
                    "name": {"000001": "上证指数", "399001": "深证成指", "399006": "创业板指"}.get(row[0], row[0]),
                    "price": float(row[1]) if row[1] else 0,
                    "change_pct": float(row[2]) if row[2] else 0,
                }
            
            # 2. 市场情绪（统计截止该时间已封板的股票）
            limit_result = await session.execute(
                text("""
                    SELECT 
                        COUNT(*) FILTER (WHERE limit_type = 'U') as limit_up_count,
                        COUNT(*) FILTER (WHERE limit_type = 'D') as limit_down_count,
                        COUNT(*) FILTER (WHERE is_broken = TRUE) as broken_board_count
                    FROM limit_list 
                    WHERE trade_date = :date AND first_time <= :time
                """),
                {"date": query_date, "time": time_obj}
            )
            limit_row = limit_result.fetchone()
            limit_up_count = limit_row[0] or 0
            limit_down_count = limit_row[1] or 0
            broken_board_count = limit_row[2] or 0
            
            total_limit = limit_up_count + broken_board_count
            seal_rate = round((limit_up_count / total_limit * 100), 2) if total_limit > 0 else 0
            
            market_sentiment = {
                "limit_up_count": limit_up_count,
                "limit_down_count": limit_down_count,
                "broken_board_count": broken_board_count,
                "seal_rate": seal_rate,
            }
            
            # 3. 涨幅榜（基于分时数据截止到指定时间）
            top_gainers_result = await session.execute(
                text("""
                    SELECT DISTINCT ON (si.stock_code)
                           si.stock_code, si.stock_name, sit.price, sit.change_pct
                    FROM stock_intraday sit
                    JOIN stock_info si ON sit.stock_code = si.stock_code
                    WHERE sit.trade_date = :date AND sit.trade_time <= :time
                    ORDER BY si.stock_code, sit.trade_time DESC
                    LIMIT :top_n
                """),
                {"date": query_date, "time": time_obj, "top_n": top_n * 10}
            )
            
            all_stocks = []
            for row in top_gainers_result.fetchall():
                all_stocks.append({
                    "code": row[0],
                    "name": row[1],
                    "price": float(row[2]) if row[2] else 0,
                    "change_pct": float(row[3]) if row[3] else 0,
                })
            
            top_gainers = sorted(all_stocks, key=lambda x: x["change_pct"], reverse=True)[:top_n]
            
            # 4. 热门板块（基于概念分时数据）
            concept_result = await session.execute(
                text("""
                    SELECT DISTINCT ON (ci.concept_code)
                           ci.concept_code, ci.concept_name, cit.change_pct
                    FROM concept_intraday_east cit
                    JOIN concept_info_east ci ON cit.concept_code = ci.concept_code
                    WHERE cit.trade_date = :date AND cit.trade_time <= :time
                    ORDER BY ci.concept_code, cit.trade_time DESC
                """),
                {"date": query_date, "time": time_obj}
            )
            
            all_concepts = []
            for row in concept_result.fetchall():
                all_concepts.append({
                    "code": row[0],
                    "name": row[1],
                    "change_pct": float(row[2]) if row[2] else 0,
                })
            
            top_concepts = sorted(all_concepts, key=lambda x: x["change_pct"], reverse=True)[:top_n]
            
            # 5. 涨停列表（截止到该时间已封板的）
            limit_up_result = await session.execute(
                text("""
                    SELECT stock_code, stock_name, first_time, limit_times
                    FROM limit_list
                    WHERE trade_date = :date AND limit_type = 'U' AND first_time <= :time
                    ORDER BY first_time
                """),
                {"date": query_date, "time": time_obj}
            )
            
            limit_up_list = []
            for row in limit_up_result.fetchall():
                limit_up_list.append({
                    "code": row[0],
                    "name": row[1],
                    "seal_time": str(row[2])[:5] if row[2] else "--:--",
                    "limit_times": row[3],
                })
            
            return {
                "time": time,
                "date": date or query_date.strftime("%Y-%m-%d"),
                "index": indices,
                "market_sentiment": market_sentiment,
                "top_gainers": top_gainers,
                "top_concepts": top_concepts,
                "limit_up_list": limit_up_list,
            }

    async def get_watchlist_snapshot(
        self, 
        time: str, 
        date: Optional[str] = None, 
        codes: List[str] = None
    ) -> Dict:
        """
        盯盘股时间点快照
        
        Args:
            time: 时间点，如 "10:17"
            date: 日期，默认今日
            codes: 股票代码列表
            
        Returns:
            指定股票在该时间点的分时数据
        """
        if not codes:
            return {
                "time": time,
                "date": date or datetime.now().strftime("%Y-%m-%d"),
                "items": []
            }
        
        if not date:
            query_date = datetime.now().date()
        else:
            query_date = self._parse_date(date)
        
        # 解析时间
        time_obj = datetime.strptime(time, "%H:%M").time()
        
        async with AsyncSessionLocal() as session:
            # 查询每只股票截止该时间的最新分时数据
            result = await session.execute(
                text("""
                    SELECT DISTINCT ON (si.stock_code)
                           si.stock_code, si.stock_name, sit.price, sit.change_pct,
                           sit.volume, sit.amount
                    FROM stock_intraday sit
                    JOIN stock_info si ON sit.stock_code = si.stock_code
                    WHERE sit.trade_date = :date 
                      AND sit.trade_time <= :time
                      AND sit.stock_code = ANY(:codes)
                    ORDER BY si.stock_code, sit.trade_time DESC
                """),
                {"date": query_date, "time": time_obj, "codes": codes}
            )
            
            items = []
            for row in result.fetchall():
                items.append({
                    "code": row[0],
                    "name": row[1],
                    "price": float(row[2]) if row[2] else 0,
                    "change_pct": float(row[3]) if row[3] else 0,
                    "volume": int(row[4]) if row[4] else 0,
                    "amount": float(row[5]) if row[5] else 0,
                })
            
            return {
                "time": time,
                "date": date or query_date.strftime("%Y-%m-%d"),
                "items": items,
            }

    async def get_timeline_snapshots(
        self, 
        date: Optional[str] = None, 
        times: List[str] = None,
        codes: List[str] = None
    ) -> Dict:
        """
        时间线快照序列
        
        Args:
            date: 日期，默认今日
            times: 时间点列表，如 ["09:30", "10:00", "10:30"]
            codes: 股票代码列表
            
        Returns:
            多个时间点的盯盘股快照
        """
        if not times:
            times = []
        
        if not codes:
            codes = []
        
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        
        snapshots = []
        for time_point in times:
            snapshot = await self.get_watchlist_snapshot(time_point, date, codes)
            snapshots.append(snapshot)
        
        return {
            "date": date,
            "snapshots": snapshots,
        }


# 单例
simulation_service = SimulationService()
