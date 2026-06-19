# API Smoke Test

After starting the backend, run these requests from the project root.

```bash
curl http://localhost:8000/api/health
```

```bash
curl http://localhost:8000/api/dashboard
```

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123456"}' | python -c "import sys,json; print(json.load(sys.stdin)['token'])")
```

```bash
curl -X POST http://localhost:8000/api/settings/models \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name":"Script model","provider":"openai-compatible","purpose":"script","api_base":"https://api.example.com/v1","api_key":"test","model_name":"demo","is_active":true}'
```

```bash
curl -X POST http://localhost:8000/api/trending/searches \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"platform":"douyin","keyword":"数字人获客","category":"企业服务"}'
```

```bash
curl -X POST http://localhost:8000/api/transcriptions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"material_id":1,"language":"zh-CN"}'
```

```bash
curl -X POST http://localhost:8000/api/transcriptions/1/create-topic \
  -H "Authorization: Bearer $TOKEN"
curl -X POST http://localhost:8000/api/transcriptions/1/generate-script \
  -H "Authorization: Bearer $TOKEN"
```

```bash
curl -X POST http://localhost:8000/api/scripts/1/video-task \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"digital_human_id":null}'
```

```bash
curl -X POST http://localhost:8000/api/video-tasks/1/run
curl -X POST http://localhost:8000/api/video-tasks/1/approve
curl -X POST http://localhost:8000/api/video-tasks/1/publish-record \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"platform":"douyin","account_name":"公司官方号"}'
```

```bash
curl -X POST http://localhost:8000/api/platform-accounts \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"platform":"douyin","account_name":"公司官方号","owner":"运营","is_default":true}'
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/platform-accounts
```

```bash
curl -X PATCH http://localhost:8000/api/publish-records/1 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"title":"发布工作台测试标题","hashtags":"#数字人 #企业获客","caption":"这是一条发布前可编辑文案。","scheduled_at":"2026-06-20T10:00:00"}'
curl -X POST http://localhost:8000/api/publish-records/1/mark-published \
  -H "Authorization: Bearer $TOKEN"
```

```bash
printf "demo" > /tmp/demo-portrait.txt
curl -X POST http://localhost:8000/api/materials/upload \
  -F "file=@/tmp/demo-portrait.txt" \
  -F "name=Demo portrait" \
  -F "kind=portrait"
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
