# API Smoke Test

After starting the backend, run these requests from the project root.

```bash
curl http://localhost:8000/api/health
```

```bash
curl http://localhost:8000/api/dashboard
```

```bash
curl -X POST http://localhost:8000/api/topics \
  -H "Content-Type: application/json" \
  -d '{"title":"企业短视频数字人获客","industry":"B2B服务","audience":"中小企业老板"}'
```

```bash
curl -X POST http://localhost:8000/api/scripts/generate \
  -H "Content-Type: application/json" \
  -d '{"topic_id":1,"topic":"企业短视频数字人获客","duration_seconds":30,"target_platform":"douyin"}'
```

```bash
curl -X POST http://localhost:8000/api/digital-humans \
  -H "Content-Type: application/json" \
  -d '{"name":"公司讲解员A","role":"品牌顾问","style":"business"}'
```

```bash
curl -X POST http://localhost:8000/api/video-tasks \
  -H "Content-Type: application/json" \
  -d '{"script_id":1,"digital_human_id":1}'
```

```bash
curl -X POST http://localhost:8000/api/video-tasks/1/run
```

Expected result: the task status becomes `needs_review`, with a mock final video URL.
