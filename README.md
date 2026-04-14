# AI Daily Digest

每天自动收集 AI 行业资讯，通过 Google Gemini 智能摘要，发送精美邮件简报。

## 功能特性

- 🏢 **大厂动态**: Apple, Google, DeepMind, OpenAI, Anthropic
- 📄 **前沿论文**: arXiv cs.AI/LG/CL/CV 最新论文
- 💰 **行业投融资**: TechCrunch, VentureBeat AI 融资新闻
- 🐦 **社交热议**: Hacker News (Twitter 暂不可用)
- 🇨🇳 **国内动态**: 36氪等中文科技媒体

## 快速开始

### 1. 安装依赖

#### Python 依赖
```bash
cd ai-daily-digest
pip install -r requirements.txt
```

#### 系统依赖 (用于生成 PDF)
本项目使用 WeasyPrint 生成 PDF 附件。如果不需要 PDF 功能，可以忽略此步。

**macOS:**
```bash
brew install pango libffi
```

**Ubuntu/Debian:**
```bash
# 系统依赖
sudo apt-get install build-essential python3-dev python3-pip python3-setuptools python3-wheel python3-cffi libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info

# 中文字体 (解决 PDF 中文乱码)
sudo apt-get install fonts-noto-cjk fonts-wqy-zenhei
```

### 2. 配置环境变量

```bash
# Gemini API (用于智能摘要)
export GEMINI_API_KEY="your-gemini-api-key"

# Gmail SMTP (用于发送邮件)
export SMTP_USER="your-email@gmail.com"
export SMTP_PASSWORD="your-app-password"  # 需要使用 App Password
export TO_EMAIL="XXXXXXX@gmail.com"
```

### 3. 本地测试

```bash
python main.py
```

### 4. 部署到 GitHub Actions

1. Fork 或 push 代码到 GitHub
2. 在 Settings → Secrets and variables → Actions 添加 secrets:
   - `GEMINI_API_KEY`
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
│   ├── summarizer.py      # Gemini 摘要
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
