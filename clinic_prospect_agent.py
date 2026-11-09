#!/usr/bin/env python3
"""يكتشف عيادات إماراتية لا يظهر لها موقع رسمي في نتائج البحث.

يستخدم Brave عند وجود BRAVE_API_KEY، وإلا يستخدم DuckDuckGo HTML كبديل.
الفحص احتمالي: النتيجة "غير ظاهر" تحتاج مراجعة بشرية، وليست حكماً قطعياً.
لا يكشط Google Maps مباشرة ولا يتجاوز CAPTCHA أو تسجيل الدخول.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import html
import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import httpx
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().\-]{7,}\d)(?!\d)")
EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
CITY_NAMES = "دبي أبوظبي الشارقة عجمان رأس الخيمة الفجيرة أم القيوين العين الإمارات"
DIRECTORY_HOSTS = {"yello.ae", "uae.arablocal.com", "connect.ae", "yellowpages.ae", "2gis.ae", "maps.google.com"}
SOCIAL_HOSTS = {"facebook.com", "instagram.com", "linkedin.com", "tiktok.com"}
SEARCH_SKIP = DIRECTORY_HOSTS | SOCIAL_HOSTS | {"google.com", "bing.com", "duckduckgo.com"}

@dataclass
class Prospect:
    clinic_name: str
    city: str
    category: str
    business_phone: str
    public_email: str
    source_url: str
    source_title: str
    website_status: str
    website_evidence: str
    opportunity_score: int
    review_status: str = "needs_human_review"


def clean(value: str, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()[:limit]


def host_of(url: str) -> str:
    return urlparse(url).netloc.lower().split(":")[0].removeprefix("www.")


def unwrap_ddg(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target) if target else href
    return href


def unique(items: list[str], limit: int = 3) -> list[str]:
    out: list[str] = []
    for item in items:
        item = clean(item, 120)
        if item and item not in out:
            out.append(item)
    return out[:limit]


def extract_ddg(html_text: str, base: str) -> list[dict[str, str]]:
    pattern = re.compile(r'<a[^>]+class=["\'][^"\']*result__a[^"\']*["\'][^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
    results: list[dict[str, str]] = []
    for href, title in pattern.findall(html_text):
        url = unwrap_ddg(urljoin(base, href))
        if urlparse(url).scheme in {"http", "https"} and host_of(url) not in {"duckduckgo.com"}:
            results.append({"url": url, "title": clean(re.sub(r"<[^>]+>", "", title), 180), "description": ""})
    return results


async def search(crawler: AsyncWebCrawler, query: str, count: int) -> tuple[list[dict[str, str]], str]:
    api_key = os.getenv("BRAVE_API_KEY", "").strip()
    headers = {"Accept": "application/json", "X-Subscription-Token": api_key}
    async with httpx.AsyncClient(timeout=25, follow_redirects=True, headers=headers) as client:
        if api_key:
            response = await client.get("https://api.search.brave.com/res/v1/web/search", params={"q": query, "country": "ae", "search_lang": "ar", "count": min(count, 20), "safesearch": "moderate"})
            response.raise_for_status()
            payload = response.json()
            items = payload.get("web", {}).get("results", [])
            return [{"url": x.get("url", ""), "title": clean(x.get("title", ""), 180), "description": clean(x.get("description", ""), 500)} for x in items], "brave"
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        cfg = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=30_000, only_text=False)
        result = await crawler.arun(url, config=cfg)
        if not result.success:
            raise RuntimeError(f"البحث الاحتياطي فشل: {result.error_message}")
        return extract_ddg(result.html or "", url)[:count], "duckduckgo_fallback"


def likely_clinic(text: str) -> bool:
    words = ("عيادة", "أسنان", "طبية", "جلدية", "dental", "clinic", "medical", "derma")
    low = text.lower()
    return any(word in low for word in words)


def city_from(text: str) -> str:
    for city in ["دبي", "أبوظبي", "الشارقة", "عجمان", "العين", "رأس الخيمة", "الفجيرة", "أم القيوين"]:
        if city in text:
            return city
    return "الإمارات"


def score(website_status: str, has_phone: bool, is_directory: bool) -> int:
    value = 100 if website_status == "not_found_in_search" else 70
    if not has_phone:
        value -= 10
    if is_directory:
        value += 5
    return max(0, min(100, value))


async def inspect_listing(crawler: AsyncWebCrawler, item: dict[str, str], query: str, source: str) -> Prospect | None:
    url = item["url"]
    host = host_of(url)
    text = f"{item['title']} {item['description']}"
    phones = unique(PHONE_RE.findall(text))
    emails = unique(EMAIL_RE.findall(text))
    if host not in SEARCH_SKIP:
        cfg = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=20_000, only_text=True, word_count_threshold=10, check_robots_txt=True)
        try:
            result = await crawler.arun(url, config=cfg)
            page_text = clean(result.markdown or result.cleaned_html or "", 6000) if result.success else ""
            text = f"{text} {page_text}"
            phones = unique(phones + PHONE_RE.findall(page_text))
            emails = unique(emails + EMAIL_RE.findall(page_text))
        except Exception as exc:
            print(f"[warn] {url}: {exc}")
    if not likely_clinic(text):
        return None
    name = clean(item["title"].split(" - ")[0].split(" | ")[0], 160) or host
    status = "not_found_in_search" if host in SEARCH_SKIP else "needs_website_review"
    evidence = "لم يظهر نطاق رسمي في نتيجة البحث؛ راجع صفحة العيادة قبل التواصل" if status == "not_found_in_search" else "ظهرت صفحة خارجية؛ تحقق من وجود موقع رسمي"
    return Prospect(name, city_from(f"{query} {text}"), query, "; ".join(phones), "; ".join(emails), url, clean(item["title"], 180), status, evidence, score(status, bool(phones), host in DIRECTORY_HOSTS))


async def run(queries: list[str], max_results: int, output: str, delay: float, total_limit: int | None = None) -> None:
    browser = BrowserConfig(headless=True, verbose=False)
    async with AsyncWebCrawler(config=browser) as crawler:
        prospects: list[Prospect] = []
        seen: set[tuple[str, str]] = set()
        for query in queries:
            items, source = await search(crawler, query, max_results)
            print(f"[info] {source}: {query} -> {len(items)} نتائج")
            for item in items:
                key = (clean(item["title"], 100).lower(), host_of(item["url"]))
                if key in seen:
                    continue
                seen.add(key)
                prospect = await inspect_listing(crawler, item, query, source)
                if prospect:
                    prospects.append(prospect)
                await asyncio.sleep(max(0.5, delay))
    if total_limit is not None:
        prospects = prospects[:max(1, total_limit)]
    fields = list(Prospect.__annotations__.keys())
    with open(output, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(asdict(item) for item in prospects)
    print(json.dumps({"count": len(prospects), "output": output, "status": "ok"}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="UAE clinic prospect discovery")
    parser.add_argument("--query", action="append", help="عبارة بحث؛ يمكن تكرارها")
    parser.add_argument("--city", action="append", help="مدينة إماراتية")
    parser.add_argument("--category", default="عيادة أسنان", help="نوع العيادة")
    parser.add_argument("--output", default="clinic-prospects.csv")
    parser.add_argument("--max-results", type=int, default=8)
    parser.add_argument("--total-limit", type=int, default=None)
    parser.add_argument("--delay", type=float, default=1.5)
    args = parser.parse_args()
    queries = args.query or [f"{args.category} {city}" for city in (args.city or ["دبي", "أبوظبي", "الشارقة"])]
    asyncio.run(run(queries, max(1, min(args.max_results, 20)), args.output, args.delay, args.total_limit))

if __name__ == "__main__":
    main()
