# 微信扫码登录与用户数据隔离设计

## 背景

当前系统使用账号密码登录，登录成功后后端签发 `AuthSession.token`，前端存入 `localStorage`。系统已有用户角色、用户启停、管理员用户管理，以及基于 `owner_user_id` 的业务数据归属机制。

新需求是：

- 登录页支持微信开放平台网站应用扫码登录。
- 首次扫码登录不能自动进入系统，需要生成申请。
- 管理员在后台看到申请，批准后用户以后可以扫码登录。
- 每个普通用户只能看到自己创建的素材、脚本、视频任务、数字人、发布账号等内容。

## 目标

1. 增加微信开放平台网站应用扫码登录。
2. 增加管理员审批流程，避免陌生微信账号自动进入系统。
3. 支持管理员把微信身份绑定到已有用户，或批准时新建用户。
4. 保持现有账号密码登录可用，微信登录作为并行登录方式。
5. 将“用户只能访问自己创建的数据”作为默认安全规则，覆盖核心业务模块。

## 非目标

- 不接企业微信登录。
- 不接公众号网页授权登录。
- 不允许任意微信扫码后自动注册并进入系统。
- 不在前端保存微信 `access_token`、`refresh_token` 或 `AppSecret`。

## 微信开放平台配置

使用微信开放平台“网站应用”登录能力：

- 应用类型：网站应用。
- 回调域名：`media.tech-ark.com`。
- 登录 scope：`snsapi_login`。
- 后端回调路径：`https://media.tech-ark.com/api/auth/wechat/callback`。

管理员需要在系统后台填写：

- `AppID`
- `AppSecret`
- 是否启用微信登录
- 默认新用户角色，建议默认 `operator`

`AppSecret` 只保存在后端数据库，不返回给前端。

## 数据模型

### WechatLoginConfig

保存微信网站应用配置。首期只需要一条 active 配置。

字段：

- `id`
- `app_id`
- `app_secret`
- `redirect_uri`
- `is_active`
- `default_role`
- `created_at`
- `updated_at`

### WechatIdentity

保存微信身份与系统用户的绑定关系。

字段：

- `id`
- `user_id`
- `openid`
- `unionid`
- `nickname`
- `avatar_url`
- `is_active`
- `bound_at`
- `last_login_at`

唯一约束：

- `openid` 唯一。
- 如果微信返回 `unionid`，`unionid` 也应唯一。

### WechatLoginRequest

保存首次扫码后的待审批申请。

字段：

- `id`
- `openid`
- `unionid`
- `nickname`
- `avatar_url`
- `status`: `pending` / `approved` / `rejected`
- `requested_at`
- `reviewed_at`
- `reviewed_by_user_id`
- `target_user_id`
- `reject_reason`
- `state_nonce`

同一个 `openid` 只允许存在一条未处理申请，避免重复刷申请。

## 后端接口

### 公开接口

- `GET /api/auth/wechat/config`
  - 返回微信登录是否启用、扫码登录入口 URL 是否可用。
  - 不返回 `AppSecret`。

- `GET /api/auth/wechat/start`
  - 生成 `state`，写入短期状态表或服务端签名状态。
  - 返回微信扫码地址，或 302 跳转到微信扫码页。

- `GET /api/auth/wechat/callback`
  - 接收微信回调 `code` 和 `state`。
  - 校验 `state` 防止 CSRF。
  - 用 `code` 换取微信 `access_token` 和 `openid`。
  - 拉取微信用户资料。
  - 如果已有 active 的 `WechatIdentity` 且绑定用户启用，创建 `AuthSession` 并跳回前端登录成功页。
  - 如果没有绑定关系，创建或更新 `WechatLoginRequest`，跳回“申请已提交，等待管理员批准”页面。
  - 如果申请被拒，跳回“申请被拒，请联系管理员”页面。

### 管理员接口

- `GET /api/settings/wechat-login/config`
  - 查看当前微信登录配置，密钥只返回 `has_app_secret`。

- `POST /api/settings/wechat-login/config`
  - 创建或更新微信登录配置。

- `GET /api/settings/wechat-login/requests`
  - 查看申请列表，默认按待处理优先。

- `POST /api/settings/wechat-login/requests/{id}/approve`
  - 批准申请。
  - 支持两种模式：
    - 绑定到已有用户。
    - 新建用户并绑定微信。

- `POST /api/settings/wechat-login/requests/{id}/reject`
  - 拒绝申请，保存拒绝原因。

- `GET /api/settings/wechat-login/identities`
  - 查看已绑定微信用户。

- `POST /api/settings/wechat-login/identities/{id}/disable`
  - 停用微信登录绑定，不删除系统用户。

## 前端体验

### 登录页

登录页保留账号密码登录，同时增加一个独立按钮：

- “微信扫码登录”

