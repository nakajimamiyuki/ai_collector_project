import asyncio
from src.collector import BiliCollector

async def test_collection():
    print("--- Starting Collector Test ---")
    
    # 1. 初始化采集器 (设置 headless=False 这样你可以亲眼看到浏览器在工作)
    collector = BiliCollector(headless=False)
    
    # 准备一个测试 URL (一个真实存在的 B 站视频)
    test_url = "https://www.bilibili.com/video/BV1GJ411x7h7"
    
    # 备选 URL 列表
    backup_urls = [
        "https://www.bilibili.com/video/BV1uv411q7Mv",
        "https://www.bilibili.com/video/BV1S74y1S7yY"
    ]
    
    target_url = test_url
    
    print(f"Attempting to collect: {target_url}")
    result = await collector.collect_content(target_url)
    
    if result:
        print("\n[SUCCESS] Content Extracted Successfully!")
        print("-" * 30)
        print(result)
        print("-" * 30)
    else:
        print("\n[FAILED] Could not extract content. Trying backup...")
        for b_url in backup_urls:
            result = await collector.collect_content(b_url)
            if result:
                print("\n[SUCCESS] Backup URL worked!")
                print(result)
                break

    print("\n--- Collector Test Completed ---")

if __name__ == "__main__":
    asyncio.run(test_collection())
