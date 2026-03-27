import asyncio
import os
import sys
import json
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from publishers.feishu_publisher import FeishuPublisher
from collectors.base import NewsItem
from datetime import datetime

# Load environment variables
load_dotenv()

async def test_card_push():
    print("\n🤖 Feishu Card Push Test (with Document Link)")
    print("================================================")

    chat_id = os.environ.get("FEISHU_BOT_CHAT_ID")
    if not chat_id:
        print("❌ FEISHU_BOT_CHAT_ID not set")
        return

    publisher = FeishuPublisher()

    # 1. Create realistic dummy data
    title = f"🤖 AI Daily Digest - {datetime.now().strftime('%Y-%m-%d')}"

    # Simulate HTML highlights from Gemini
    highlights = """
    <div class="highlight-item"><span class="highlight-number">1</span><span class="highlight-text">OpenAI发布GPT-5预览版，性能提升显著。</span></div>
    <div class="highlight-item"><span class="highlight-number">2</span><span class="highlight-text">Google DeepMind推出新一代机器人模型。</span></div>
    <div class="highlight-item"><span class="highlight-number">3</span><span class="highlight-text">Meta开源Llama 4，参数量高达1000B。</span></div>
    """

    # Simulate Categories
    categories = {
        "big_tech": [
            NewsItem(
                title="OpenAI Announces GPT-5 Preview",
                url="https://openai.com/blog/gpt-5",
                source="OpenAI Blog",
                category="big_tech",
                summary="OpenAI has officially announced the preview of GPT-5, featuring enhanced reasoning capabilities and multimodal support.",
                published=datetime.now()
            ),
            NewsItem(
                title="Google's Gemini 2.0 Now Available",
                url="https://blog.google/technology/ai/gemini-2",
                source="Google AI Blog",
                category="big_tech",
                summary="Gemini 2.0 brings faster inference speeds and larger context windows to developers worldwide.",
                published=datetime.now()
            )
        ],
        "industry": [
            NewsItem(
                title="AI Startup 'Molt Book' Raises $100M",
                url="https://techcrunch.com/molt-book-funding",
                source="TechCrunch",
                category="industry",
                summary="Molt Book, a new AI reading assistant, has raised $100M in Series A funding led by Sequoia.",
                published=datetime.now()
            )
        ]
    }

    category_names = {
        "big_tech": "🏢 大厂动态",
        "industry": "💰 行业投融资"
    }

    # Simulate a document URL (in production, this comes from publisher.publish())
    test_doc_url = "https://feishu.cn/docs/test-document"

    print(f"🔄 Attempting to send card to {chat_id}...")
    print(f"   With document link: {test_doc_url}")

    try:
        # This calls the exact method used in main.py, now with doc_url
        await publisher.send_digest_card(chat_id, title, highlights, categories, category_names, test_doc_url)
        print("✅ Test finished (Check logs above for success/fail message)")
    except Exception as e:
        print(f"❌ Exception during send_digest_card: {e}")

if __name__ == "__main__":
    asyncio.run(test_card_push())
