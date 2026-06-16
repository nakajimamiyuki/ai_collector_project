import os
from src.db_manager import DBManager

def test_database_workflow():
    print("--- Starting DBManager Test ---")
    
    # 1. 初始化数据库
    db = DBManager(db_path="data/test_collector.db")
    print("[OK] Database initialized.")

    # 2. 测试添加新 URL
    test_urls = [
        "https://example.com/article1",
        "https://example.com/article2",
        "https://example.com/article1" # 重复 URL，用于测试去重
    ]
    added = db.add_new_urls(test_urls)
    print(f"[OK] Added {added} new URLs (Expected: 2).")

    # 3. 测试获取待处理任务
    pending = db.get_pending_tasks(limit=5)
    print(f"[OK] Pending tasks: {pending} (Expected: 2 URLs).")

    # 4. 测试更新状态为 PROCESSING
    url_to_test = pending[0]
    db.update_task_status(url_to_test, "PROCESSING")
    print(f"[OK] Updated {url_to_test} to PROCESSING.")

    # 5. 测试保存采集到的内容 (Markdown)
    sample_markdown = "# Test Title\nThis is some sample content from Playwright."
    db.save_raw_content(url_to_test, sample_markdown)
    print(f"[OK] Saved raw content for {url_to_test}.")

    # 6. 测试保存 LLM 结构化结果
    sample_json = '{"title": "Test Title", "summary": "A sample summary"}'
    db.save_final_result(url_to_test, sample_json)
    print(f"[OK] Saved final structured result for {url_to_test}.")

    # 7. 验证最终状态
    # 我们尝试再次获取 pending 任务，刚才那个应该已经消失了
    remaining_pending = db.get_pending_tasks()
    print(f"[OK] Remaining pending: {len(remaining_pending)} (Expected: 1).")

    print("--- All DB Tests Passed Successfully! ---")

if __name__ == "__main__":
    try:
        test_database_workflow()
    except Exception as e:
        print(f"[FAILED] Test encountered an error: {e}")
