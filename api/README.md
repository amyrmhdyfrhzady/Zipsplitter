# مستندات کامل API — FileSplitter-API

نسخه مستندات: `1.0.0`  
روش اجرا: GitHub REST API + GitHub Actions  
اندازه قطعه: `19,922,944` بایت (۱۹ MiB)

---

## 1. معرفی و مدل استفاده

FileSplitter-API یک API میزبانی‌شده روی GitHub است. این پروژه سرور HTTP دائمی یا URL اختصاصی برای دریافت فایل ندارد. مصرف‌کننده با GitHub REST API کار می‌کند و GitHub Actions پردازش را اجرا می‌کند.

هر درخواست یک `job_id`، یک Workflow Run و یک Release خروجی مستقل دارد. وضعیت اجرای پردازش از GitHub Actions دریافت می‌شود. پس از تکمیل موفق، لینک قطعات در فایل `response.json` قرار می‌گیرد.

**جریان کلی:**

1. ارسال لینک مستقیم یا آپلود یک فایل به Draft Release موقت.
2. اجرای Workflow با `workflow_dispatch`.
3. دریافت شناسه اجرای Workflow (`workflow_run_id`).
4. بررسی وضعیت اجرای Workflow.
5. پس از موفقیت، دریافت Release با Tag مربوط به `job_id`.
6. دانلود Asset با نام `response.json`؛ این JSON فقط لینک مستقیم قطعات را برمی‌گرداند.

## 2. پیش‌نیازها و احراز هویت

### 2.1 تنظیم مخزن

- مخزن باید Fork یا کپی مستقل این پروژه باشد.
- GitHub Actions باید فعال باشد.
- هر دو Workflow باید در شاخه پیش‌فرض مخزن وجود داشته باشند:
  - `.github/workflows/process.yml`
  - `.github/workflows/cleanup.yml`

### 2.2 ساخت Fine-grained Personal Access Token

یک توکن Fine-grained برای همان مخزن بسازید و این مجوزها را فعال کنید:

| Repository permission | سطح | دلیل |
|---|---|---|
| Actions | Read and write | اجرای Workflow و خواندن وضعیت Run |
| Contents | Read and write | ساخت Draft Release ورودی، آپلود فایل، خواندن خروجی و Releaseها |

توکن را در backend ربات یا برنامه مصرف‌کننده نگهداری کنید. توکن نباید به کاربر نهایی برگردانده شود، در Workflow input قرار بگیرد یا در log چاپ شود.

**حریم خصوصی خروجی:** در مخزن Public، Release خروجی و لینک‌های قطعات عمومی‌اند و هر کسی که لینک را داشته باشد می‌تواند فایل را دریافت کند. در مخزن Private، لینک‌های `browser_download_url` برای دریافت ناشناس کار نمی‌کنند؛ برنامه مصرف‌کننده باید دانلود را با توکن معتبر انجام دهد یا فایل را از سمت backend به کاربر تحویل دهد.

### 2.3 مجوز داخل GitHub Actions

Workflowها از `GITHUB_TOKEN` خودکار GitHub استفاده می‌کنند. `process.yml` و `cleanup.yml` فقط `contents: write` درخواست می‌کنند؛ هیچ Secret اضافه‌ای برای اجرای پردازش لازم نیست.

## 3. قرارداد ورودی

### 3.1 شناسه درخواست

هر درخواست باید `job_id` یکتا داشته باشد. قالب پیشنهادی:

```text
job_<uuid-hex>
```

مثال:

```text
job_9f3140e14cc24e70a82ce3b0a6d80d6e
```

`job_id` برای ساخت Tag و Release استفاده می‌شود؛ در ارسال درخواست‌های دستی از شناسه تکراری استفاده نکنید.

### 3.2 حالت ورودی لینک مستقیم

`source_type=url`

فیلدهای لازم:

| نام | نوع | اجباری | توضیح |
|---|---|---|---|
| `job_id` | string | بله | شناسه یکتا |
| `source_type` | string | بله | مقدار `url` |
| `source_url` | string | بله | لینک مستقیم HTTP یا HTTPS فایل |
| `filename` | string | خیر | نام فایل اصلی؛ در صورت حذف از مسیر URL استخراج می‌شود |

لینک باید مستقیماً محتوای فایل را برگرداند؛ لینک صفحه اشتراک‌گذاری یا صفحه HTML دانلود، لزوماً قابل پردازش نیست.

### 3.3 حالت آپلود مستقیم فایل

GitHub `workflow_dispatch` باینری را در فیلدهای JSON دریافت نمی‌کند. بنابراین ابتدا فایل در یک Draft Release موقت آپلود می‌شود و سپس Workflow با شناسه Release و شناسه Asset اجرا می‌شود.

