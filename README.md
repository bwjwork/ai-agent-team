# AI Agent Team

فريق وكلاء مجاني عبر GitHub Actions لاكتشاف العملاء المحتملين.

## وكيل اكتشاف العيادات

افتح **Actions → UAE Clinic Prospect Finder → Run workflow**، ثم اختر نوع العيادة والمدن. يستخدم Brave عند إضافة السر `BRAVE_API_KEY` في **Settings → Secrets and variables → Actions**، ويستخدم DuckDuckGo كبديل عند غياب المفتاح. النتيجة ملف CSV داخل Artifacts.

`not_found_in_search` تعني أن موقعاً رسمياً لم يظهر في نتائج البحث، وليست حكماً قطعياً. راجع كل نتيجة يدوياً قبل التواصل. الوكيل يستخدم صفحات عامة فقط، ويحترم robots.txt، ولا يكشط Google Maps مباشرة ولا يتجاوز CAPTCHA أو تسجيل الدخول.

## وكيل باحث السوق

افتح **Actions → Market Research Agent → Run workflow**، واكتب عبارات البحث مفصولة بـ `|`.

## تشغيل محلي

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
crawl4ai-setup
python clinic_prospect_agent.py --city دبي --city أبوظبي --category "عيادة أسنان" --output clinic-prospects.csv
python market_research_agent.py --query "عيادة أسنان دبي" --output leads.csv
```

كل النتائج تجريبية/بحثية وليست بديلاً عن المراجعة البشرية أو الالتزام بسياسات المصادر وقوانين التواصل.
