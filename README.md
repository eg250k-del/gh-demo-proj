# Manhwa Studio: مصنع فيديوهات Motion Comic

سكريبت حلقة (JSON) ← صور مانهوا (SDXL) ← أصوات (Kokoro) ← مونتاج بحركة كاميرا وهزّة وشاشات System وترجمة وموسيقى (FFmpeg) ← **MP4 جاهز لليوتيوب**.

```
episodes/ep01_pilot.json   الحلقة التجريبية (13 مشهد، حوالي 75 ثانية)
pipeline/run_episode.py    المحرك (لو اشتغل تاني بيكمّل من آخر حاجة خلصت)
pipeline/images.py         الصور: Animagine XL، ومعاه وضع سريع SDXL-Lightning
pipeline/tts.py            الأصوات: Kokoro
pipeline/render.py         المونتاج: zoom/pan/shake/flash، لوحة System، ترجمة، موسيقى
pipeline/server.py         صفحة ويب على Salad: تحط السكريبت، وتنزّل الفيديو
salad.py                   تحكم في Salad من جهازك: إنشاء/تشغيل/حالة/إيقاف
```

## التشغيل لأول مرة (حوالي 15 دقيقة، مرة واحدة بس)

### 1) Docker Hub
1. اعمل حساب على hub.docker.com.
2. Account Settings ← Personal access tokens ← اعمل **Token** بصلاحية Read & Write.

### 2) GitHub Secrets، عشان الـ image تتبني لوحدها
في الريبو: Settings ← Secrets and variables ← Actions ← New repository secret:
- `DOCKERHUB_USERNAME`: اسم المستخدم بتاعك على Docker Hub
- `DOCKERHUB_TOKEN`: الـ Token اللي عملته

بعدها: تبويب Actions ← **Build & push image** ← Run workflow. البناء بياخد حوالي 15 دقيقة.

### 3) Salad
في الطريقة الأسهل، من الموقع: portal.salad.com ← Create Container Group:
| الإعداد | القيمة |
|---|---|
| Image | `docker.io/<اسمك>/manhwa-studio:latest` (لو الـ image خاصة (Private)، حط بيانات Docker Hub في Registry auth) |
| GPU | RTX 3090 أو 4090 (أقل حاجة 12GB VRAM) |
| vCPU / RAM | 8 / 30 GB |
| Storage | 50 GB |
| Replicas | 1 |
| Container Gateway | مفعّل، Port **8000** |
| Environment | `APP_TOKEN` = أي كلمة سر تختارها |

أو من جهازك:
```
set SALAD_API_KEY=...        (Windows)
set APP_TOKEN=كلمة-سر
python salad.py create اسم-الـorg اسم-الـproject اسمك-على-dockerhub "RTX 3090"
python salad.py start  org project
python salad.py status org project      ← بيطلّعلك اللينك
```

### 4) الإنتاج
1. افتح اللينك في المتصفح، مع `?token=كلمة-السر` في آخره.
2. استنى لحد ما **Models** تبقى `ready`. أول تشغيل بيحمّل الموديلات، حوالي 7GB.
3. السكريبت التجريبي موجود في الصفحة ← **Render episode** ← حمّل الـ MP4.
4. **⚠️ اقفل السيرفر أول ما تخلص**: `python salad.py stop org project`. الفلوس بتتحسب طول ما هو شغال.

## إعدادات
- `FAST_MODE=1`: صور أسرع حوالي 4 مرات (Lightning)، والجودة أقل شوية.
- `assets/music.mp3`: موسيقاك الخاصة بدل الموسيقى اللي بتتولد.
- أصوات Kokoro: `am_michael`, `am_fenrir`, `am_adam`, `af_heart`, `af_nicole`, `bm_george`, `bm_lewis` …

## تجربة من غير GPU
```
python pipeline/run_episode.py episodes/ep01_pilot.json out/test --cpu-test
```
بيطلع فيديو بصور مؤقتة وصوت صامت، عشان تختبر المونتاج بس.
