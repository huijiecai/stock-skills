"""定时任务定义"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime

from app.core.logger import get_logger

logger = get_logger(__name__)

# 创建调度器
scheduler = AsyncIOScheduler()


async def collect_daily_data():
    """采集日线数据"""
    from app.services.data_collector import data_collector
    logger.info("开始采集日线数据...")
    try:
        await data_collector.collect_all_daily()
        logger.info("✅ 日线数据采集完成")
    except Exception as e:
        logger.error(f"❌ 日线数据采集失败: {e}")


async def collect_intraday_data():
    """采集分时数据"""
    from app.services.data_collector import data_collector
    logger.info("开始采集分时数据...")
    try:
        await data_collector.collect_all_intraday()
        logger.info("✅ 分时数据采集完成")
    except Exception as e:
        logger.error(f"❌ 分时数据采集失败: {e}")


async def collect_concept_data():
    """采集概念板块数据"""
    from app.services.data_collector import data_collector
    logger.info("开始采集概念板块数据...")
    try:
        await data_collector.collect_concepts()
        logger.info("✅ 概念板块数据采集完成")
    except Exception as e:
        logger.error(f"❌ 概念板块数据采集失败: {e}")


async def collect_limit_list():
    """采集涨跌停数据"""
    from app.services.data_collector import data_collector
    logger.info("开始采集涨跌停数据...")
    try:
        await data_collector.collect_limit_list()
        logger.info("✅ 涨跌停数据采集完成")
    except Exception as e:
        logger.error(f"❌ 涨跌停数据采集失败: {e}")


async def update_concept_mapping():
    """更新概念成分股映射"""
    from app.services.data_collector import data_collector
    logger.info("开始更新概念成分股映射...")
    try:
        await data_collector.update_concept_mapping()
        logger.info("✅ 概念成分股映射更新完成")
    except Exception as e:
        logger.error(f"❌ 概念成分股映射更新失败: {e}")


def init_jobs():
    """初始化定时任务"""
    logger.info("初始化定时任务...")
    
    # 每个交易日 19:30 采集日线数据
    scheduler.add_job(
        collect_daily_data,
        CronTrigger(day_of_week='mon-fri', hour=19, minute=30),
        id='daily_data_collector',
        replace_existing=True,
    )
    
    # 每个交易日 19:35 采集分时数据
    scheduler.add_job(
        collect_intraday_data,
        CronTrigger(day_of_week='mon-fri', hour=19, minute=35),
        id='intraday_data_collector',
        replace_existing=True,
    )
    
    # 每个交易日 19:40 采集概念板块数据
    scheduler.add_job(
        collect_concept_data,
        CronTrigger(day_of_week='mon-fri', hour=19, minute=40),
        id='concept_data_collector',
        replace_existing=True,
    )
    
    # 每个交易日 19:45 采集涨跌停数据
    scheduler.add_job(
        collect_limit_list,
        CronTrigger(day_of_week='mon-fri', hour=19, minute=45),
        id='limit_list_collector',
        replace_existing=True,
    )
    
    # 每周一 09:00 更新概念成分股映射
    scheduler.add_job(
        update_concept_mapping,
        CronTrigger(day_of_week='mon', hour=9, minute=0),
        id='concept_mapping_updater',
        replace_existing=True,
    )
    
    logger.info("✅ 定时任务初始化完成")
