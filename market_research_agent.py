#!/usr/bin/env python3
"""باحث سوق أخلاقي: يجلب صفحات عامة ويستخرج بيانات تواصل منشورة.
لا يرسل رسائل ولا يتجاوز تسجيل الدخول أو CAPTCHA.

مثال:
  python3 market_research_agent.py \
    --query "وكالة تسويق دبي" \
    --query "شركة عقارات دبي" \
    --output leads.csv --max-results 10
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import re
from dataclasses import dataclass, asdict
from typing import Iterable
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().\-]{7,}\d)(?!\d)")
SKIP_HOSTS = {
    "duckduckgo.com", "www.duckduckgo.com", "google.com", "www.google.com",
    "bing.com", "www.bing.com", "facebook.com", "www.facebook.com",
    "instagram.com", "www.instagram.com", "linkedin.com", "www.linkedin.com",
}


@dataclass
class Lead:
    query: str
    name: str
    url: str
    domain: str
    emails: str
    phones: str
    title: str
    summary: str
    source: str = "public_web"


def clean(value: str, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


def unwrap_ddg_url(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target) if target else href
    return href


def result_links(html: str, base_url: str) -> list[str]:
    # DuckDuckGo HTML result links are ordinary anchors; keep only external HTTP(S).
    links = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)
    found: list[str] = []
    for raw in links:
        url = unwrap_ddg_url(urljoin(base_url, raw))
        p = urlparse(url)
        host = p.netloc.lower().split(":")[0]
        if p.scheme in {"http", "https"} and host not in SKIP_HOSTS and "." in host:
            if url not in found:
                found.append(url)
    return found


def unique(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        value = clean(value, 120)
        if value and value not in out:
            out.append(value)
    return out


async def search(crawler: AsyncWebCrawler, query: str, limit: int) -> list[str]:
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    cfg = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=30_000, only_text=False)
    result = await crawler.arun(url, config=cfg)
    if not result.success:
        print(f"[warn] search failed: {query}: {result.error_message}")
        return []
    return result_links(result.html or "", url)[:limit]


async def inspect_page(crawler: AsyncWebCrawler, query: str, url: str) -> Lead | None:
    cfg = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        page_timeout=30_000,
        only_text=True,
        word_count_threshold=20,
        check_robots_txt=True,
    )
    try:
        result = await crawler.arun(url, config=cfg)
    except Exception as exc:
        print(f"[warn] {url}: {exc}")
        return None
    if not result.success:
        print(f"[warn] page failed: {url}: {result.error_message}")
        return None

    text = clean(result.markdown or result.cleaned_html or "", 5000)
    if len(text) < 80:
        return None
    emails = unique(EMAIL_RE.findall(text))
    phones = unique(PHONE_RE.findall(text))
    parsed = urlparse(url)
    title = clean(getattr(result, "title", "") or "", 180)
    name = title or parsed.netloc
    return Lead(
        query=query,
        name=name,
        url=url,
        domain=parsed.netloc,
        emails="; ".join(emails[:5]),
        phones="; ".join(phones[:5]),
        title=title,
        summary=clean(text, 400),
    )


async def run(queries: list[str], max_results: int, output: str, delay: float) -> None:
    browser = BrowserConfig(headless=True, verbose=False)
    async with AsyncWebCrawler(config=browser) as crawler:
        leads: list[Lead] = []
        seen_domains: set[str] = set()
        for query in queries:
            urls = await search(crawler, query, max_results)
            for url in urls:
                domain = urlparse(url).netloc.lower()
                if domain in seen_domains:
                    continue
                seen_domains.add(domain)
                lead = await inspect_page(crawler, query, url)
                if lead:
                    leads.append(lead)
                await asyncio.sleep(delay)

    with open(output, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(asdict(leads[0]).keys()) if leads else list(Lead.__annotations__.keys()))
        writer.writeheader()
        writer.writerows(asdict(lead) for lead in leads)
    print(f"تم حفظ {len(leads)} عميلاً محتملاً في {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl4AI market research lead finder")
    parser.add_argument("--query", action="append", required=True, help="عبارة بحث؛ يمكن تكرارها")
    parser.add_argument("--output", default="leads.csv")
    parser.add_argument("--max-results", type=int, default=5)
    parser.add_argument("--delay", type=float, default=2.0, help="فاصل بين الصفحات بالثواني")
    args = parser.parse_args()
    asyncio.run(run(args.query, max(1, args.max_results), args.output, max(0.5, args.delay)))


if __name__ == "__main__":
    main()