ترتیب عملیات:

1. `POST /repos/{owner}/{repo}/releases` با `draft: true` و Tag برابر `fs-input-{job_id}`.
2. آپلود فایل به URL موجود در `upload_url` همان Draft Release.
3. دریافت `asset.id` از پاسخ آپلود.
4. اجرای Workflow با `source_type=release_asset`، `input_release_id` و `input_asset_id`.
5. Runner فایل را دریافت و Draft Release و Tag ورودی را حذف می‌کند.

اگر Workflow اصلاً شروع نشود، Workflow پاک‌سازی Draftهای ورودی قدیمی‌تر از ۲۴ ساعت را حذف می‌کند.

## 4. API شروع پردازش

### Endpoint رسمی GitHub

```http
POST https://api.github.com/repos/{owner}/{repo}/actions/workflows/process.yml/dispatches
```

Headers:

```http
Accept: application/vnd.github+json
Authorization: Bearer <GITHUB_TOKEN>
X-GitHub-Api-Version: 2026-03-10
Content-Type: application/json
```

### 4.1 نمونه درخواست برای لینک مستقیم

```json
{
  "ref": "main",
  "return_run_details": true,
  "inputs": {
    "job_id": "job_9f3140e14cc24e70a82ce3b0a6d80d6e",
    "source_type": "url",
    "source_url": "https://example.com/files/archive.iso",
    "filename": "archive.iso"
  }
}
```

### 4.2 نمونه درخواست برای فایل آپلودشده

```json
{
  "ref": "main",
  "return_run_details": true,
  "inputs": {
    "job_id": "job_9f3140e14cc24e70a82ce3b0a6d80d6e",
    "source_type": "release_asset",
    "input_release_id": "123456789",
    "input_asset_id": "987654321",
    "filename": "archive.iso"
  }
}
```

### 4.3 پاسخ موفق Dispatch

با `return_run_details: true` پاسخ HTTP `200` شامل شناسه Run و URLهای مربوط است:

```json
{
  "workflow_run_id": 1234567890,
  "run_url": "https://api.github.com/repos/OWNER/REPO/actions/runs/1234567890",
  "html_url": "https://github.com/OWNER/REPO/actions/runs/1234567890"
}
```

`workflow_run_id` را برای پیگیری وضعیت ذخیره کنید. موفقیت Dispatch به معنی پایان پردازش نیست.

## 5. آپلود مستقیم فایل — جزئیات REST API

### 5.1 ایجاد Draft Release ورودی

```http
POST https://api.github.com/repos/{owner}/{repo}/releases
```

Body نمونه:

```json
{
  "tag_name": "fs-input-job_9f3140e14cc24e70a82ce3b0a6d80d6e",
  "name": "FileSplitter input job_9f3140e14cc24e70a82ce3b0a6d80d6e",
  "body": "filesplitter_created_at=1793990000",
  "draft": true,
  "prerelease": false
}
```

پاسخ شامل `id` و `upload_url` است.

### 5.2 آپلود باینری

`{?name,label}` را از انتهای `upload_url` حذف کنید و نام فایل را به‌عنوان query parameter با نام `name` ارسال کنید.

```http
POST https://uploads.github.com/repos/{owner}/{repo}/releases/{release_id}/assets?name=archive.iso
Content-Type: application/octet-stream
Authorization: Bearer <GITHUB_TOKEN>
```

Body باید باینری خام فایل باشد، نه JSON و نه multipart/form-data.

پاسخ شامل شناسه Asset است:

```json
{
  "id": 987654321,
  "name": "archive.iso",
  "size": 12582912,
  "state": "uploaded"
}
```

سپس با `release_id` و `asset_id`، Workflow را با روش بخش ۴ اجرا کنید.

## 6. بررسی وضعیت پردازش

### Endpoint

```http
GET https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}
```

### وضعیت‌های مهم

| فیلد | مقدار | معنی |
|---|---|---|
| `status` | `queued` | در صف اجرا |
| `status` | `in_progress` | در حال پردازش |
| `status` | `completed` | اجرای Workflow تمام شده |
| `conclusion` | `success` | پردازش موفق |
| `conclusion` | `failure` | خطا در پردازش |
| `conclusion` | `cancelled` | اجرا لغو شده |
| `conclusion` | `timed_out` | زمان اجرای Workflow تمام شده |

نمونه پاسخ خلاصه:

```json
{
  "id": 1234567890,
  "status": "completed",
  "conclusion": "success",
  "html_url": "https://github.com/OWNER/REPO/actions/runs/1234567890"
}
```

پیشنهاد: هر ۵ تا ۱۵ ثانیه وضعیت را بررسی کنید و از polling با فاصله بسیار کوتاه خودداری کنید. وقتی `status=completed` شد، فقط در صورت `conclusion=success` سراغ دریافت خروجی بروید.

