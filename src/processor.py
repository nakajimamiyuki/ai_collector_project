import os
import json
from openai import OpenAI
from dotenv import load_dotenv

# 加载 .env 配置
load_dotenv()

class LLMProcessor:
    def __init__(self):
        api_key = os.getenv("LLM_API_KEY")
        base_url = os.getenv("LLM_API_BASE")
        self.model = os.getenv("LLM_MODEL")
        
        if not all([api_key, base_url, self.model]):
            raise ValueError("Missing LLM credentials in .env file. Please check LLM_API_KEY, LLM_API_BASE, and LLM_MODEL.")
        
        # 初始化 OpenAI 兼容客户端 (火山引擎 Coding Plan)
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )

    def _build_prompt(self, markdown_text):
        """构建结构化提取的 Prompt"""
        return f"""你是一个专业的数据分析师。请从以下 B 站视频页面的 Markdown 文本中精准提取关键信息，并以严格的 JSON 格式返回。

要求字段：
- title: 视频标题（去除播放量、弹幕等无关信息）
- up_name: UP 主名称
- publish_time: 发布时间（格式: YYYY-MM-DD HH:MM:SS，如未找到则填 null）
- play_count: 播放量（保留原始字符串，例如 "9977.2万"）
- danmaku_count: 弹幕数量（保留原始字符串）
- tags: 视频标签 (字符串数组)
- summary: 视频核心内容总结 (50-150 字以内，基于上下文推断)
- key_points: 视频可能讨论的核心要点 (字符串数组，3-5 个)

特别注意：
1. 必须返回纯 JSON，禁止包含 ```json 代码块标记或其他解释文字。
2. 如果某字段在原文中找不到，置为 null 或空数组。
3. summary 字段需要你基于标题、标签、UP主等线索进行合理推断。

待分析文本：
---
{markdown_text[:6000]}
---

请直接输出 JSON："""

    def clean_data(self, markdown_text):
        """
        调用 LLM 将 Markdown 转化为结构化 JSON
        """
        if not markdown_text or len(markdown_text) < 20:
            print("Warning: Markdown text too short, skipping LLM processing.")
            return None
        
        prompt = self._build_prompt(markdown_text)
        
        try:
            print(f"Calling LLM ({self.model}) for structured extraction...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个数据提取助手，只返回严格 JSON 格式。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,  # 低温度，保证输出稳定
                max_tokens=2000
            )
            
            raw_output = response.choices[0].message.content.strip()
            
            # 简单清洗 LLM 可能返回的代码块标记
            if raw_output.startswith("```"):
                raw_output = raw_output.split("```")[1]
                if raw_output.startswith("json"):
                    raw_output = raw_output[4:].strip()
            
            # 验证是否为合法 JSON
            try:
                parsed = json.loads(raw_output)
                print(f"[OK] LLM extracted successfully. Title: {parsed.get('title', 'N/A')}")
                return json.dumps(parsed, ensure_ascii=False, indent=2)
            except json.JSONDecodeError as e:
                print(f"[WARN] LLM returned invalid JSON: {e}")
                print(f"Raw output: {raw_output[:300]}")
                return None
                
        except Exception as e:
            print(f"[ERROR] LLM API call failed: {e}")
            return None
