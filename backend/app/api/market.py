"""市场数据相关 API"""
from fastapi import APIRouter, Query
from typing import Optional, List
from datetime import datetime, timedelta, date as date_type
from sqlalchemy import text

from app.core.database import get_db_session
from app.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/market", tags=["市场"])


def success_response(data=None, message: str = "success"):
    return {"code": 200, "message": message, "data": data}


def parse_date(date_str: str) -> date_type:
    """解析日期字符串为 date 对象"""
    return datetime.strptime(date_str, "%Y-%m-%d").date()


# ==================== 市场概览 ====================

@router.get("/snapshot")
async def get_market_snapshot(
    date: Optional[str] = Query(None, description="日期"),
):
    """
    获取市场快照
    
    返回涨停家数、跌停家数、炸板家数、封板率等市场情绪指标
    """
    if not date:
        query_date = datetime.now().date()
    else:
        query_date = parse_date(date)
    
    async with get_db_session() as db:
        # 统计涨停
        up_result = await db.execute(
            text("SELECT COUNT(*) FROM limit_list WHERE trade_date = :date AND limit_type = 'U'"),
            {"date": query_date}
        )
        limit_up_count = up_result.scalar() or 0
        
        # 统计跌停
        down_result = await db.execute(
            text("SELECT COUNT(*) FROM limit_list WHERE trade_date = :date AND limit_type = 'D'"),
            {"date": query_date}
        )
        limit_down_count = down_result.scalar() or 0
        
        # 统计炸板
        broken_result = await db.execute(
            text("SELECT COUNT(*) FROM limit_list WHERE trade_date = :date AND is_broken = TRUE"),
            {"date": query_date}
        )
        broken_board_count = broken_result.scalar() or 0
        
        # 计算封板率
        total_limit = limit_up_count + limit_down_count
        seal_rate = round((total_limit - broken_board_count) / total_limit * 100, 2) if total_limit > 0 else 0
        
        # 获取主要指数
        index_result = await db.execute(
            text("""
                SELECT index_code, index_name, close_price, change_pct
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
            })
        
        return success_response({
            "date": date,
            "limit_up_count": limit_up_count,
            "limit_down_count": limit_down_count,
            "broken_board_count": broken_board_count,
            "seal_rate": seal_rate,
            "indices": indices,
        })


# ==================== 涨跌停数据 ====================

@router.get("/limit-up")
async def get_limit_up_list(
    date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """获取涨停股列表"""
    if not date:
        query_date = datetime.now().date()
    else:
        query_date = parse_date(date)
    
    async with get_db_session() as db:
        result = await db.execute(
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
        
        return success_response({"date": date or query_date.strftime("%Y-%m-%d"), "items": items})


@router.get("/limit-down")
async def get_limit_down_list(
    date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """获取跌停股列表"""
    if not date:
        query_date = datetime.now().date()
    else:
        query_date = parse_date(date)
    
    async with get_db_session() as db:
        result = await db.execute(
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
        
        return success_response({"date": date or query_date.strftime("%Y-%m-%d"), "items": items})


# ==================== 连板天梯 ====================

@router.get("/continuous-board")
async def get_continuous_board(
    date: Optional[str] = Query(None),
):
    """获取连板天梯"""
    if not date:
        query_date = datetime.now().date()
    else:
        query_date = parse_date(date)
    
    async with get_db_session() as db:
        # 按连板数分组
        result = await db.execute(
            text("""
                SELECT limit_times, COUNT(*) as count,
                       array_agg(stock_code ORDER BY first_time) as stock_codes,
                       array_agg(stock_name ORDER BY first_time) as stock_names
                FROM limit_list 
                WHERE trade_date = :date AND limit_type = 'U' AND limit_times >= 2
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
        
        return success_response({"date": date or query_date.strftime("%Y-%m-%d"), "ladder": ladder})


# ==================== 炸板股 ====================

@router.get("/broken-board")
async def get_broken_board_list(
    date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """获取炸板股列表"""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    
    async with get_db_session() as db:
        result = await db.execute(
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
        
        return success_response({"date": date, "items": items})


# ==================== 个股排行 ====================

@router.get("/rank")
async def get_stock_rank(
    date: Optional[str] = Query(None),
    rank_type: str = Query("change_pct", description="排行类型: change_pct/amount/capital_flow"),
    direction: str = Query("up", description="up/down"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """获取个股排行"""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    
    order_sql = "DESC" if direction == "up" else "ASC"
    
    async with get_db_session() as db:
        if rank_type == "change_pct":
            result = await db.execute(
                text(f"""
                    SELECT sd.stock_code, si.stock_name, sd.close_price, sd.change_pct,
                           sd.volume, sd.amount
                    FROM stock_daily sd
                    LEFT JOIN stock_info si ON sd.stock_code = si.stock_code
                    WHERE sd.trade_date = :date
                    ORDER BY sd.change_pct {order_sql}
                    LIMIT :limit OFFSET :offset
                """),
                {"date": date, "limit": page_size, "offset": (page - 1) * page_size}
            )
        elif rank_type == "amount":
            result = await db.execute(
                text(f"""
                    SELECT sd.stock_code, si.stock_name, sd.close_price, sd.change_pct,
                           sd.volume, sd.amount
                    FROM stock_daily sd
                    LEFT JOIN stock_info si ON sd.stock_code = si.stock_code
                    WHERE sd.trade_date = :date
                    ORDER BY sd.amount {order_sql}
                    LIMIT :limit OFFSET :offset
                """),
                {"date": date, "limit": page_size, "offset": (page - 1) * page_size}
            )
        else:  # capital_flow
            result = await db.execute(
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
                {"date": date, "limit": page_size, "offset": (page - 1) * page_size}
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
        
        return success_response({"date": date, "rank_type": rank_type, "items": items})


# ==================== 历史数据查询 ====================

@router.get("/history/seal-rate")
async def get_seal_rate_history(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """获取封板率历史"""
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    async with get_db_session() as db:
        result = await db.execute(
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
        
        return success_response({"items": items})


@router.get("/history/limit-times")
async def get_limit_times_history(
    stock_code: str = Query(..., description="股票代码"),
    limit_type: str = Query("U", description="涨停U/跌停D"),
    limit: int = Query(30, ge=1, le=100),
):
    """获取个股连板次数历史"""
    async with get_db_session() as db:
        result = await db.execute(
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
        
        return success_response({"stock_code": stock_code, "items": items})
