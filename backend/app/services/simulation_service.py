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


# 单例
simulation_service = SimulationService()
