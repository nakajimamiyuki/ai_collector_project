import asyncio
import logging
import random
import os
import sqlite3
from datetime import datetime
from src.db_manager import DBManager
from src.monitor import BiliMonitor
from src.collector import BiliCollector
from src.processor import LLMProcessor

# ===== 日志配置 =====
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('logs/pipeline.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class AIPipeline:
    """AI 信息采集流水线总调度"""
    
    # 目标 UP 主 UID
    TARGET_UIDS = [
        '285286947',    # 橘鸦Juya
        '1333131174',   # 稚晖君
    ]
    
    def __init__(self, headless=True):
        self.db = DBManager()
        self.monitor = BiliMonitor()
        self.collector = BiliCollector(headless=headless)
        self.processor = LLMProcessor()
        logger.info("=" * 60)
        logger.info("AI Pipeline Initialized.")
        logger.info("=" * 60)
    
    # =========== 阶段 1: 监控 ===========
    def stage1_monitor(self):
        """发现新 URL"""
        logger.info("[Stage 1] Monitoring targets for new content...")
        added = self.monitor.sync_targets(self.TARGET_UIDS)
        logger.info(f"[Stage 1] Done. {added} new URLs added to queue.")
        return added
    
    # =========== 阶段 2: 采集 ===========
    async def stage2_collect(self, max_count=5):
        """从队列取出 PENDING 任务，使用 Playwright 抓取"""
        logger.info(f"[Stage 2] Fetching up to {max_count} pending tasks...")
        
        # 从数据库查 PENDING 任务
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT url FROM task_queue WHERE status='PENDING' LIMIT ?", (max_count,))
        pending_urls = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        if not pending_urls:
            logger.info("[Stage 2] No pending tasks.")
            return 0
        
        success_count = 0
        for i, url in enumerate(pending_urls, 1):
            logger.info(f"[Stage 2] ({i}/{len(pending_urls)}) Collecting: {url}")
            
            # 标记为 PROCESSING
            self.db.update_task_status(url, "PROCESSING")
            
            try:
                content = await self.collector.collect_content(url)
                
                if content and len(content) > 50:
                    # 存原文 (save_raw_content 内部会自动更新状态为 COLLECTED)
                    self.db.save_raw_content(url, content)
                    logger.info(f"[Stage 2] OK ({len(content)} chars)")
                    success_count += 1
                else:
                    self.db.update_task_status(url, "FAILED")
                    logger.warning(f"[Stage 2] Empty content for {url}")
            except Exception as e:
                self.db.update_task_status(url, "FAILED")
                logger.error(f"[Stage 2] Failed: {e}")
            
            # 反爬限流：随机延迟 3-8 秒
            if i < len(pending_urls):
                delay = random.uniform(3, 8)
                logger.info(f"[Stage 2] Sleeping {delay:.1f}s before next...")
                await asyncio.sleep(delay)
        
        logger.info(f"[Stage 2] Done. {success_count}/{len(pending_urls)} collected.")
        return success_count
    
    # =========== 阶段 3: LLM 清洗 ===========
    def stage3_process(self, max_count=5):
        """从已采集任务中取出，调用 LLM 提取结构化数据"""
        logger.info(f"[Stage 3] Processing up to {max_count} collected tasks with LLM...")
        
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.url, r.markdown_text 
            FROM task_queue t 
            JOIN raw_contents r ON t.url = r.url 
            WHERE t.status='COLLECTED' LIMIT ?
        """, (max_count,))
        tasks = cursor.fetchall()
        conn.close()
        
        if not tasks:
            logger.info("[Stage 3] No collected tasks waiting for LLM.")
            return 0
        
        success_count = 0
        for i, (url, markdown) in enumerate(tasks, 1):
            logger.info(f"[Stage 3] ({i}/{len(tasks)}) Cleaning: {url}")
            
            try:
                json_result = self.processor.clean_data(markdown)
                
                if json_result:
                    # save_final_result 内部会自动更新状态为 COMPLETED
                    self.db.save_final_result(url, json_result)
                    logger.info(f"[Stage 3] OK")
                    success_count += 1
                else:
                    self.db.update_task_status(url, "FAILED")
                    logger.warning(f"[Stage 3] LLM returned empty result")
            except Exception as e:
                self.db.update_task_status(url, "FAILED")
                logger.error(f"[Stage 3] Failed: {e}")
        
        logger.info(f"[Stage 3] Done. {success_count}/{len(tasks)} processed.")
        return success_count
    
    # =========== 主流程 ===========
    async def run(self):
        """执行完整的流水线"""
        start_time = datetime.now()
        logger.info(f"\n>>> Pipeline started at {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # 阶段 1: 监控
        new_urls = self.stage1_monitor()
        
        # 阶段 2: 采集
        collected = await self.stage2_collect(max_count=3)
        
        # 阶段 3: LLM 清洗
        processed = self.stage3_process(max_count=3)
        
        # 总结
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.info("\n" + "=" * 60)
        logger.info(f">>> Pipeline completed in {duration:.1f}s")
        logger.info(f"   New URLs:   {new_urls}")
        logger.info(f"   Collected:  {collected}")
        logger.info(f"   Processed:  {processed}")
        logger.info("=" * 60 + "\n")


def show_results():
    """展示数据库里的最终结果"""
    db = DBManager()
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT url, structured_json, processed_at FROM final_results ORDER BY processed_at DESC LIMIT 5")
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("\n[INFO] No completed results yet.")
        return
    
    print("\n" + "=" * 60)
    print("Latest Final Results:")
    print("=" * 60)
    for url, json_data, ts in rows:
        print(f"\nURL: {url}")
        print(f"Completed: {ts}")
        print(f"Data:\n{json_data}")
        print("-" * 60)


if __name__ == "__main__":
    pipeline = AIPipeline(headless=True)
    asyncio.run(pipeline.run())
    show_results()
