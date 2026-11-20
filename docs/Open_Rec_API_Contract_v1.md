# Open Rec – API Contract v1

## Why This File

الفرونت والـ backend رح يشتغلوا بنفس الوقت. الفرونت بيبني الشاشات على بيانات وهمية، والـ backend بيبني الروابط (P2-3). عشان لما نربطهم يزبطوا من أول مرة، لازم نتفق **من هلأ** على شغلتين:
1. **أسماء الروابط (endpoints):** شو الرابط، وأي method.
2. **شكل الرد:** شو الحقول اللي بترجع، وبأي أسماء.

القاعدة: **أسماء الحقول نفسها اللي بالداتا كونتراكت وبالداتا بيس**، وما في أسماء جديدة.

## How We Use It

- **الفرونت:** البيانات الوهمية بـ `api.ts` لازم تكون بنفس الأشكال هون بالزبط. ولما الـ backend يجهز، بنبدّل الوهمي بالحقيقي بدون ما نغيّر الشاشات.
- **الـ backend (P2-3):** كل رابط هون بيرجّع نفس الشكل المكتوب. والأشكال بتنعمل كـ Pydantic models (response models).
- **أي تغيير:** بيصير بـ PR على هالملف أول، والفريق كله بيوافق، وبعدين الكود.

## General Rules

| الموضوع | القاعدة |
|---|---|
| الصيغة | JSON، والأسماء `snake_case` |
| التواريخ | ISO 8601 بتوقيت UTC، مثل `"2026-11-08T07:00:00Z"` |
| تسجيل الدخول | كل رابط (غير login وregister) بيحتاج الهيدر `Authorization: Bearer <token>` |
| القوائم | `?page=1&page_size=20`، والرد: `{"items": [...], "total": 57, "page": 1, "page_size": 20}` |
| الأخطاء | `{"detail": "رسالة واضحة"}` |
| أكواد الرد | 200 تمام · 201 انعمل · 202 انقبل وشغّال بالخلفية · 401 مش مسجّل دخول · 403 مش مسموحلك (مش admin) · 404 مش موجود · 409 تعارض (مثلاً في تشغيل شغال) · 422 بيانات غلط · 502 الـ AI ما رجّع جواب صالح |
| الأدوار | `reviewer`: مراجعة. `admin`: كمان الإعدادات وتشغيل المسار |

## Auth (P2-7 / P2-8)

| Method | Endpoint | بيبعت | بيرجّع |
|---|---|---|---|
| POST | `/auth/register` | `full_name`، `email`، `password` | المستخدم (بدون كلمة السر) |
| POST | `/auth/login` | `email`، `password` | `{"access_token": "...", "token_type": "bearer"}` |
| GET | `/auth/me` | – | `{"user_id", "full_name", "email", "role"}` |

## Jobs (P2-4)

| Method | Endpoint | شو بيعمل |
|---|---|---|
| GET | `/jobs?status=&q=&page=` | قائمة الوظائف، مع فلترة بالحالة وبحث بالعنوان أو الشركة |
| GET | `/jobs/{job_id}` | تفاصيل وظيفة وحدة |
| PATCH | `/jobs/{job_id}/requirements` | تصحيح المتطلبات يدوياً (FR-12) |

**عنصر بالقائمة:**
```json
{
  "job_id": 12,
  "title": "Senior React Developer",
  "company_name": "Acme Corp",
  "source": "himalayas",
  "posted_at": "2026-11-07T10:00:00Z",
  "status": "scored",
  "fit_score": 92
}
```

**التفاصيل:** نفس الحقول، وزيادة عليها:
```json
{
  "url": "https://himalayas.app/...",
  "description_text": "...",
  "expires_at": null,
  "requirements": {
    "required_skills": ["react", "typescript"],
    "preferred_skills": ["redux"],
    "seniority": "senior",
    "min_years_experience": 5,
    "timezone_offsets": [-5, -4],
    "employment_type": "full_time",
    "remote_policy": "remote",
    "salary_min": null, "salary_max": null,
    "salary_currency": null, "salary_period": null,
    "fit_score": 92,
    "fit_reason": "3 profiles cover react and typescript with 5+ years",
    "flag_reason": null
  }
}
```
`requirements` بيكون `null` إذا الوظيفة لسا `discovered`.

