import requests
import re
from src.db_manager import DBManager
import os
from dotenv import load_dotenv

# 加载 .env 配置
load_dotenv()

class BiliMonitor:
    def __init__(self):
        # 此时不再依赖 RSSHub URL
        self.db = DBManager()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/"
        }

    def fetch_bilibili_urls(self, uid):
        """
        直接调用 B 站公开接口获取用户最新视频列表
        接口: https://api.bilibili.com/x/space/arc/search
        """
        print(f"Directly scanning Bilibili API for UID {uid}...")
        
        params = {
            "uid": uid,
            "pn": 1,           # 第一页
            "ps": 30,          # 每页 30 条
            "std": 0           # 排序方式
        }
        
        try:
            # 使用 requests 直接请求 API
            response = requests.get("https://api.bilibili.com/x/space/arc/search", params=params, headers=self.headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") == -111:
                print(f"Error: UID {uid} not found or access denied.")
                return []
            
            # 提取视频链接
            video_list = data.get("data", {}).get("list", [])
            urls = []
            for video in video_list:
                # 构造完整的 B 站视频链接
                bvid = video.get("bvid")
                if bvid:
                    urls.append(f"https://www.bilibili.com/video/{bvid}")
            
            print(f"Found {len(urls)} latest videos for UID {uid}.")
            return urls
            
        except Exception as e:
            print(f"Error fetching Bilibili API for UID {uid}: {e}")
            return []

    def sync_targets(self, target_uids):
        """
        同步多个目标的更新情况
        """
        total_added = 0
        for uid in target_uids:
            urls = self.fetch_bilibili_urls(uid)
            if urls:
                added = self.db.add_new_urls(urls)
                print(f"UID {uid}: Added {added} new tasks to queue.")
                total_added += added
        
        print(f"Sync completed. Total new tasks added: {total_added}")
        return total_added