## 7. دریافت JSON و لینک قطعات

### 7.1 پیدا کردن Release خروجی

Tag خروجی با این الگو ساخته می‌شود:

```text
fs-output-{job_id}
```

درخواست:

```http
GET https://api.github.com/repos/{owner}/{repo}/releases/tags/fs-output-{job_id}
```

در آرایه `assets`، Asset با نام `response.json` را پیدا کنید.

### 7.2 دانلود response.json

شناسه Asset را از پاسخ Release بردارید:

```http
GET https://api.github.com/repos/{owner}/{repo}/releases/assets/{asset_id}
Accept: application/octet-stream
```

برای دریافت JSON در مخزن خصوصی، درخواست باید با توکن مجاز احراز هویت شود. در مخزن عمومی، لینک‌های `browser_download_url` قطعات مستقیماً قابل استفاده‌اند.

### 7.3 شکل دقیق JSON خروجی

JSON خروجی عمداً فقط شامل لینک‌هاست:

```json
{
  "parts": [
    "https://github.com/OWNER/REPO/releases/download/fs-output-job_.../part1.zip",
    "https://github.com/OWNER/REPO/releases/download/fs-output-job_.../part2.zip",
    "https://github.com/OWNER/REPO/releases/download/fs-output-job_.../part3.zip"
  ]
}
```

هیچ نام، حجم، شناسه، هش یا metadata دیگری در `response.json` قرار نمی‌گیرد. لینک‌ها به ترتیب قطعات هستند.

## 8. دریافت فایل اصلی از قطعات

قطعات، تکه‌های باینری پشت‌سرهم از یک ZIP واحد هستند؛ هر قطعه به‌تنهایی ZIP قابل استخراج نیست.

برای بازسازی:

1. `part1.zip`، `part2.zip` و بقیه را به ترتیب دانلود کنید.
2. بایت‌های هر قطعه را بدون فاصله و بدون تغییر به ترتیب به یک فایل واحد اضافه کنید.
3. فایل ترکیب‌شده را با ابزار ZIP استخراج کنید.

نمونه Linux/macOS:

```bash
cat part1.zip part2.zip part3.zip > restored.zip
unzip restored.zip -d restored
```

## 9. انقضا و پاک‌سازی

- Release خروجی پس از Publish شدن، زمان پنج‌ساعته خود را شروع می‌کند.
- `cleanup.yml` هر پنج دقیقه اجرا می‌شود.
- Release خروجی با Tag دارای پیشوند `fs-output-` که حداقل پنج ساعت از `published_at` آن گذشته باشد حذف می‌شود.
- Tag Git مربوط به Release نیز حذف می‌شود.
- Draftهای ورودی `fs-input-` که بیش از ۲۴ ساعت از زمان ثبت‌شده در `body` آن‌ها (یا آخرین آپلود Asset، هرکدام جدیدتر است) گذشته باشد نیز پاک می‌شوند. کلاینت‌های نمونه این زمان را هنگام ساخت Draft ثبت می‌کنند.
- پاک‌سازی ممکن است به‌دلیل زمان‌بندی GitHub چند دقیقه پس از پنج ساعت انجام شود؛ حذف در ثانیه دقیق تضمین‌شده نیست.
- Artifact استفاده نمی‌شود و Releaseها پس از انقضا برای همیشه در دسترس نمی‌مانند.

## 10. محدودیت‌ها

| مورد | مقدار / رفتار |
|---|---|
| اندازه قطعه | ۱۹ MiB = 19,922,944 bytes |
| سقف ورودی پیش‌فرض | 1,900,000,000 bytes |
| تغییر سقف ورودی | Repository Variable با نام `FILESPLITTER_MAX_INPUT_BYTES` |
| مهلت اجرای Workflow | حداکثر ۳۰۰ دقیقه |
| تعداد قطعات | حداکثر ۹۹۹ قطعه + `response.json` در یک Release |
| ورودی URL | فقط HTTP/HTTPS؛ لینک باید مستقیم باشد |
| دسترسی URL | IPهای خصوصی، localhost، link-local و reserved مسدود می‌شوند |
| خروجی خصوصی | دانلود نیازمند مجوز GitHub است |
| خروجی عمومی | لینک مستقیم هر Asset قابل استفاده است |
| زمان حذف | اولین اجرای موفق پاک‌سازی پس از پنج ساعت |

هر Release GitHub تا ۱۰۰۰ Asset می‌تواند داشته باشد و هر Asset باید کمتر از ۲ GiB باشد. این پروژه یک Asset برای `response.json` رزرو می‌کند.

## 11. خطاها و عیب‌یابی

