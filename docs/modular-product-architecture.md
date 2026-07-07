# 模块化产品架构

## 核心模块

系统围绕五个产品模块组织：

1. 参考视频学习生成
2. 输入方向自动创作
3. 素材库与数字人
4. 视频库与生成任务
5. 账号绑定与自动发布

模块定义在 `backend/app/services/product_modules.py`，前端通过 `GET /api/product-modules` 渲染模块总览。

## API 模块边界

后端 API 入口已通过 `backend/app/api/router.py` 组合挂载，并由
`backend/app/api/module_registry.py` 统一维护模块归属。现阶段为了保持线上接口稳定，
原有 handler 仍保留在 `backend/app/api/routes.py`，组合 router 会按路径前缀把接口分配到模块：

- `system`：认证、微信登录、系统设置、模型配置、总览和集成状态。
- `reference_learning`：素材、参考链接、转写和视频拆解。
- `script_creation`：主题、脚本生成和脚本更新。
- `digital_humans`：数字人资产和真人认证。
- `video_library`：视频任务、分段、成片输出和审核。
- `trending`：主题采集和爆款参考。
- `publishing`：平台账号和发布记录。

新增 API 时必须先在 `module_registry.py` 明确归属，再实现 endpoint。后续迁移时按这些模块拆出实体 router 文件，保持 URL 不变。

## 新功能接入规则

- 新功能必须归属到一个明确模块，不能只在页面上新增孤立按钮。
- 新 API 必须归属到 `module_registry.py` 中的一个 API 模块。
- 后端优先新增 service 层能力，再由 API routes 暴露，避免把业务逻辑堆在路由里。
- 前端入口从模块定义或现有页面状态派生，避免重复硬编码多套入口。
- 视频生成相关规则应优先接入 `video_skills.py`，再进入脚本、拆解、素材匹配或任务执行。
- 新增数据字段必须考虑账号隔离、审计备注和发布/视频库闭环。

## 类型约束

- 新增 Python 代码不要随意使用 `Any`。
- 面对外部平台返回的不稳定 JSON，可以先使用 `object` 或专门的 dataclass/TypedDict 边界处理。
- 模块定义使用 dataclass，字段固定，便于前端和后续测试依赖。
- 对 AI 生成结果要做 normalize/clean，不信任模型直接输出。

## 当前入口映射

- `analysis`：参考视频学习生成
- `creation`：输入方向自动创作
- `humans`：素材库与数字人
- `tasks`：视频库与生成任务
- `publish`：账号绑定与自动发布
