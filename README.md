# AI Daily Digest

每天自动收集 AI 行业资讯，通过 Claude 智能摘要，发送精美邮件简报。

## 功能特性

- 🏢 **大厂动态**: Apple, Google, DeepMind, OpenAI, Anthropic
- 📄 **前沿论文**: arXiv cs.AI/LG/CL/CV 最新论文
- 💰 **行业投融资**: TechCrunch, VentureBeat AI 融资新闻
- 🐦 **社交热议**: X/Twitter AI 意见领袖动态, Hacker News
- 🇨🇳 **国内动态**: 36氪等中文科技媒体

## 快速开始

### 1. 安装依赖

```bash
cd ai-daily-digest
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# Claude API (用于智能摘要)
export ANTHROPIC_API_KEY="your-api-key"

# Gmail SMTP (用于发送邮件)
export SMTP_USER="your-email@gmail.com"
export SMTP_PASSWORD="your-app-password"  # 需要使用 App Password
export TO_EMAIL="rillahai@gmail.com"
```

### 3. 本地测试

```bash
python main.py
```

### 4. 部署到 GitHub Actions

1. Fork 或 push 代码到 GitHub
2. 在 Settings → Secrets and variables → Actions 添加 secrets:
   - `ANTHROPIC_API_KEY`
   - `SMTP_USER`
   - `SMTP_PASSWORD`
3. 启用 Actions，每天北京时间 8:00 自动运行

## 配置数据源

编辑 `config/sources.yaml` 来自定义数据源：

```yaml
rss_sources:
  my_source:
    name: "自定义来源"
    url: "https://example.com/rss"
    category: "industry"
    keywords: ["AI", "LLM"]  # 留空表示全部接收
    max_items: 10
    enabled: true
```

### 添加新分类

```yaml
output:
  category_order:
    - "big_tech"
    - "papers"
    - "your_new_category"

  category_names:
    your_new_category: "🆕 新分类"
```

## Gmail 配置说明

1. 开启两步验证: Google 账户 → 安全性 → 两步验证
2. 生成应用专用密码:
   - Google 账户 → 安全性 → 应用专用密码
   - 选择"邮件"和设备，生成 16 位密码
3. 使用生成的密码作为 `SMTP_PASSWORD`

## 项目结构

```
ai-daily-digest/
├── config/
│   └── sources.yaml       # 数据源配置
├── collectors/
│   ├── base.py            # 基础类
│   ├── rss_collector.py   # RSS 采集器
│   ├── arxiv_collector.py # arXiv 采集器
│   ├── twitter_collector.py # X/Twitter 采集器
│   └── hackernews_collector.py
├── processors/
│   ├── summarizer.py      # Claude 摘要
│   └── deduper.py         # 去重排序
├── templates/
│   └── email.html         # 邮件模板
├── main.py                # 入口
├── email_sender.py        # 邮件发送
├── requirements.txt
└── .github/workflows/
    └── daily-digest.yml   # GitHub Actions
```

## 自定义邮件模板

编辑 `templates/email.html`，支持 Jinja2 模板语法。

可用变量:
- `{{ date }}` - 日期
- `{{ item_count }}` - 新闻总数
- `{{ highlights }}` - AI 生成的今日要点
- `{{ categories }}` - 分类后的新闻字典
- `{{ category_names }}` - 分类中文名映射

## License

MIT
