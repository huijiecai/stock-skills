"""导入热门概念成分股数据"""
import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.core.database import AsyncSessionLocal
from app.core.logger import setup_logging, get_logger

setup_logging("INFO")
logger = get_logger(__name__)


# 热门概念及其成分股数据（手动整理的常用概念）
HOT_CONCEPTS_DATA = {
    "BK0917": {  # 半导体概念
        "name": "半导体概念",
        "stocks": [
            ("688981", "中芯国际", True, "晶圆代工龙头"),
            ("688041", "海光信息", True, "CPU+DCU双轮驱动"),
            ("688012", "中微公司", True, "刻蚀设备龙头"),
            ("688126", "沪硅产业", False, "半导体硅片"),
            ("002371", "北方华创", True, "半导体设备平台"),
            ("603501", "韦尔股份", True, "CIS芯片设计"),
            ("688008", "澜起科技", False, "内存接口芯片"),
            ("688187", "时代电气", False, "IGBT模块"),
            ("688396", "华润微", False, "功率半导体"),
            ("600584", "长电科技", False, "封测龙头"),
        ]
    },
    "BK0900": {  # 新能源车
        "name": "新能源车",
        "stocks": [
            ("300750", "宁德时代", True, "动力电池龙头"),
            ("002594", "比亚迪", True, "新能源车整车"),
            ("300014", "亿纬锂能", False, "锂电池"),
            ("002460", "赣锋锂业", False, "锂矿资源"),
            ("300035", "中科电气", False, "负极材料"),
            ("603799", "华友钴业", False, "钴镍资源"),
            ("002466", "天齐锂业", False, "锂矿"),
            ("688005", "容百科技", False, "正极材料"),
            ("300769", "德方纳米", False, "磷酸铁锂"),
            ("002812", "恩捷股份", False, "锂电隔膜"),
        ]
    },
    "BK0854": {  # 华为概念
        "name": "华为概念",
        "stocks": [
            ("002456", "欧菲光", False, "华为摄像头供应商"),
            ("300346", "南大光电", False, "光刻胶"),
            ("002384", "东山精密", False, "FPC柔性电路板"),
            ("600745", "闻泰科技", False, "ODM代工"),
            ("000063", "中兴通讯", True, "5G通信设备"),
            ("601127", "赛力斯", True, "华为汽车合作伙伴"),
            ("300502", "新易盛", False, "光模块"),
            ("002415", "海康威视", False, "智能安防"),
            ("002230", "科大讯飞", True, "AI语音技术"),
            ("688111", "金山办公", False, "办公软件"),
        ]
    },
    "BK1090": {  # 机器人概念
        "name": "机器人概念",
        "stocks": [
            ("300124", "汇川技术", True, "工业自动化"),
            ("002747", "埃斯顿", True, "工业机器人"),
            ("688169", "石头科技", False, "服务机器人"),
            ("603160", "汇顶科技", False, "传感器"),
            ("300607", "拓斯达", False, "机器人集成"),
            ("002008", "大族激光", False, "激光加工"),
            ("688065", "凯赛生物", False, "生物基材料"),
            ("300024", "机器人", True, "机器人本体"),
            ("688303", "大全能源", False, "多晶硅"),
            ("002611", "东方精工", False, "智能包装"),
        ]
    },
    "BK0989": {  # 储能概念
        "name": "储能概念",
        "stocks": [
            ("300750", "宁德时代", True, "储能电池"),
            ("002518", "科士达", True, "储能逆变器"),
            ("300274", "阳光电源", True, "光伏逆变器+储能"),
            ("688390", "固德威", False, "储能逆变器"),
            ("605117", "德业股份", False, "微逆变器"),
            ("300763", "锦浪科技", False, "组串式逆变器"),
            ("002335", "科华数据", False, "储能系统集成"),
            ("688349", "三一重能", False, "风电+储能"),
            ("300827", "上能电气", False, "储能PCS"),
            ("600481", "双良节能", False, "储能热管理"),
        ]
    },
    "BK0707": {  # 人工智能
        "name": "人工智能",
        "stocks": [
            ("002230", "科大讯飞", True, "AI语音龙头"),
            ("688187", "时代电气", False, "AI芯片"),
            ("603019", "中科曙光", True, "AI服务器"),
            ("002415", "海康威视", True, "AI视觉"),
            ("688111", "金山办公", False, "AI办公"),
            ("300496", "中科创达", False, "AI操作系统"),
            ("600588", "用友网络", False, "AI企业应用"),
            ("002261", "拓维信息", False, "AI算力"),
            ("601360", "三六零", False, "AI安全"),
            ("688369", "致远互联", False, "AI协同办公"),
        ]
    },
}


