"""账户管理服务层"""
import json
import uuid
from datetime import datetime
from typing import Optional, Dict, List
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.logger import get_logger

logger = get_logger(__name__)


class AccountService:
    """账户管理业务服务"""

    # ==================== 账户信息 ====================

    async def get_account_info(self) -> Dict:
        """获取账户信息"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT * FROM account_info ORDER BY id LIMIT 1")
            )
            row = result.fetchone()

            if row:
                return {
                    "account_id": row[0],
                    "account_name": row[1],
                    "initial_capital": float(row[2]) if row[2] else 0,
                    "available_cash": float(row[3]) if row[3] else 0,
                    "market_value": float(row[4]) if row[4] else 0,
                    "total_asset": float(row[5]) if row[5] else 0,
                    "total_profit": float(row[6]) if row[6] else 0,
                    "total_profit_pct": float(row[7]) if row[7] else 0,
                    "updated_at": str(row[9]) if row[9] else None,
                }

            # 如果没有账户，创建默认账户
            await session.execute(
                text("""
                    INSERT INTO account_info (account_name, initial_capital, available_cash, market_value, total_asset)
                    VALUES ('默认账户', 1000000, 1000000, 0, 1000000)
                """)
            )
            await session.commit()

            return {
                "account_id": 1,
                "account_name": "默认账户",
                "initial_capital": 1000000,
                "available_cash": 1000000,
                "market_value": 0,
                "total_asset": 1000000,
                "total_profit": 0,
                "total_profit_pct": 0,
            }

    async def update_account_info(
        self, 
        account_name: Optional[str] = None, 
        initial_capital: Optional[float] = None
    ) -> bool:
        """更新账户信息"""
        updates = []
        params = {}

        if account_name:
            updates.append("account_name = :account_name")
            params["account_name"] = account_name

        if initial_capital is not None:
            updates.append("initial_capital = :initial_capital")
            params["initial_capital"] = initial_capital

        if not updates:
            return False

        params["updated_at"] = datetime.now()
        async with AsyncSessionLocal() as session:
            await session.execute(
                text(f"UPDATE account_info SET {', '.join(updates)}, updated_at = :updated_at WHERE id = 1"),
                params
            )

        return True

    # ==================== 持仓管理 ====================

    async def get_positions(self) -> Dict:
        """获取持仓列表"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT p.id, p.stock_code, p.stock_name, p.quantity, p.available,
                           p.cost_price, p.current_price, p.market_value, p.profit, p.profit_pct
                    FROM position p
                    WHERE p.quantity > 0
                    ORDER BY p.market_value DESC
                """)
            )
            rows = result.fetchall()

            items = []
            total_market_value = 0
            total_profit = 0

            for row in rows:
                market_value = float(row[7]) if row[7] else 0
                profit = float(row[8]) if row[8] else 0
                total_market_value += market_value
                total_profit += profit

                items.append({
                    "position_id": row[0],
                    "stock_code": row[1],
                    "stock_name": row[2] or "",
                    "quantity": row[3],
                    "available": row[4],
                    "cost_price": float(row[5]) if row[5] else 0,
                    "current_price": float(row[6]) if row[6] else 0,
                    "market_value": market_value,
                    "profit": profit,
                    "profit_pct": float(row[9]) if row[9] else 0,
                })

            return {
                "positions": items,
                "total_market_value": total_market_value,
                "total_profit": total_profit,
            }

    async def update_position_prices(self) -> bool:
        """更新持仓价格"""
        async with AsyncSessionLocal() as session:
            # 获取所有持仓
            result = await session.execute(
                text("SELECT id, stock_code, quantity, cost_price FROM position WHERE quantity > 0")
            )
            positions = result.fetchall()

            for pos in positions:
                pos_id, stock_code, quantity, cost_price = pos

                # 获取最新价格
                price_result = await session.execute(
                    text("""
                        SELECT close_price FROM stock_daily 
                        WHERE stock_code = :code 
                        ORDER BY trade_date DESC LIMIT 1
                    """),
                    {"code": stock_code}
                )
                price_row = price_result.fetchone()

                if price_row and price_row[0]:
                    current_price = float(price_row[0])
                    market_value = current_price * quantity
                    cost = float(cost_price) * quantity if cost_price else 0
                    profit = market_value - cost
                    profit_pct = (profit / cost * 100) if cost > 0 else 0

                    await session.execute(
                        text("""
                            UPDATE position SET 
                                current_price = :current_price,
                                market_value = :market_value,
                                profit = :profit,
                                profit_pct = :profit_pct,
                                updated_at = :updated_at
                            WHERE id = :id
                        """),
                        {
                            "current_price": current_price,
                            "market_value": market_value,
                            "profit": profit,
                            "profit_pct": profit_pct,
                            "updated_at": datetime.now(),
                            "id": pos_id,
                        }
                    )

            # 更新账户市值
            await session.execute(
                text("""
                    UPDATE account_info SET 
                        market_value = (SELECT COALESCE(SUM(market_value), 0) FROM position),
                        total_asset = available_cash + (SELECT COALESCE(SUM(market_value), 0) FROM position),
                        updated_at = :updated_at
                    WHERE id = 1
                """),
                {"updated_at": datetime.now()}
            )

        return True

    # ==================== 交易记录 ====================

    async def get_trade_records(
        self, 
        start_date: Optional[str] = None, 
        end_date: Optional[str] = None, 
        page: int = 1, 
        page_size: int = 20
    ) -> Dict:
        """获取交易记录"""
        async with AsyncSessionLocal() as session:
            where_clauses = ["account_id = 1"]
            params = {"limit": page_size, "offset": (page - 1) * page_size}

            if start_date:
                where_clauses.append("trade_time >= :start_date")
                params["start_date"] = f"{start_date} 00:00:00"

            if end_date:
                where_clauses.append("trade_time <= :end_date")
                params["end_date"] = f"{end_date} 23:59:59"

            where_sql = " AND ".join(where_clauses)

            result = await session.execute(
                text(f"""
                    SELECT trade_id, trade_time, stock_code, stock_name, action,
                           price, quantity, amount, reason
                    FROM trade_record
                    WHERE {where_sql}
                    ORDER BY trade_time DESC
                    LIMIT :limit OFFSET :offset
                """),
                params
            )
            rows = result.fetchall()

            items = []
            for row in rows:
                items.append({
                    "trade_id": row[0],
                    "trade_time": str(row[1]),
                    "stock_code": row[2],
                    "stock_name": row[3] or "",
                    "action": row[4],
                    "price": float(row[5]) if row[5] else 0,
                    "quantity": row[6],
                    "amount": float(row[7]) if row[7] else 0,
                    "reason": row[8] or "",
                })

            return {"items": items}

    async def execute_trade(
        self, 
        stock_code: str, 
        action: str, 
        price: float, 
        quantity: int, 
        reason: Optional[str] = None
    ) -> Dict:
        """执行交易"""
        if action not in ["buy", "sell"]:
            raise ValueError("action 必须是 buy 或 sell")

        async with AsyncSessionLocal() as session:
            # 获取股票名称
            info_result = await session.execute(
                text("SELECT stock_name FROM stock_info WHERE stock_code = :code"),
                {"code": stock_code}
            )
            info_row = info_result.fetchone()
            stock_name = info_row[0] if info_row else ""

            amount = price * quantity
            trade_id = f"T{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}"

            if action == "buy":
                # 买入：检查资金
                account_result = await session.execute(
                    text("SELECT available_cash FROM account_info WHERE id = 1")
                )
                account_row = account_result.fetchone()
                if not account_row or account_row[0] < amount:
                    raise ValueError("可用资金不足")

                # 扣除资金
                await session.execute(
                    text("UPDATE account_info SET available_cash = available_cash - :amount WHERE id = 1"),
                    {"amount": amount}
                )

                # 更新持仓
                pos_result = await session.execute(
                    text("SELECT id, quantity, cost_price FROM position WHERE stock_code = :code AND account_id = 1"),
                    {"code": stock_code}
                )
                pos_row = pos_result.fetchone()

                if pos_row:
                    # 加仓
                    new_quantity = pos_row[1] + quantity
                    new_cost = (pos_row[1] * float(pos_row[2]) + amount) / new_quantity
                    await session.execute(
                        text("UPDATE position SET quantity = :qty, cost_price = :cost WHERE id = :id"),
                        {"qty": new_quantity, "cost": new_cost, "id": pos_row[0]}
                    )
                else:
                    # 新建持仓
                    await session.execute(
                        text("""
                            INSERT INTO position (account_id, stock_code, stock_name, quantity, available, cost_price)
                            VALUES (1, :code, :name, :qty, 0, :cost)
                        """),
                        {"code": stock_code, "name": stock_name, "qty": quantity, "cost": price}
                    )

            else:  # sell
                # 卖出：检查持仓
                pos_result = await session.execute(
                    text("SELECT id, quantity, cost_price FROM position WHERE stock_code = :code AND account_id = 1"),
                    {"code": stock_code}
                )
                pos_row = pos_result.fetchone()

                if not pos_row or pos_row[1] < quantity:
                    raise ValueError("持仓数量不足")

                # 增加资金
                await session.execute(
                    text("UPDATE account_info SET available_cash = available_cash + :amount WHERE id = 1"),
                    {"amount": amount}
                )

                # 更新持仓
                new_quantity = pos_row[1] - quantity
                if new_quantity == 0:
                    await session.execute(
                        text("DELETE FROM position WHERE id = :id"), 
                        {"id": pos_row[0]}
                    )
                else:
                    await session.execute(
                        text("UPDATE position SET quantity = :qty WHERE id = :id"),
                        {"qty": new_quantity, "id": pos_row[0]}
                    )

            # 记录交易
            await session.execute(
                text("""
                    INSERT INTO trade_record (trade_id, account_id, trade_time, stock_code, stock_name, action, price, quantity, amount, reason)
                    VALUES (:trade_id, 1, :trade_time, :code, :name, :action, :price, :qty, :amount, :reason)
                """),
                {
                    "trade_id": trade_id,
                    "trade_time": datetime.now(),
                    "code": stock_code,
                    "name": stock_name,
                    "action": action,
                    "price": price,
                    "qty": quantity,
                    "amount": amount,
                    "reason": reason or "",
                }
            )

            return {
                "trade_id": trade_id,
                "stock_code": stock_code,
                "stock_name": stock_name,
                "action": action,
                "price": price,
                "quantity": quantity,
                "amount": amount,
            }

    # ==================== 每日快照 ====================

    async def get_account_snapshots(
        self, 
        start_date: Optional[str] = None, 
        end_date: Optional[str] = None, 
        limit: int = 30
    ) -> Dict:
        """获取账户每日快照"""
        async with AsyncSessionLocal() as session:
            where_clauses = ["account_id = 1"]
            params = {"limit": limit}

            if start_date:
                where_clauses.append("snapshot_date >= :start_date")
                params["start_date"] = start_date
            if end_date:
                where_clauses.append("snapshot_date <= :end_date")
                params["end_date"] = end_date

            where_sql = " AND ".join(where_clauses)

            result = await session.execute(
                text(f"""
                    SELECT snapshot_date, total_asset, available_cash, market_value,
                           daily_profit, daily_profit_pct, positions
                    FROM account_snapshot
                    WHERE {where_sql}
                    ORDER BY snapshot_date DESC
                    LIMIT :limit
                """),
                params
            )
            rows = result.fetchall()

            items = []
            for row in rows:
                items.append({
                    "date": str(row[0]),
                    "total_asset": float(row[1]) if row[1] else 0,
                    "available_cash": float(row[2]) if row[2] else 0,
                    "market_value": float(row[3]) if row[3] else 0,
                    "daily_profit": float(row[4]) if row[4] else 0,
                    "daily_profit_pct": float(row[5]) if row[5] else 0,
                    "positions": row[6] or [],
                })

            return {"items": items}

    async def create_daily_snapshot(self) -> str:
        """创建当日快照"""
        today = datetime.now().strftime("%Y-%m-%d")

        async with AsyncSessionLocal() as session:
            # 检查是否已存在
            exist_result = await session.execute(
                text("SELECT id FROM account_snapshot WHERE account_id = 1 AND snapshot_date = :date"),
                {"date": today}
            )
            if exist_result.fetchone():
                raise ValueError(f"{today} 快照已存在")

            # 获取账户信息
            account_result = await session.execute(
                text("SELECT total_asset, available_cash, market_value FROM account_info WHERE id = 1")
            )
            account_row = account_result.fetchone()

            if not account_row:
                raise ValueError("账户不存在")

            # 获取持仓
            pos_result = await session.execute(
                text("SELECT stock_code, stock_name, quantity, cost_price, current_price, market_value FROM position WHERE account_id = 1")
            )
            positions = []
            for row in pos_result.fetchall():
                positions.append({
                    "stock_code": row[0],
                    "stock_name": row[1],
                    "quantity": row[2],
                    "cost_price": float(row[3]) if row[3] else 0,
                    "current_price": float(row[4]) if row[4] else 0,
                    "market_value": float(row[5]) if row[5] else 0,
                })

            # 计算日收益
            prev_result = await session.execute(
                text("SELECT total_asset FROM account_snapshot WHERE account_id = 1 ORDER BY snapshot_date DESC LIMIT 1")
            )
            prev_row = prev_result.fetchone()
            prev_asset = float(prev_row[0]) if prev_row else 0

            total_asset = float(account_row[0]) if account_row[0] else 0
            daily_profit = total_asset - prev_asset if prev_asset > 0 else 0
            daily_profit_pct = (daily_profit / prev_asset * 100) if prev_asset > 0 else 0

            # 创建快照
            await session.execute(
                text("""
                    INSERT INTO account_snapshot (account_id, snapshot_date, total_asset, available_cash, market_value, daily_profit, daily_profit_pct, positions)
                    VALUES (1, :date, :total_asset, :available_cash, :market_value, :daily_profit, :daily_profit_pct, :positions)
                """),
                {
                    "date": today,
                    "total_asset": total_asset,
                    "available_cash": float(account_row[1]) if account_row[1] else 0,
                    "market_value": float(account_row[2]) if account_row[2] else 0,
                    "daily_profit": daily_profit,
                    "daily_profit_pct": daily_profit_pct,
                    "positions": json.dumps(positions),
                }
            )

        return f"{today} 快照创建成功"


# 单例
account_service = AccountService()
