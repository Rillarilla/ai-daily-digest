"""Test full flow: Create document then send card with real link."""
import asyncio
import os
import sys
from dotenv import load_dotenv
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from publishers.feishu_publisher import FeishuPublisher
from collectors.base import NewsItem

load_dotenv()

async def test_full_flow():
    print("\n🤖 Full Flow Test: Document + Card")
    print("=" * 50)

    chat_id = os.environ.get("FEISHU_BOT_CHAT_ID")
    if not chat_id:
        print("❌ FEISHU_BOT_CHAT_ID not set")
        return

    publisher = FeishuPublisher()
    if not publisher.is_configured():
        print("❌ Feishu publisher not configured")
        return

    date_str = datetime.now().strftime('%Y-%m-%d')
    title = f"🤖 AI Daily Digest - {date_str}"

    # Create markdown content for the document
    md_content = f"""## ⚡ 今日要点

1. OpenAI发布GPT-5预览版，性能提升显著。
2. Google DeepMind推出新一代机器人模型。
3. Meta开源Llama 4，参数量高达1000B。

## 🏢 大厂动态

### [OpenAI Announces GPT-5 Preview](https://openai.com/blog/gpt-5)
- 来源: OpenAI Blog
- 摘要: OpenAI has officially announced the preview of GPT-5, featuring enhanced reasoning capabilities.

### [Google's Gemini 2.0 Now Available](https://blog.google/technology/ai/gemini-2)
- 来源: Google AI Blog
- 摘要: Gemini 2.0 brings faster inference speeds and larger context windows.

## 💰 行业投融资

### [AI Startup Raises $100M](https://techcrunch.com/funding)
- 来源: TechCrunch
- 摘要: A new AI reading assistant has raised $100M in Series A funding.
"""

    # Step 1: Create the document with chat_id for permission
    print("\n📄 Step 1: Creating Feishu document...")
    doc_url = await publisher.publish(title, md_content, chat_id)

    if not doc_url:
        print("❌ Failed to create document")
        return

    print(f"   Document URL: {doc_url}")

    # Step 2: Send card with the real document link
    print("\n📨 Step 2: Sending simplified card (only highlights + button)...")

    # Simplified highlights - only 3 eye-catching items
    highlights = """1. OpenAI发布GPT-5预览版，推理能力大幅提升，支持实时语音对话。

2. Google DeepMind推出新一代机器人模型，可完成复杂物理任务。

3. AI初创公司融资热度不减，本周累计融资超5亿美元。"""

    categories = {
        "big_tech": [
            NewsItem(
                title="OpenAI Announces GPT-5 Preview",
                url="https://openai.com/blog/gpt-5",
                source="OpenAI Blog",
                category="big_tech",
                summary="OpenAI发布GPT-5预览版",
                published=datetime.now()
            ),
        ],
        "industry": [
            NewsItem(
                title="AI Startup Raises $100M",
                url="https://techcrunch.com/funding",
                source="TechCrunch",
                category="industry",
                summary="AI初创公司融资1亿美元",
                published=datetime.now()
            )
        ]
    }

    category_names = {
        "big_tech": "🏢 大厂动态",
        "industry": "💰 行业投融资"
    }

    await publisher.send_digest_card(chat_id, title, highlights, categories, category_names, doc_url)

    print("\n✅ Full flow test complete!")
    print(f"   Check your Feishu group - click the button to open: {doc_url}")

if __name__ == "__main__":
    asyncio.run(test_full_flow())
