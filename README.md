# AI Agent Team

فريق وكلاء مجاني عبر GitHub Actions لاكتشاف العملاء المحتملين.

## وكيل أصحاب القرار

افتح **Actions → Clinic Decision Makers → Run workflow**، ثم اكتب أسماء العيادات مفصولة بـ `|`. الناتج CSV ويشمل الاسم المهني، المنصب، البريد المهني، هاتف الشركة، المصدر، الدليل، ودرجة الثقة.

المعلومات مهنية ومنشورة علناً فقط. لا يجمع أرقاماً شخصية، ولا يتجاوز تسجيل الدخول أو CAPTCHA، ولا يرسل رسائل. كل صف حالته `needs_human_review` ويجب التحقق منه قبل التواصل.

## وكيل اكتشاف العيادات

افتح **Actions → UAE Clinic Prospect Finder → Run workflow**. يستخدم Brave عند إضافة السر `BRAVE_API_KEY`، أو DuckDuckGo كبديل. `not_found_in_search` تعني أن الموقع الرسمي لم يظهر في النتائج، وليست حكماً قطعياً.

## وكيل باحث السوق

افتح **Actions → Market Research Agent → Run workflow**، واكتب عبارات البحث مفصولة بـ `|`.

## محلياً

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
crawl4ai-setup
python decision_maker_agent.py --clinic "Emirates Hospitals Dubai" --output decision-makers.csv
```
