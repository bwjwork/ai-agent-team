# AI Agent Team

فريق وكلاء مجاني عبر GitHub Actions.

## التشغيل

1. افتح تبويب **Actions**.
2. اختر **Market Research Agent**.
3. اضغط **Run workflow**.
4. اكتب عبارات البحث مفصولة بـ `|`.
5. حمّل ملف `leads.csv` من Artifacts.

الوكيل يقرأ صفحات عامة ويحترم robots.txt. لا يتجاوز تسجيل الدخول ولا يرسل رسائل تلقائياً.

## محلياً

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
crawl4ai-setup
python market_research_agent.py --query "وكالات تسويق دبي" --output leads.csv
```
