#!/usr/bin/env python3
"""
HK-AI-Dashboard 情报抓取脚本
- 精准抓取 Google News RSS（物流/海关主题）
- 抓取香港海关与中国海关公告页面
- 可维护式站点配置，便于后续扩展
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus
import html as html_lib
try:
    import feedparser
except ImportError:
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "feedparser"])
    import feedparser

try:
    import requests
except ImportError:
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None


# 中文物流關鍵詞（配大中華視角地區）
CN_TOPICS = [
    "香港 物流 海關",
    "海運 港口 動態",
    "空運 貨運 燃油附加費",
    "陸運 跨境貨車 通關",
    "倉儲 供應鏈 政策",
    "跨境電商 物流",
    "中國 海關 公告",
    "關稅 貿易政策",
]

# 英文物流關鍵詞（配國際英文視角地區）
EN_TOPICS = [
    "shipping tariff trade policy",
    "port congestion strike",
    "air cargo freight rates",
    "supply chain disruption",
    "section 301 tariff",
    "customs trade regulation",
]

REGION_ZH = {"hl": "zh-TW", "gl": "HK", "ceid": "HK:zh-Hant"}
REGION_EN = {"hl": "en-US", "gl": "US", "ceid": "US:en"}

GOOGLE_NEWS_QUERIES = (
    [{"q": t, **REGION_ZH} for t in CN_TOPICS] +
    [{"q": t, **REGION_EN} for t in EN_TOPICS]
)

SOURCE_CONFIG = [
    {
        "id": "hk-customs-press",
        "name": "香港海關 新聞公報",
        "type": "html",
        "url": "https://www.customs.gov.hk/tc/customs-announcement/press-release/index.html",
        "category": "hongkong",
        "region": "hongkong",
        "icon": "🇭🇰",
        "src_class": "src-hk",
        "cat_class": "cat-hk-bg",
        "item_pattern": r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
    },
    {
        "id": "hk-customs-whatsnew",
        "name": "香港海關 最新消息",
        "type": "html",
        "url": "https://www.customs.gov.hk/tc/customs-announcement/whats-new/index.html",
        "category": "hongkong",
        "region": "hongkong",
        "icon": "🇭🇰",
        "src_class": "src-hk",
        "cat_class": "cat-hk-bg",
        "item_pattern": r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
    },
    {
        "id": "cn-customs-news",
        "name": "中國海關 總署新聞",
        "type": "html",
        "url": "http://www.customs.gov.cn/customs/xwfb34/index.html",
        "category": "china",
        "region": "china",
        "icon": "🇨🇳",
        "src_class": "src-china",
        "cat_class": "cat-china-bg",
        "item_pattern": r'<a[^>]+href="([^"]+)"[^>]*title="([^"]+)"',
    }
]

KEYWORDS = [
    "shipping", "logistics", "port", "customs", "tariff", "trade",
    "maritime", "freight", "container", "cargo", "supply chain",
    "航运", "物流", "港口", "海关", "關稅", "贸易", "海關", "供應鏈",
]


TRANSLATOR = GoogleTranslator(source="auto", target="zh-TW") if GoogleTranslator else None
CACHE = {}


def clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    text = html_lib.unescape(text)       
    text = text.replace("\u3000", " ") 
    return re.sub(r"\s+", " ", text).strip()


def to_absolute_url(base_url: str, href: str) -> str:
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return base_url.split("/")[0] + "//" + base_url.split("/")[2] + href
    return base_url.rsplit("/", 1)[0] + "/" + href


def translate(text: str) -> str:
    if not text or not TRANSLATOR:
        return text
    if text in CACHE:
        return CACHE[text]
    try:
        out = TRANSLATOR.translate(text)
        CACHE[text] = out
        return out
    except:
        return text


def is_relevant(text: str) -> bool:
    t = text.lower()
    return any(k.lower() in t for k in KEYWORDS)


def priority(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ["sanction", "制裁", "禁令","关税","tariff","關稅"]):
        return "high"
    if any(k in t for k in ["policy", "regulation", "政策"]):
        return "medium"
    return "low"


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def build_item(src, title, summary, link):
    item_id = hashlib.md5((src["id"] + title + link).encode()).hexdigest()[:12]
    return {
        "id": item_id,
        "category": src["category"],
        "priority": priority(title + summary),
        "source": src["name"],
        "title": translate(title),
        "summary": translate(summary)[:220],
        "link": link,
        "time": now(),
        "region": src["region"],
        "icon": src["icon"],
        "srcClass": src["src_class"],
        "catClass": src["cat_class"],
        "tags": ["海关动态"],
    }


def fetch_google_news():
    items = []
    source = {
        "id": "google-news",
        "name": "Google News",
        "category": "global",
        "region": "global",
        "icon": "🌐",
        "src_class": "src-news",
        "cat_class": "cat-news-bg",
    }

    for cfg in GOOGLE_NEWS_QUERIES:
        url = (
            f"https://news.google.com/rss/search?q={quote_plus(cfg['q'])}"
            f"&hl={cfg['hl']}&gl={cfg['gl']}&ceid={cfg['ceid']}"
        )
        feed = feedparser.parse(url)

        for e in feed.entries[:10]:
            title = clean_html(getattr(e, "title", ""))
            summary = clean_html(getattr(e, "summary", ""))

            if title and is_relevant(title + summary):
                items.append(build_item(source, title, summary, e.link))

    return items


def fetch_html(src):
    items = []
    try:
        r = requests.get(
            src["url"], timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        r.encoding = r.apparent_encoding
        matches = re.findall(src["item_pattern"], r.text, re.DOTALL)

        for m in matches[:40]:
            href, title = m[0], clean_html(m[1])
            if not title:
                continue
            link = to_absolute_url(src["url"], href)
            if is_relevant(title):
                items.append(build_item(src, title, title, link))

    except Exception as e:
        print("fetch error:", src["name"], e)

    return items


def main():
    all_items = []

    all_items += fetch_google_news()

    for s in SOURCE_CONFIG:
        all_items += fetch_html(s)

    seen = set()
    uniq = []

    for i in all_items:
        if i["id"] not in seen:
            seen.add(i["id"])
            uniq.append(i)

    uniq.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}[x["priority"]])

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total": len(uniq),
            "sources_count": len(SOURCE_CONFIG) + 1,
        },
        "items": uniq[:80],
    }

    path = Path(__file__).parent.parent / "data" / "news.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
