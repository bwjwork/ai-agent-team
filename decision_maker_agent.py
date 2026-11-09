#!/usr/bin/env python3
"""يبحث عن أصحاب القرار المهنيين المعلنين علناً لدى عيادات محددة.

لا يجمع أرقاماً شخصية ولا يتجاوز تسجيل الدخول أو CAPTCHA، ولا يرسل رسائل.
النتيجة تحتاج مراجعة بشرية قبل أي تواصل.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import html
import os
import re
from dataclasses import asdict, dataclass
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import httpx
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?<!\d)(?:(?:\+|00)971|0)[\s().\-]*\d(?:[\d\s().\-]{6,12})\d(?!\d)")
EN_NAME_RE = re.compile(r"\b(?:Dr\.?|Doctor)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})")
AR_NAME_RE = re.compile(r"\b(?:د(?:كتور|كتورة)?\.?|الطبيب|الطبيبة)\s+([\u0600-\u06ff]{2,}(?:\s+[\u0600-\u06ff]{2,}){1,3})")
ROLE_PATTERNS = [
    ("Founder / Owner", re.compile(r"\b(founder|co-founder|owner|proprietor)\b|المؤسس|المالك", re.I)),
    ("CEO / Managing Director", re.compile(r"\b(CEO|chief executive|managing director|general manager)\b|الرئيس التنفيذي|المدير العام", re.I)),
    ("Medical Director", re.compile(r"\b(medical director|clinical director|director of dentistry)\b|المدير الطبي|المدير السريري", re.I)),
    ("Lead Dentist", re.compile(r"\b(principal dentist|lead dentist|head dentist|specialist)\b|طبيب الأسنان الرئيسي|أخصائي", re.I)),
]
SKIP_HOSTS = {"linkedin.com", "facebook.com", "instagram.com", "tiktok.com", "google.com", "bing.com", "duckduckgo.com"}

@dataclass
class DecisionMaker:
    clinic_query: str
    candidate_name: str
    role: str
    professional_email: str
    company_phone: str
    source_url: str
    source_title: str
    evidence: str
    confidence: float
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


def parse_ddg(html_text: str, base: str) -> list[dict[str, str]]:
    pattern = re.compile(r'<a[^>]+class=["\'][^"\']*result__a[^"\']*["\'][^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
    results: list[dict[str, str]] = []
    for href, title in pattern.findall(html_text):
        url = unwrap_ddg(urljoin(base, href))
        if urlparse(url).scheme in {"http", "https"} and host_of(url) not in {"duckduckgo.com"}:
            results.append({"url": url, "title": clean(re.sub(r"<[^>]+>", "", title), 180)})
    return results


async def search(crawler: AsyncWebCrawler, query: str, count: int) -> list[dict[str, str]]:
    key = os.getenv("BRAVE_API_KEY", "").strip()
    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
        if key:
            response = await client.get("https://api.search.brave.com/res/v1/web/search", headers={"Accept": "application/json", "X-Subscription-Token": key}, params={"q": query, "country": "ae", "search_lang": "en", "count": min(count, 20), "safesearch": "moderate"})
            response.raise_for_status()
            return [{"url": x.get("url", ""), "title": clean(x.get("title", ""), 180)} for x in response.json().get("web", {}).get("results", [])]
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        result = await crawler.arun(url, config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=30_000, only_text=False))
        if not result.success:
            raise RuntimeError(f"فشل البحث: {result.error_message}")
        return parse_ddg(result.html or "", url)[:count]


def first_unique(values: list[str], limit: int = 3) -> list[str]:
    out: list[str] = []
    for value in values:
        value = clean(value, 140)
        if value and value not in out:
            out.append(value)
    return out[:limit]


def extract_names(text: str) -> list[str]:
    names: list[str] = []
    for pattern in (EN_NAME_RE, AR_NAME_RE):
        names.extend(match.group(1) for match in pattern.finditer(text))
    return first_unique(names)


def extract_role(text: str) -> str:
    for role, pattern in ROLE_PATTERNS:
        if pattern.search(text):
            return role
    return "Unconfirmed professional role"


def confidence(name: str, role: str, email: str, source_url: str) -> float:
    value = 0.42
    if name:
        value += 0.24
    if role != "Unconfirmed professional role":
        value += 0.2
    if email:
        value += 0.08
    if any(part in source_url.lower() for part in ("team", "about", "doctor", "leadership", "our-doctors")):
        value += 0.06
    return round(min(value, 0.99), 2)


async def inspect(crawler: AsyncWebCrawler, clinic: str, item: dict[str, str]) -> list[DecisionMaker]:
    url = item["url"]
    if host_of(url) in SKIP_HOSTS:
        return []
    page_text = ""
    try:
        result = await crawler.arun(url, config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=25_000, only_text=True, word_count_threshold=10, check_robots_txt=True))
        if result.success:
            page_text = clean(result.markdown or result.cleaned_html or "", 10000)
    except Exception as exc:
        print(f"[warn] {url}: {exc}")
    text = clean(f"{item['title']} {page_text}", 10000)
    names = extract_names(text)
    emails = first_unique(EMAIL_RE.findall(text))
    phones = first_unique(PHONE_RE.findall(text))
    role = extract_role(text)
    if not names:
        return []
    evidence = clean(next((line for line in text.split(".") if any(name in line for name in names)), text[:300]), 350)
    return [DecisionMaker(clinic, name, role, "; ".join(emails), "; ".join(phones), url, item["title"], evidence, confidence(name, role, "; ".join(emails), url)) for name in names]


async def run(clinics: list[str], max_results: int, output: str, delay: float) -> None:
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        rows: list[DecisionMaker] = []
        seen: set[tuple[str, str, str]] = set()
        for clinic in clinics:
            query = f'{clinic} doctor dermatologist founder owner'
            items = await search(crawler, query, max_results)
            print(f"[info] {clinic}: {len(items)} مصادر")
            for item in items:
                for row in await inspect(crawler, clinic, item):
                    key = (row.clinic_query, row.candidate_name, row.source_url)
                    if key not in seen:
                        seen.add(key)
                        rows.append(row)
                await asyncio.sleep(max(0.5, delay))
    fields = list(DecisionMaker.__annotations__.keys())
    with open(output, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)
    print(f"تم حفظ {len(rows)} مرشحاً في {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Public professional decision-maker finder")
    parser.add_argument("--clinic", action="append", required=True, help="اسم العيادة؛ يمكن تكراره")
    parser.add_argument("--output", default="decision-makers.csv")
    parser.add_argument("--max-results", type=int, default=5)
    parser.add_argument("--delay", type=float, default=1.5)
    args = parser.parse_args()
    asyncio.run(run(args.clinic, max(1, min(args.max_results, 10)), args.output, args.delay))

if __name__ == "__main__":
    main()