**تصحيح المتطلبات (`PATCH /jobs/{job_id}/requirements`):**
- **بيبعت:** بس الحقول اللي بدّه يغيّرها من حقول `requirements` فوق (غير `fit_score` و`fit_reason` و`flag_reason`). مثال:
  ```json
  { "required_skills": ["react", "typescript"], "min_years_experience": 5 }
  ```
- **الحدود:** نفس حدود فهم الوظيفة. الخبرة من 0 لـ 50، والراتب الأدنى مش أكبر من الأعلى (حتى لو انبعت واحد منهم بس)، والعملة 3 أحرف، وفرق التوقيت من -12 لـ 14. وإذا في قيمة غلط: **422**، وما بيتغير إشي.
- **بعد الحفظ:** الوظيفة بترجع `parsed`، و`fit_score` و`fit_reason` و`flag_reason` بيصيروا `null`، عشان التشغيل الجاي يقيّمها من جديد على القيم المصححة.
- **بيرجّع:** تفاصيل الوظيفة (نفس شكل `GET /jobs/{job_id}`).
- **وظيفة `discovered` (ما إلها متطلبات):** **404** "This job has no extracted requirements yet".

## Leads (P2-5)

| Method | Endpoint | شو بيعمل |
|---|---|---|
| GET | `/leads?status=&page=` | الشركات مرتبة من الأعلى درجة |
| GET | `/leads/{lead_id}` | صفحة مراجعة شركة |
| PATCH | `/leads/{lead_id}/contact` | إضافة جهة اتصال يدوياً: `contact_name`، `contact_title`، `contact_email` |

**عنصر بالقائمة:**
```json
{
  "lead_id": 3,
  "company_name": "Acme Corp",
  "lead_score": 97,
  "best_job_score": 92,
  "qualifying_jobs": 2,
  "status": "qualified",
  "reason": "Acme has two React roles with fit scores 92 and 78."
}
```

**التفاصيل:** نفس الحقول، وزيادة عليها:
```json
{
  "company": { "name": "Acme Corp", "website": null, "location": null,
               "contact_name": null, "contact_title": null, "contact_email": null },
  "jobs": [ { "job_id": 12, "title": "Senior React Developer", "fit_score": 92, "fit_reason": "..." } ],
  "history": [ { "run_id": 7, "lead_score": 97, "status": "qualified",
                 "created_at": "2026-11-08T07:00:00Z" } ],
  "draft": { "draft_id": 5, "subject": "...", "body": "...", "word_count": 150,
             "version": 1, "status": "pending_review",
             "review_comment": null, "reviewed_at": null, "reviewed_by": null }
}
```
- `jobs` = الوظائف اللي دخلت بالحساب (من `evidence`).
- `history`: من الأقدم للأحدث، و`status` هي حالة الشركة بهداك التشغيل.
- `draft` = **أحدث** نسخة، وبيكون `null` إذا لسا ما في مسودة.

## Drafts (P2-1 / P2-2 / P2-5)

| Method | Endpoint | بيبعت | شو بيعمل |
|---|---|---|---|
| POST | `/leads/{lead_id}/draft/regenerate` | – | مسودة جديدة بـ `version` أعلى (P2-2)، والرد **201** |
| PATCH | `/drafts/{draft_id}` | `subject`، `body` | تعديل، والحالة بتصير `edited` |
| POST | `/drafts/{draft_id}/approve` | – | الحالة `approved` |
| POST | `/drafts/{draft_id}/reject` | `review_comment` | الحالة `rejected` |

**شكل المسودة:** كل الروابط فوق بترجّع نفس شكل `draft` اللي بتفاصيل الشركة:
```json
{
  "draft_id": 5, "subject": "...", "body": "...", "word_count": 150,
  "version": 2, "status": "rejected",
  "review_comment": "Too generic",
  "reviewed_at": "2026-11-15T09:30:00Z",
  "reviewed_by": "Lilian Abu Ramadan"
}
```
- `reviewed_by` = **الاسم الكامل** للمراجع، مش رقمه.
- `review_comment` بيكون موجود بس لما المسودة مرفوضة.
- مسودة جديدة (لسا ما انراجعت): الثلاثة `null`.

كل قرار بيسجّل `reviewed_by` (المستخدم الحالي) و`reviewed_at`. **وما في رابط للإرسال.**

