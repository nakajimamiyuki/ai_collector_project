from src.monitor import BiliMonitor

def test_monitor_sync():
    print("--- Starting Direct BiliMonitor Sync Test ---")
    
    # 1. 初始化监控器
    monitor = BiliMonitor()
    
    # 2. 定义目标 UID (橘鸦Juya 和 稚晖君)
    targets = ['285286947', '1333131174']
    
    # 3. 执行同步
    print("Syncing directly with Bilibili API...")
    added_count = monitor.sync_targets(targets)
    
    if added_count > 0:
        print(f"\n[SUCCESS] Successfully discovered {added_count} new videos!")
    else:
        print("\n[INFO] No new updates found or already in database.")
    
    print("--- Monitor Test Completed ---")

if __name__ == "__main__":
    test_monitor_sync()
