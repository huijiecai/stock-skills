from datetime import datetime
from typing import Dict, List, Optional
from app.services.data_service import get_data_service


class AnalysisService:
    """龙头战法分析服务"""
    
    def __init__(self):
        self.data_service = get_data_service()
    
    def analyze_stock(self, code: str, date: str) -> Dict:
        """
        分析单只股票是否符合龙头战法
        
        Args:
            code: 股票代码
            date: 分析日期（格式：YYYY-MM-DD）
        
        Returns:
            分析结果字典
        """
        # 1. 获取市场情绪
        market = self.data_service.get_market_status(date)
        
        # 2. 获取个股信息
        try:
            stock = self.data_service.get_stock_with_concept(code, date)
        except Exception as e:
            return {
                "success": False,
                "error": f"股票数据获取失败: {str(e)}"
            }
        
        # 3. 计算人气度排名
        popularity = self.data_service.get_stock_popularity_rank(date, 100)
        rank = next((i for i, s in enumerate(popularity) if s['stock_code'] == code), None)
        
        # 4. 判断龙头标准
        is_leader = self._check_leader_criteria(stock, market, rank)
        
        # 5. 生成建议
        suggestion = self._generate_suggestion(stock, market, rank, is_leader)
        
        return {
            "success": True,
            "stock_code": code,
            "stock_name": stock.get('stock_name', ''),
            "date": date,
            "market_phase": market.get('market_phase', '正常'),
            "market_sentiment": {
                "limit_up_count": market.get('limit_up_count', 0),
                "limit_down_count": market.get('limit_down_count', 0),
                "max_streak": market.get('max_streak', 0)
            },
            "popularity_rank": rank + 1 if rank is not None else None,
            "change_percent": stock.get('change_percent', 0) * 100,
            "turnover": stock.get('turnover', 0),
            "concepts": stock.get('concepts', []),
            "is_leader_candidate": is_leader,
            "suggestion": suggestion
        }
    
    def analyze_concept(self, concept_name: str, date: str) -> Dict:
        """
        分析概念内所有股票
        
        Args:
            concept_name: 概念名称
            date: 分析日期
        
        Returns:
            概念分析结果
        """
        # 获取概念分析
        concept_data = self.data_service.get_concept_analysis(concept_name, date)
        
        # 获取概念下的股票
        stocks = self.data_service.list_concept_stocks(concept_name)
        
        # 批量分析概念内股票
        stock_analyses = []
        for stock in stocks[:10]:  # 限制前10只，避免过慢
            analysis = self.analyze_stock(stock['stock_code'], date)
            if analysis['success']:
                stock_analyses.append(analysis)
        
        return {
            "success": True,
            "concept_name": concept_name,
            "date": date,
            "concept_stats": concept_data,
            "stock_count": len(stocks),
            "stock_analyses": stock_analyses
        }
    
    def _check_leader_criteria(self, stock: Dict, market: Dict, rank: Optional[int]) -> bool:
        """
        判断是否符合龙头标准
        
        龙头标准：
        1. 人气度：进入成交额前30
        2. 逻辑正宗：有核心概念归属
        3. 涨幅突出：涨幅>3%或涨停
        """
        # 人气度检查
        if rank is None or rank >= 30:
            return False
        
        # 逻辑正宗性检查
        concepts = stock.get('concepts', [])
        has_core_concept = any(c.get('is_core', False) for c in concepts)
        if not has_core_concept:
            return False
        
        # 涨幅检查
        change_percent = stock.get('change_percent', 0)
        if change_percent < 0.03:  # 涨幅低于3%
            return False
        
        return True
    
    def _generate_suggestion(self, stock: Dict, market: Dict, rank: Optional[int], is_leader: bool) -> str:
        """
        生成操作建议
        """
        if not is_leader:
            if rank is None or rank >= 30:
                return "⚠️ 人气不足，不符合龙头标准，建议观望"
            elif not stock.get('concepts'):
                return "⚠️ 无明确概念归属，逻辑不够正宗，建议观望"
            else:
                return "⚠️ 涨幅不足，暂不符合龙头标准，可继续观察"
        
        market_phase = market.get('market_phase', '正常')
        
        if market_phase == '冰点':
            return "✅ 符合龙头标准，市场冰点期，可关注修复机会"
        elif market_phase == '主升':
            return "✅ 符合龙头标准，市场主升期，注意分时承接和高开强度"
        else:
            return "✅ 符合龙头标准，等待明日确认信号（高开+强承接）"


# 单例
_analysis_service: Optional[AnalysisService] = None

def get_analysis_service() -> AnalysisService:
    """获取分析服务单例"""
    global _analysis_service
    if _analysis_service is None:
        _analysis_service = AnalysisService()
    return _analysis_service