点击后跳转到 `/api/auth/wechat/start`，由后端生成微信扫码地址。

回调完成后，前端显示三种状态：

- 已登录：写入 token，跳转首页。
- 已提交申请：提示等待管理员批准。
- 被拒绝或配置异常：提示联系管理员。

### 管理员后台

在“系统设置”里增加“微信登录”区域：

- 微信开放平台配置卡片。
- 待审批申请表格。
- 已绑定微信用户表格。

审批表格显示：

- 微信头像
- 昵称
- openid 后 6 位
- unionid 后 6 位
- 申请时间
- 状态
- 操作

批准时管理员选择：

- 绑定已有用户。
- 新建用户：填写用户名、角色，密码可自动生成随机临时密码。

## 用户数据隔离规则

系统采用“默认按创建者隔离”的策略。

普通用户：

- 只能看到自己创建的素材、脚本、数字人、视频任务、发布账号、发布记录、主题采集、参考视频拆解、转写任务。
- 只能修改自己创建的业务数据。
- 不能查看其他用户的业务列表、详情、文件下载、视频预览、图片预览。

管理员：

- 可以查看全部业务数据。
- 可以管理用户、微信登录配置、微信登录申请、模型配置和平台接入配置。
- 可以协助解绑微信身份和停用用户。

审核员：

- 保持现有只读/审核角色定位。
- 不能创建或修改业务数据。
- 访问范围按后续业务需要决定，首期建议只看自己名下数据，管理员另行处理跨用户审核。

技术实现规则：

- 新建业务记录时统一调用 `_assign_owner(record, user)`。
- 查询列表时统一使用 `_owned_statement(statement, Model, user)`。
- 访问详情、更新、删除、文件读取时统一使用 `_ensure_record_access(record, user, label, write=...)`。
- 没有 `owner_user_id` 的核心业务表，需要补字段或用关联父记录校验所有权。
- 媒体文件接口也必须校验记录所有权，不能只靠文件路径。

首期必须审计这些模块：

- `Material`
- `Topic`
- `Script`
- `DigitalHuman`
- `VideoTask`
- `VideoSegment`
- `VideoSegmentMaterial`
- `PublishRecord`
- `PlatformAccount`
- `TrendingSearch`
- `TrendingVideo`
- `TranscriptionTask`
- `ReferenceVideoAnalysis`

## 错误处理

- 微信未配置：登录页隐藏或禁用微信扫码按钮。
- 微信回调 state 不匹配：拒绝登录并提示重新扫码。
- 微信接口失败：展示“微信登录暂不可用”，后台记录错误。
- 未审批用户扫码：复用已有 pending 申请，不重复创建大量记录。
- 被拒用户再次扫码：展示拒绝状态，可由管理员重新打开或新建申请。
- 已绑定但系统用户停用：拒绝登录，提示联系管理员。

## 测试计划

### 后端

- 微信配置保存时不返回 `AppSecret`。
- 未配置微信时，start 接口返回明确错误。
- callback 校验 state。
- 新微信用户扫码后生成 pending 申请。
- 管理员批准后创建 `WechatIdentity`。
- 已绑定微信再次扫码可获得系统 token。
- 被停用用户不能扫码登录。
- 普通用户无法访问其他用户的素材和视频任务。

### 前端

- 登录页账号密码登录不受影响。
- 微信登录按钮在未配置时禁用或隐藏。
- 申请提交状态展示清楚。
- 管理员能看到待审批申请并完成批准/拒绝。

### 上线验证

1. 在微信开放平台配置回调域 `media.tech-ark.com`。
2. 在系统后台填入 AppID 和 AppSecret。
3. 使用一个未绑定微信扫码，确认生成申请。
4. 管理员批准并绑定用户。
5. 同一微信再次扫码，确认直接进入系统。
6. 创建素材和脚本，用另一个普通账号确认不可见。

## 实施顺序

1. 新增模型、schema 和数据库迁移兼容逻辑。
2. 新增微信 OAuth 服务类，隔离外部 HTTP 调用和签名/state 校验。
3. 新增公开登录接口和管理员配置/审批接口。
4. 更新登录页和系统设置页。
5. 审计并补齐核心业务模块的数据隔离。
6. 添加自动化测试和线上 smoke test。

## 用户配合事项

用户需要提供或在后台填写：

- 微信开放平台网站应用 AppID。
- 微信开放平台网站应用 AppSecret。
- 确认微信开放平台已开通“微信登录”能力。
- 确认回调域名为 `media.tech-ark.com`。
- 提供一个微信账号进行首次扫码申请测试。

## 决策

采用“扫码申请 + 管理员批准 + 用户绑定”的方案，不做自动注册放行。这样更符合当前系统的数据权限模型，也能避免陌生微信账号进入内容生产后台。