**الأخطاء:**
| الرابط | الكود | الرسالة |
|---|---|---|
| regenerate | 404 | "Lead not found" |
| regenerate | 409 | "This draft is already approved" · "This company has no suitable jobs" |
| regenerate | 502 | "Could not write a valid draft. Please try again." (ولا إشي بيتغير) |
| edit / approve / reject | 404 | "Draft not found" |
| edit / approve / reject | 409 | "Only the latest draft version can be reviewed" · "This draft is already decided" |
| approve / reject | 409 | "This company has no suitable jobs" |

## Pipeline (P1-6 / P2-6)

| Method | Endpoint | مين | شو بيعمل |
|---|---|---|---|
| POST | `/pipeline/run` | admin | بيبلّش تشغيل، وبيرد **فوراً** بـ **202** و`{"run_id": 8}`. والتشغيل بيكمّل بالخلفية. وإذا في تشغيل شغال: **409** "A run is already in progress" |
| GET | `/pipeline/runs?limit=10` | أي مستخدم | آخر التشغيلات، الأحدث أول (`limit` من 1 لـ 100) |
| GET | `/pipeline/runs/{run_id}` | أي مستخدم | تشغيل واحد، أو **404** "Run not found". الواجهة بتسأل عليه كل 3 ثواني لحد ما `status` ما يضل `running` |

**تشغيل:**
```json
{
  "run_id": 8, "status": "partial", "trigger_type": "manual",
  "started_by": "Lilian Abu Ramadan",
  "started_at": "2026-11-15T09:00:00Z", "finished_at": "2026-11-15T09:04:10Z",
  "jobs_fetched": 100, "jobs_new": 12, "jobs_updated": 3,
  "errors": {
    "stages": [
      { "stage": "discovery", "result": "100 fetched, 12 new, 3 updated, 85 unchanged, 0 skipped" },
      { "stage": "understanding", "result": "14 parsed, 1 needs review, 0 failed" },
      { "stage": "fit", "result": "14 scored" },
      { "stage": "leads", "result": "3 qualified, 9 not qualified" },
      { "stage": "drafts", "result": "2 created" }
    ],
    "errors": [ { "stage": "drafts", "message": "lead 4 (Acme Corp): no draft: ..." } ]
  }
}
```
- `status`: `running` · `completed` (بدون أخطاء) · `partial` (في أخطاء بس كمّل) · `failed` (وقف).
- `started_by` = **الاسم الكامل** لمين ضغط الزر، و`null` للتشغيل المجدول.
- `finished_at` و`errors` بيكونوا `null` وقت ما التشغيل `running`.
- `errors.stages`: سطر لكل مرحلة. و`errors.errors`: كل خطأ مع المرحلة اللي صار فيها.

## Settings (P2-6) – admin

| Method | Endpoint | شو بيعمل |
|---|---|---|
| GET | `/settings` | الإعدادات الحالية |
| PUT | `/settings` | تعديلها (بس الحقول اللي بتتبعت) |

```json
{ "lead_threshold": 60, "fetch_limit": 100, "himalayas_enabled": true,
  "run_mode": "manual", "max_retries": 3, "run_interval_hours": 32,
  "run_at_hour": null }
```
- `run_interval_hours` (P1-7): من 1 لـ 168. لما `run_mode` يكون `scheduled`، التشغيل المجدول بيبلّش لما يصير عمر آخر تشغيل خلص (يدوي أو مجدول) هالعدد من الساعات. وما بيبلّش إذا في تشغيل شغّال.
- `run_at_hour` (P1-7b): من 0 لـ 23، أو `null` (الافتراضي).
  - **رقم:** التشغيل المجدول بيصير مرة باليوم، بعد هالساعة بتوقيت غزة (`Asia/Gaza`). وأي تشغيل بلّش بعدها بنفس اليوم، يدوي أو مجدول، بيُحسب تشغيل اليوم. وهون `run_interval_hours` بينتجاهل.
  - **`null`:** القاعدة القديمة، "كل `run_interval_hours` ساعة".
  - `PUT /settings` بـ `{"run_at_hour": null}` بيرجّعه لـ `null`.

## Open Points

1. **`source_fields`** (شغل شيماء): بنعرضه بتفاصيل الوظيفة كمعلومات من المصدر، ولا بس بنستخدمه بالـ backend؟
2. **البحث بـ Jobs:** بالعنوان والشركة بس، ولا كمان بالمهارات؟
3. ~~**تحديث صفحة التشغيل**~~ **انحسمت:** الواجهة بتسأل على `GET /pipeline/runs/{run_id}` كل 3 ثواني لحد ما يخلص (polling).
