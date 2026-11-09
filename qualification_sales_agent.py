#!/usr/bin/env python3
"""يؤهل العملاء ويكتب مسودات تواصل عربية؛ لا يرسل رسائل تلقائياً."""
from __future__ import annotations
import argparse, csv, re
from pathlib import Path


def norm(v: str) -> str:
    return re.sub(r"\s+", " ", v or "").strip()


def read_csv(path: str) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def key(row: dict[str, str]) -> str:
    return norm(row.get("clinic_name") or row.get("clinic_query") or "").lower()


def qualify(prospect: dict[str, str], decision: dict[str, str] | None) -> dict[str, str]:
    score = 0
    reasons: list[str] = []
    status = norm(prospect.get("website_status", ""))
    if status == "not_found_in_search":
        score += 45; reasons.append("لا يظهر موقع رسمي")
    elif status == "needs_website_review":
        score += 20; reasons.append("يحتاج مراجعة الموقع")
    opportunity = int(float(prospect.get("opportunity_score") or 0))
    score += min(25, opportunity // 4)
    if norm(prospect.get("business_phone")):
        score += 10; reasons.append("هاتف تجاري منشور")
    if decision and norm(decision.get("company_phone")):
        score += 10; reasons.append("رقم مهني لصاحب قرار")
    if decision and norm(decision.get("professional_email")):
        score += 10; reasons.append("بريد مهني منشور")
    score = min(score, 100)
    tier = "A" if score >= 70 else "B" if score >= 45 else "C"
    name = norm((decision or {}).get("candidate_name")) or "مسؤول العيادة"
    clinic = norm(prospect.get("clinic_name"))
    city = norm(prospect.get("city"))
    draft = (f"السلام عليكم {name}، لاحظت أن {clinic} في {city} قد تستفيد من صفحة موقع سريعة "
             "مع حجز ومتابعة تلقائية للاستفسارات. أعددت نموذجاً تجريبياً قصيراً للعيادات، "
             "هل يناسبكم أن أرسله للاطلاع؟")
    return {
        "clinic_name": clinic, "city": city, "decision_maker": name,
        "professional_phone": norm((decision or {}).get("company_phone")),
        "professional_email": norm((decision or {}).get("professional_email")),
        "priority": tier, "score": str(score), "reasons": "؛ ".join(reasons),
        "draft_message": draft, "send_status": "draft_only_manual_approval_required",
        "source": norm((decision or {}).get("source_url") or prospect.get("source_url")),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--prospects", required=True)
    p.add_argument("--decision-makers", required=True)
    p.add_argument("--output", default="qualified-leads.csv")
    args = p.parse_args()
    prospects = read_csv(args.prospects)
    decisions = read_csv(args.decision_makers)
    by_clinic: dict[str, dict[str, str]] = {}
    for row in decisions:
        k = key(row)
        if k and (norm(row.get("company_phone")) or norm(row.get("professional_email"))):
            by_clinic.setdefault(k, row)
    rows = [qualify(item, by_clinic.get(key(item))) for item in prospects]
    rows.sort(key=lambda r: (-int(r["score"]), r["clinic_name"]))
    fields = list(rows[0]) if rows else ["clinic_name", "priority", "score"]
    with open(args.output, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    print(f"تم تأهيل {len(rows)} عميلاً. الإرسال متوقف: موافقة يدوية مطلوبة.")

if __name__ == "__main__":
    main()
