# 发布验收清单

## 必过项

- 每次修改功能、接口、模型配置、部署方式、关键数据同步方式后，必须更新 `docs/system-status-handoff.md`。
- 每次新增或调整模型/API 适配方式后，必须同步更新 `docs/integrations.md`。
- 所有 `/api/*` 业务接口必须登录后才能访问；公开接口仅限 `/api/health`、`/api/auth/login`、微信扫码登录入口/回调配置，以及第三方回调入口。
- 管理员初始密码必须在生产环境替换，`AUTH_SESSION_TTL_HOURS` 应保持为有限时长。
- 视频任务点击生成后进入后台队列，页面不等待长时间生成请求。
- 只有已审核通过、有真实成片文件、且不是 `mock://` 占位结果的视频才能进入发布准备。
- 数字人头像和口播源视频不能是 `reference_only` 或 `blocked` 授权状态。
- 发布标题不能为空，停用的平台账号不能用于发布。
- 脚本合规备注中出现不可发布、侵权、未授权等风险标记时，发布必须被拦截。

## 发布前命令

```bash
cd backend
../.venv/bin/python -m compileall app
../.venv/bin/python tests/wechat_login_smoke.py
../.venv/bin/python tests/release_smoke.py
```

前端静态脚本检查：

```bash
/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check backend/app/static/app.js
```

## 发布后检查

- 打开后台首页，确认登录状态正常。
- 生成一条脚本并创建视频任务，确认任务先显示为排队/生成中，再进入待审核。
- 审核通过后创建发布记录，确认发布中心能展示记录。
- 尝试对占位成片创建发布记录，应看到发布前校验失败。
