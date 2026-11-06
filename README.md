# FileSplitter-API

یک پروژه تقسیم فایل مبتنی بر GitHub Actions؛ بدون وب‌سرور دائمی، سایت، ربات، دیتابیس یا سرویس ذخیره‌سازی خارجی.

> **حریم خصوصی:** اگر مخزن عمومی باشد، Release خروجی و تمام لینک‌های قطعات برای عموم قابل دانلود هستند تا زمان حذف. برای فایل‌های خصوصی از مخزن Private استفاده کنید؛ در این حالت دریافت‌کننده لینک‌ها نیز باید مجوز GitHub داشته باشد یا فایل‌ها را از backend ربات با توکن مجاز دریافت کند.

## رفتار پروژه

- ورودی: لینک مستقیم HTTP/HTTPS یا فایل آپلودشده به GitHub.
- پردازش: دانلود فایل، قرار دادن آن در یک ZIP و تقسیم باینری ZIP به قطعات ۱۹ MiB.
- خروجی: هر قطعه به‌صورت یک GitHub Release Asset مستقل منتشر می‌شود.
- پاسخ: فایل `response.json` داخل Release که فقط آرایه لینک‌های قطعات را دارد.
- انقضا: Release خروجی در اولین اجرای موفق پاک‌سازی پس از پنج ساعت از زمان انتشار حذف می‌شود. پاک‌سازی هر پنج دقیقه برنامه‌ریزی شده است؛ زمان‌بندی Cron گیت‌هاب ممکن است با تأخیر اجرا شود.

## راه‌اندازی

1. این مخزن را در حساب یا سازمان خود Fork کنید.
2. مطمئن شوید GitHub Actions برای مخزن فعال است.
3. مطمئن شوید فایل‌های `.github/workflows/process.yml` و `.github/workflows/cleanup.yml` روی شاخه پیش‌فرض مخزن قرار دارند.
4. اگر لازم است سقف ورودی را تغییر دهید، Repository Variable با نام `FILESPLITTER_MAX_INPUT_BYTES` بسازید. مقدار پیش‌فرض `1900000000` بایت است.
5. یک Fine-grained Personal Access Token برای همان مخزن بسازید و مجوزهای `Actions: write` و `Contents: write` را بدهید. این توکن را فقط در backend ربات/برنامه مصرف‌کننده نگه دارید؛ آن را در Workflow input، پیام کاربر یا کد عمومی قرار ندهید.
6. از API گیت‌هاب برای فعال‌سازی Workflow استفاده کنید. مستندات کامل و نمونه‌ها در [`api/README.md`](api/README.md) هستند.

## نمونه سریع با Python

```bash
python -m pip install -r requirements.txt
export GITHUB_TOKEN="github_pat_..."
python api/client.py --repo OWNER/REPO --ref main submit-url "https://example.com/file.iso" --filename file.iso
```

آپلود مستقیم فایل:

```bash
python api/client.py --repo OWNER/REPO --ref main submit-file ./file.iso
```

شناسه اجرای Workflow در پاسخ چاپ می‌شود. برای بررسی وضعیت:

```bash
python api/client.py --repo OWNER/REPO status RUN_ID
```

پس از موفقیت:

```bash
python api/client.py --repo OWNER/REPO result JOB_ID
```

## محدودیت‌های مهم

- این پروژه API server مستقل با endpoint شخصی مثل `/upload` ندارد. قرارداد API بر پایه GitHub REST API است.
- ورودی آپلودشده موقتاً در یک Draft Release قرار می‌گیرد؛ پس از دریافت فایل توسط Runner، Release ورودی حذف می‌شود. اگر Workflow شروع نشود، پاک‌سازی Draftهای رهاشده را پس از ۲۴ ساعت حذف می‌کند.
- حداکثر ورودی پیش‌فرض `1,900,000,000` بایت است. فایل‌های بزرگ‌تر از این مقدار رد می‌شوند.
- خروجی قطعات در یک Release قرار می‌گیرد؛ حداکثر ۹۹۹ قطعه به‌علاوه `response.json` پشتیبانی می‌شود.
- هر قطعه به‌جز قطعه آخر دقیقاً ۱۹ MiB است. قطعات، بخش‌های باینری یک ZIP واحد هستند و به‌تنهایی ZIP قابل استخراج نیستند؛ برای بازیابی باید بایت‌های قطعات به ترتیب به هم متصل و سپس ZIP استخراج شود.
- لینک‌های دانلود مخزن عمومی بدون احراز هویت قابل استفاده‌اند. در مخزن خصوصی، مصرف‌کننده برای دانلود به دسترسی معتبر GitHub نیاز دارد.
- پاک‌سازی پنج‌ساعته با Cron هر پنج دقیقه انجام می‌شود؛ حذف ممکن است چند دقیقه بعد از موعد انجام شود، چون زمان شروع Cron در GitHub تضمین ثانیه‌ای ندارد.

## آزمون محلی

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

برای قرارداد کامل ورودی، وضعیت، خروجی، مجوزها، مثال‌های cURL و نحوه دریافت JSON به [`api/README.md`](api/README.md) مراجعه کنید.
