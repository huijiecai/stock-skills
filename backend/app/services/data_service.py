from pathlib import Path
from typing import Optional, List, Dict
import sqlite3
from datetime import datetime

# 导入后端内部服务模块
from app.services.query_service import QueryService
from app.services.concept_manager import ConceptManager
from app.services.stock_concept_manager import StockConceptManager

project_root = Path(__file__).parent.parent.parent.parent


class DataService:
    """数据服务 - 后端唯一数据库访问层"""
    
    def __init__(self):
        # 数据文件统一放在项目根目录的data文件夹
        db_path = project_root / "data" / "dragon_stock.db"
        self.db_path = str(db_path)
        self.query_service = QueryService(self.db_path)
        self.concept_manager = ConceptManager(self.db_path)
        self.stock_concept_manager = StockConceptManager(self.db_path)
    
    # ==================== 市场数据查询（已有） ====================
    
    def get_market_status(self, date: str):
        """获取市场情绪数据"""
        return self.query_service.get_market_status(date)
    
    def get_stock_with_concept(self, stock_code: str, date: str):
        """获取个股信息（含概念）"""
        return self.query_service.get_stock_with_concept(stock_code, date)
    
    def get_stock_popularity_rank(self, date: str, limit: int = 30):
        """获取人气榜"""
        return self.query_service.get_stock_popularity_rank(date, limit)
    
    def get_concept_leaders(self, date: str, min_limit_up: int = 1):
        """获取概念龙头"""
        return self.query_service.get_concept_leaders(date, min_limit_up)
    
    def get_concept_analysis(self, concept: str, date: str):
        """获取概念分析"""
        return self.query_service.get_concept_analysis(concept, date)
    
    def list_concept_stocks(self, concept_name: str):
        """获取概念下的股票"""
        return self.stock_concept_manager.list_concept_stocks(concept_name)
    
    def add_stock_to_concept(self, stock_code: str, concept_name: str, is_core: bool, note: str):
        """添加股票到概念"""
        return self.stock_concept_manager.add_stock_to_concept(stock_code, concept_name, is_core, note)
    
    def remove_stock_from_concept(self, stock_code: str, concept_name: str):
        """从概念中移除股票"""
        return self.stock_concept_manager.remove_stock_from_concept(stock_code, concept_name)
    
    # ==================== 新增：股票池管理 ====================
    
    def get_stock_pool(self, active_only: bool = True) -> List[Dict]:
        """
        获取股票池
        
        Args:
            active_only: 是否只返回活跃股票（默认True）
        
        Returns:
            股票列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if active_only:
            cursor.execute('''
                SELECT stock_code, stock_name, market, added_date, note
                FROM stock_pool
                WHERE is_active = 1
                ORDER BY stock_code
            ''')
        else:
            cursor.execute('''
                SELECT stock_code, stock_name, market, added_date, note, is_active
                FROM stock_pool
                ORDER BY stock_code
            ''')
        
        stocks = []
        for row in cursor.fetchall():
            stock = {
                "code": row[0],
                "name": row[1],
                "market": row[2],
                "added_date": row[3] or "",
                "note": row[4] or ""
            }
            if not active_only:
                stock["is_active"] = row[5]
            stocks.append(stock)
        
        conn.close()
        return stocks
    
    def add_stock_to_pool(self, stock_code: str, stock_name: str, market: str, note: str = "") -> bool:
        """
        添加股票到池
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            market: 市场（SH/SZ）
            note: 备注
        
        Returns:
            是否成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO stock_pool
                (stock_code, stock_name, market, is_active, added_date, note)
                VALUES (?, ?, ?, 1, date('now'), ?)
            ''', (stock_code, stock_name, market, note))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"添加股票失败: {e}")
            return False
    
    def remove_stock_from_pool(self, stock_code: str) -> bool:
        """
        从池中移除股票（软删除，设置为不活跃）
        
        Args:
            stock_code: 股票代码
        
        Returns:
            是否成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE stock_pool
                SET is_active = 0
                WHERE stock_code = ?
            ''', (stock_code,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"移除股票失败: {e}")
            return False
    
    def sync_stock_info(self, stock_code: str, stock_name: str, market: str, board_type: str) -> bool:
        """
        同步股票信息到 stock_info 表
        
        如果股票已存在则更新，不存在则插入
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            market: 市场（SH/SZ）
            board_type: 板块类型（主板/创业板/科创板/北交所）
        
        Returns:
            是否成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 使用 INSERT OR REPLACE 确保数据同步
            cursor.execute('''
                INSERT OR REPLACE INTO stock_info
                (stock_code, stock_name, market, board_type, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (stock_code, stock_name, market, board_type))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"同步股票信息失败: {e}")
            return False
    
    def batch_sync_stock_info(self, stocks: List[Dict]) -> tuple:
        """
        批量同步股票信息到 stock_info 表
        
        Args:
            stocks: 股票信息列表，每项包含:
                - stock_code: 股票代码
                - stock_name: 股票名称
                - market: 市场
                - board_type: 板块类型
        
        Returns:
            (成功数量, 失败数量)
        """
        success_count = 0
        failed_count = 0
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            for stock in stocks:
                try:
                    cursor.execute('''
                        INSERT OR REPLACE INTO stock_info
                        (stock_code, stock_name, market, board_type, updated_at)
                        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (
                        stock['stock_code'],
                        stock['stock_name'],
                        stock['market'],
                        stock['board_type']
                    ))
                    success_count += 1
                except Exception as e:
                    print(f"同步 {stock.get('stock_code')} 失败: {e}")
                    failed_count += 1
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"批量同步失败: {e}")
            failed_count = len(stocks) - success_count
        
        return success_count, failed_count
    
    # ==================== 新增：概念层级管理 ====================
    
    def get_concept_hierarchy(self) -> Dict:
        """
        获取概念层级（树形结构）
        
        Returns:
            概念层级字典
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 查询所有概念
        cursor.execute('''
            SELECT concept_name, parent_concept, description, position_in_chain
            FROM concept_hierarchy
            ORDER BY parent_concept, concept_name
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        # 构建树形结构
        hierarchy = {}
        
        # 先处理顶级概念
        for row in rows:
            if row[1] is None:  # parent_concept为NULL
                hierarchy[row[0]] = {
                    "description": row[2] or "",
                    "subconcepts": {}
                }
        
        # 再处理子概念
        for row in rows:
            if row[1] is not None:  # 有父概念
                parent = row[1]
                if parent in hierarchy:
                    hierarchy[parent]["subconcepts"][row[0]] = {
                        "description": row[2] or ""
                    }
        
        return hierarchy
    
    def add_concept(self, concept_name: str, parent_concept: Optional[str], description: str) -> bool:
        """
        添加概念
        
        Args:
            concept_name: 概念名称
            parent_concept: 父概念（None表示顶级概念）
            description: 描述
        
        Returns:
            是否成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO concept_hierarchy
                (concept_name, parent_concept, description)
                VALUES (?, ?, ?)
            ''', (concept_name, parent_concept, description))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"添加概念失败: {e}")
            return False
    
    # ==================== 新增：市场数据写入 ====================
    
    def save_market_sentiment(self, date: str, data: Dict) -> bool:
        """
        保存市场情绪数据
        
        Args:
            date: 交易日期
            data: 市场数据字典
        
        Returns:
            是否成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO market_sentiment
                (trade_date, limit_up_count, limit_down_count, broken_board_count, 
                 max_streak, sh_index_change, sz_index_change, cy_index_change, 
                 kc_index_change, total_turnover)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                date,
                data.get('limit_up_count', 0),
                data.get('limit_down_count', 0),
                data.get('broken_board_count', 0),
                data.get('max_streak', 0),
                data.get('sh_index_change', 0.0),
                data.get('sz_index_change', 0.0),
                data.get('cy_index_change', 0.0),
                data.get('kc_index_change', 0.0),
                data.get('total_turnover', 0.0)
            ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"保存市场情绪失败: {e}")
            return False
    
    def save_stock_daily(self, date: str, stock: Dict) -> bool:
        """
        保存个股日行情
        
        Args:
            date: 交易日期
            stock: 个股数据字典
        
        Returns:
            是否成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 获取价格数据
            close_price = stock.get('close', 0.0)
            pre_close = stock.get('pre_close', 0.0)
            
            # 涨跌额：优先使用提供的值，否则自动计算
            change_amount = stock.get('change')
            if change_amount is None or change_amount == 0.0:
                change_amount = close_price - pre_close if pre_close != 0 else 0.0
            
            # 涨跌幅：使用数据源提供的值（更准确）
            change_percent = stock.get('change_percent', 0.0)
            
            cursor.execute('''
                INSERT OR REPLACE INTO stock_daily
                (trade_date, stock_code, stock_name, market, 
                 open_price, high_price, low_price, close_price, pre_close,
                 change_amount, change_percent, volume, turnover, turnover_rate,
                 is_limit_up, is_limit_down, limit_up_time, streak_days)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                date,
                stock.get('code'),
                stock.get('name'),
                stock.get('market'),
                stock.get('open', 0.0),
                stock.get('high', 0.0),
                stock.get('low', 0.0),
                close_price,
                pre_close,
                change_amount,
                change_percent,
                stock.get('volume', 0),
                stock.get('turnover', 0.0),
                stock.get('turnover_rate', 0.0),
                stock.get('is_limit_up', 0),
                stock.get('is_limit_down', 0),
                stock.get('limit_up_time', ''),
                stock.get('streak_days', 0)
            ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"保存个股数据失败 {stock.get('code')}: {e}")
            return False
    
    # ==================== 分时数据管理 ====================
    
    def save_intraday_data(self, date: str, stock_code: str, intraday_data: List[Dict]) -> bool:
        """
        保存分时数据
        
        Args:
            date: 交易日期（YYYY-MM-DD）
            stock_code: 股票代码
            intraday_data: 分时数据列表
        
        Returns:
            是否成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 先删除已有数据（避免重复）
            cursor.execute('''
                DELETE FROM stock_intraday 
                WHERE trade_date = ? AND stock_code = ?
            ''', (date, stock_code))
            
            # 批量插入
            for item in intraday_data:
                cursor.execute('''
                    INSERT INTO stock_intraday
                    (trade_date, stock_code, trade_time, price, change_percent, 
                     volume, turnover, avg_price)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    date, stock_code, item['trade_time'], item['price'],
                    item['change_percent'], item['volume'], item['turnover'],
                    item['avg_price']
                ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"保存分时数据失败 {stock_code}: {e}")
            return False
    
    def get_stock_quote(self, stock_code: str) -> Optional[Dict]:
        """
        获取股票实时行情（从stock_daily表获取最新一天的数据）
        
        Args:
            stock_code: 股票代码
        
        Returns:
            行情数据字典，包含：code, name, price, change, change_percent, volume, turnover, etc.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 从stock_daily获取最新一天的数据
        cursor.execute('''
            SELECT 
                sd.stock_code,
                si.stock_name,
                sd.close_price as price,
                sd.change_amount as change,
                sd.change_percent,
                sd.volume,
                sd.turnover,
                sd.turnover_rate,
                sd.high_price as high,
                sd.low_price as low,
                sd.open_price as open,
                sd.pre_close
            FROM stock_daily sd
            LEFT JOIN stock_info si ON sd.stock_code = si.stock_code
            WHERE sd.stock_code = ?
            ORDER BY sd.trade_date DESC
            LIMIT 1
        ''', (stock_code,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return {
            'code': row[0],
            'name': row[1] or stock_code,
            'price': row[2],
            'change': row[3],
            'change_percent': row[4],
            'volume': row[5],
            'turnover': row[6],
            'turnover_rate': row[7],
            'high': row[8],
            'low': row[9],
            'open': row[10],
            'prev_close': row[11]
        }
    
    def get_stock_daily(self, stock_code: str, start_date: str, end_date: str) -> List[Dict]:
        """
        获取股票日K线数据
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
        
        Returns:
            日K线数据列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                trade_date,
                open_price as open,
                high_price as high,
                low_price as low,
                close_price as close,
                volume,
                turnover,
                change_percent
            FROM stock_daily
            WHERE stock_code = ? AND trade_date BETWEEN ? AND ?
            ORDER BY trade_date ASC
        ''', (stock_code, start_date, end_date))
        
        data = []
        for row in cursor.fetchall():
            data.append({
                'date': row[0],
                'open': row[1],
                'high': row[2],
                'low': row[3],
                'close': row[4],
                'volume': row[5],
                'turnover': row[6],
                'change_percent': row[7]
            })
        
        conn.close()
        return data
    
    def batch_get_stock_quote(self, codes: List[str]) -> List[Dict]:
        """
        批量获取股票行情
        
        Args:
            codes: 股票代码列表
        
        Returns:
            行情数据列表
        """
        if not codes:
            return []
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 使用子查询获取每个股票的最新交易日期
        placeholders = ','.join('?' * len(codes))
        cursor.execute(f'''
            WITH latest_dates AS (
                SELECT stock_code, MAX(trade_date) as max_date
                FROM stock_daily
                WHERE stock_code IN ({placeholders})
                GROUP BY stock_code
            )
            SELECT 
                sd.stock_code,
                si.stock_name,
                sd.close_price as price,
                sd.change_amount as change,
                sd.change_percent,
                sd.volume,
                sd.turnover,
                sd.turnover_rate,
                sd.high_price as high,
                sd.low_price as low,
                sd.open_price as open,
                sd.pre_close
            FROM stock_daily sd
            INNER JOIN latest_dates ld ON sd.stock_code = ld.stock_code AND sd.trade_date = ld.max_date
            LEFT JOIN stock_info si ON sd.stock_code = si.stock_code
        ''', codes)
        
        quotes = []
        for row in cursor.fetchall():
            quotes.append({
                'code': row[0],
                'name': row[1] or row[0],
                'price': row[2],
                'change': row[3],
                'change_percent': row[4],
                'volume': row[5],
                'turnover': row[6],
                'turnover_rate': row[7],
                'high': row[8],
                'low': row[9],
                'open': row[10],
                'prev_close': row[11]
            })
        
        conn.close()
        return quotes
    
    def get_intraday_data(self, stock_code: str, date: str) -> List[Dict]:
        """
        获取分时数据
        
        Args:
            stock_code: 股票代码
            date: 交易日期（YYYY-MM-DD）
        
        Returns:
            分时数据列表
            
        注意：使用trade_date字段查询，因为Tushare可能返回临近交易日的数据
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 使用 trade_date 字段查询（反映请求的日期）
        cursor.execute('''
            SELECT trade_time, price, change_percent, volume, turnover, avg_price
            FROM stock_intraday
            WHERE stock_code = ? AND trade_date = ?
            ORDER BY trade_time
        ''', (stock_code, date))
        
        data = []
        for row in cursor.fetchall():
            data.append({
                'trade_time': row[0],
                'price': row[1],
                'change_percent': row[2],
                'volume': row[3],
                'turnover': row[4],
                'avg_price': row[5]
            })
        
        conn.close()
        return data


    def check_intraday_exists(self, stock_code: str, date: str) -> bool:
        """
        检查指定股票指定日期的分时数据是否存在
        
        Args:
            stock_code: 股票代码
            date: 交易日期（YYYY-MM-DD）
        
        Returns:
            True if data exists, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) 
            FROM stock_intraday 
            WHERE stock_code = ? AND trade_date = ?
        ''', (stock_code, date))
        
        count = cursor.fetchone()[0]
        conn.close()
        
        return count > 0


# 单例
_data_service: Optional[DataService] = None

def get_data_service() -> DataService:
    """获取数据服务单例"""
    global _data_service
    if _data_service is None:
        _data_service = DataService()
    return _data_service