| نشانه | علت محتمل | اقدام |
|---|---|---|
| `401 Bad credentials` | توکن نامعتبر یا منقضی | توکن را بررسی/تعویض کنید |
| `403 Resource not accessible` | مجوز Actions یا Contents ناقص | مجوزهای Fine-grained token را بررسی کنید |
| `404 workflow not found` | Workflow روی شاخه پیش‌فرض نیست یا نام فایل اشتباه است | `process.yml` و شاخه `ref` را بررسی کنید |
| `422 Validation Failed` | ورودی ناقص، `job_id` تکراری یا فرمت ورودی نامعتبر | Body درخواست و Tagهای موجود را بررسی کنید |
| `Input exceeds the configured maximum` | فایل از سقف ورودی بزرگ‌تر است | مقدار Repository Variable را در محدوده منابع Runner تنظیم کنید |
| `URLs resolving to private... are blocked` | URL به IP داخلی/خصوصی Resolve شده است | از لینک عمومی قابل دسترسی استفاده کنید |
| Workflow موفق ولی Release نیست | مشکل در انتشار یا Tag/Release | log اجرای Workflow را بررسی کنید |
| Asset در مخزن خصوصی دانلود نمی‌شود | درخواست دانلود احراز هویت نشده | دانلود را با API و توکن مجاز انجام دهید |

## 12. نمونه‌های آماده

### cURL — ثبت درخواست با لینک

```bash
export GITHUB_TOKEN="github_pat_..."
OWNER="YOUR_OWNER"
REPO="YOUR_REPO"

curl -sS -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "X-GitHub-Api-Version: 2026-03-10" \
  -H "Content-Type: application/json" \
  https://api.github.com/repos/$OWNER/$REPO/actions/workflows/process.yml/dispatches \
  -d '{
    "ref": "main",
    "return_run_details": true,
    "inputs": {
      "job_id": "job_9f3140e14cc24e70a82ce3b0a6d80d6e",
      "source_type": "url",
      "source_url": "https://example.com/archive.iso",
      "filename": "archive.iso"
    }
  }'
```

### cURL — آپلود مستقیم فایل

برای این نمونه به `curl` و Python 3 نیاز دارید. فایل باید از سقف ورودی مخزن کوچک‌تر باشد.

```bash
export GITHUB_TOKEN="github_pat_..."
export OWNER="YOUR_OWNER"
export REPO="YOUR_REPO"
export FILE_PATH="./archive.iso"
export REF="main"
bash api/examples/curl-submit-file.sh
```

این اسکریپت Draft Release ورودی را می‌سازد، فایل را به‌صورت باینری آپلود می‌کند و سپس Workflow را Dispatch می‌کند.

### Python client — هر دو نوع ورودی

```bash
python -m pip install requests
export GITHUB_TOKEN="github_pat_..."

# لینک مستقیم
python api/client.py --repo OWNER/REPO --ref main submit-url \
  "https://example.com/archive.iso" --filename archive.iso

# آپلود مستقیم فایل
python api/client.py --repo OWNER/REPO --ref main submit-file ./archive.iso

# بررسی وضعیت
python api/client.py --repo OWNER/REPO status RUN_ID

# دریافت JSON لینک‌های قطعات پس از موفقیت
python api/client.py --repo OWNER/REPO result JOB_ID
```

### JavaScript / Node.js

نمونه‌های آماده برای backend ربات یا برنامه Node.js در [`examples/javascript.mjs`](examples/javascript.mjs) هستند. این مثال از Node.js 20+ و `fetch` داخلی استفاده می‌کند و توکن را از Environment Variables می‌خواند.

```bash
export GITHUB_OWNER=OWNER
export GITHUB_REPO=REPO
export GITHUB_REF=main
export GITHUB_TOKEN=github_pat_...
node --input-type=module -e 'import("./api/examples/javascript.mjs").then(async m => console.log(await m.submitUrl("https://example.com/archive.iso")))'
```

برای آپلود مستقیم فایل، تابع `submitFile("./archive.iso")` را فراخوانی کنید. توکن فقط باید روی backend باقی بماند.

## 13. مرجع رسمی GitHub

- [Create a workflow dispatch event](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event)
- [Get a workflow run](https://docs.github.com/en/rest/actions/workflow-runs#get-a-workflow-run)
- [Create a release](https://docs.github.com/en/rest/releases/releases#create-a-release)
- [Upload a release asset](https://docs.github.com/en/rest/releases/assets#upload-a-release-asset)
- [Get a release by tag name](https://docs.github.com/en/rest/releases/releases#get-a-release-by-tag-name)
- [Get a release asset](https://docs.github.com/en/rest/releases/assets#get-a-release-asset)
- [Delete a release](https://docs.github.com/en/rest/releases/releases#delete-a-release)
- [About releases and asset limits](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)