async def import_concept_components():
    """导入概念成分股数据"""
    
    logger.info("=" * 60)
    logger.info("开始导入热门概念成分股数据")
    logger.info("=" * 60)
    
    async with AsyncSessionLocal() as session:
        total_imported = 0
        total_skipped = 0
        
        for concept_code, concept_data in HOT_CONCEPTS_DATA.items():
            concept_name = concept_data["name"]
            stocks = concept_data["stocks"]
            
            logger.info(f"\n导入概念: {concept_name} ({concept_code})")
            logger.info(f"成分股数量: {len(stocks)}")
            
            for stock_code, stock_name, is_core, reason in stocks:
                try:
                    # 检查是否已存在
                    check_result = await session.execute(
                        text("""
                            SELECT COUNT(*) FROM stock_concept_mapping_east 
                            WHERE stock_code = :stock_code AND concept_code = :concept_code
                        """),
                        {
                            "stock_code": stock_code,
                            "concept_code": concept_code
                        }
                    )
                    exists = check_result.scalar()
                    
                    if exists > 0:
                        # 更新现有记录
                        await session.execute(
                            text("""
                                UPDATE stock_concept_mapping_east 
                                SET is_core = :is_core, reason = :reason
                                WHERE stock_code = :stock_code AND concept_code = :concept_code
                            """),
                            {
                                "stock_code": stock_code,
                                "concept_code": concept_code,
                                "is_core": is_core,
                                "reason": reason
                            }
                        )
                        total_skipped += 1
                        logger.debug(f"  更新: {stock_code} {stock_name}")
                    else:
                        # 插入新记录
                        await session.execute(
                            text("""
                                INSERT INTO stock_concept_mapping_east 
                                (stock_code, concept_code, is_core, reason)
                                VALUES (:stock_code, :concept_code, :is_core, :reason)
                            """),
                            {
                                "stock_code": stock_code,
                                "concept_code": concept_code,
                                "is_core": is_core,
                                "reason": reason
                            }
                        )
                        total_imported += 1
                        logger.info(f"  ✓ 导入: {stock_code} {stock_name} ({'核心' if is_core else '普通'})")
                        
                except Exception as e:
                    logger.error(f"  ✗ 失败: {stock_code} {stock_name} - {e}")
            
            await session.commit()
            logger.info(f"  ✅ 概念 {concept_name} 导入完成")
        
        logger.info("\n" + "=" * 60)
        logger.info(f"导入完成!")
        logger.info(f"  新增: {total_imported} 条")
        logger.info(f"  更新: {total_skipped} 条")
        logger.info(f"  总计: {total_imported + total_skipped} 条")
        logger.info("=" * 60)


async def verify_import():
    """验证导入结果"""
    async with AsyncSessionLocal() as session:
        logger.info("\n验证导入结果:")
        logger.info("-" * 60)
        
        for concept_code in HOT_CONCEPTS_DATA.keys():
            result = await session.execute(
                text("""
                    SELECT COUNT(*) FROM stock_concept_mapping_east 
                    WHERE concept_code = :concept_code
                """),
                {"concept_code": concept_code}
            )
            count = result.scalar()
            concept_name = HOT_CONCEPTS_DATA[concept_code]["name"]
            logger.info(f"  {concept_name} ({concept_code}): {count} 只成分股")


async def main():
    """主函数"""
    try:
        await import_concept_components()
        await verify_import()
        
        logger.info("\n✅ 数据导入成功!")
        logger.info("现在可以在前端页面查看板块成分股数据了")
        
    except Exception as e:
        logger.error(f"❌ 导入失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
