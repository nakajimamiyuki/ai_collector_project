from src.processor import LLMProcessor

def test_llm():
    print("--- Starting LLM Processor Test ---")
    
    # 1. 模拟一段从 Step 3 抓取到的 B站 Markdown 内容（截取自之前测试的真实数据）
    sample_markdown = """
    # 【官方 MV】Never Gonna Give You Up - Rick Astley
    
    9977.2万播放
    13.8万弹幕
    2020-01-01 07:43:23
    
    UP主：索尼音乐中国 (粉丝 92.0万)
    
    标签：Never Gonna Give You Up, Rick Astley, 欧美MV, 流行音乐, 欧美音乐, MV
    
    描述：发现《Never gonna give you up》
    
    44.9万投币
    """
    
    # 2. 初始化处理器
    processor = LLMProcessor()
    
    # 3. 进行结构化提取
    result = processor.clean_data(sample_markdown)
    
    if result:
        print("\n[SUCCESS] LLM Structured Output:")
        print("-" * 40)
        print(result)
        print("-" * 40)
    else:
        print("\n[FAILED] LLM processing failed.")
    
    print("--- LLM Test Completed ---")

if __name__ == "__main__":
    test_llm()
