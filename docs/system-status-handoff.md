# 系统现状与接手说明

更新时间：2026-06-28

这份文档是接手本系统时的第一入口。它记录的是当前线上实例的真实状态，不是产品设想。

## 线上环境

- 线上地址：`https://media.tech-ark.com/`
- 服务器：`82.156.2.200`
- 项目目录：`/opt/new-media-ai-platform`
- 平台容器：`server-platform-api-1`
- 平台本地端口：`127.0.0.1:8010 -> 8000`
- 数据库：`/opt/new-media-ai-platform/backend/data/platform.db`
- 素材上传服务：`asset-uploader.service`
- 素材上传接口：`https://media.tech-ark.com/asset-upload/api/upload`
- 素材公网目录：`https://media.tech-ark.com/asset-uploads/`

本地开发目录：

```text
/Users/Admin/Documents/Codex/2026-06-19/r/outputs/new-media-ai-platform
```

注意：本地 `127.0.0.1:8000` 和线上 `https://media.tech-ark.com` 是两套运行实例。处理线上页面、素材和模型状态时，必须确认自己操作的是线上数据库和线上容器。

## 文档地图

接手时建议按这个顺序看：

| 文档 | 用途 |
| --- | --- |
| `README.md` | 项目入口和本地启动说明。 |
| `docs/system-status-handoff.md` | 当前线上真实状态、已接入 API、排查顺序。接手优先看这份。 |
| `docs/integrations.md` | 各类模型/API 的适配方式和接口形状，不代表当前已经接入。 |
| `docs/model-selection.md` | 模型选型建议，不代表当前已经配置上线。 |
| `docs/deploy-own-server.md` | 自有服务器部署说明。 |
| `docs/https-domain-setup.md` | 域名、HTTPS、Nginx 和素材上传公网访问说明。 |
| `docs/api-smoke-test.md` | API 冒烟测试说明。 |
| `docs/release-checklist.md` | 发布前检查清单。 |

## 当前数据

线上当前已有：

- 数字人：3 个
- 素材：8 条
- 脚本：6 条
- 视频任务：0 个
- 发布记录：0 个
- 参考视频分析记录：6 条

当前数字人：

| 名称 | 头像素材 | 口播源视频 | 声音 |
| --- | --- | --- | --- |
| 李明亮讲酒店 | 已绑定 | 未绑定 | `Eddy (中文（中国大陆）)` |
| 酒店数智化控制系统梁欣欣 | 已绑定 | 未绑定 | 未复刻 |
| 黄丽的数字人 | 已绑定 | 已绑定 | 已复刻，`cosyvoice-v3-flash-voice0d32-f962e633bf8a4b04898068b7693b14bc` |

## API 与模型接入状态

以下状态来自线上 `/api/integrations/status` 和模型配置表。

| 模块 | 当前状态 | 真实 API | 说明 |
| --- | --- | --- | --- |
| 脚本生成 | 可用 | 是 | 线上模型配置显示 `volcengine-ark / doubao-seed-2-0-pro-260215` 已配置为真实 API。 |
| TTS 语音合成 | 可用 | 是 | 线上模型配置显示 `aliyun-cosyvoice / cosyvoice-v3-flash` 已配置为真实 API。 |
| 声音复刻 | 可用 | 是 | 已接入阿里云百炼 CosyVoice，provider 为 `aliyun-cosyvoice-clone`。 |
| 数字人驱动 | 可用 | 是 | 线上模型配置显示 `aliyun-wan-s2v / wan2.2-s2v` 已配置为真实 API。正式运行会产生模型费用。 |
| 视频生成 | 可用 | 是 | 线上模型配置显示 `seedance / doubao-seedance-2-0-260128` 已配置为真实 API。正式运行会产生模型费用。 |
| 视频理解/深度拆解 | 可用 | 是 | 线上模型配置显示 `volcengine-ark / doubao-seed-2-0-pro-260215` 已配置为真实 API。 |
| 视频合成/专业包装 | 可用 | 是 | 线上 `COMPOSITION_PROVIDER=remotion`，通过独立 Remotion 渲染服务做专业包装；FFmpeg 通用 concat 链路仍未作为主链路启用。 |
| 字幕引擎 | 可用 | 是 | 已内置自研字幕后处理：脚本文案自动断句、生成 SRT/ASS、按模板烧录到本地视频。依赖 FFmpeg 和真实本地视频；如果前置视频仍是 `mock://` 或云端 URL，会跳过烧录并记录真实状态。 |
| 链接素材采集 | 部分可用 | 否 | 系统支持粘贴链接保存为参考素材，也支持外部解析器下载视频；当前公开视频号 worker 在本机可解析，但线上服务器访问 `sph.litao.workers.dev` 不可达，需切换 Just One/TikHub/自有解析服务。 |
| 爆款采集 | 可用 | 否 | 已支持按主题、点赞/评论阈值、排序和采集数量创建任务；线上当前未配置真实 TikHub/自有采集 token，仍会回退到 `mock`。 |
| ASR 转写 | 可用 | 是 | 线上模型配置显示 `aliyun-bailian / qwen3-asr-flash` 已配置为真实 API。 |

已经真实打通的能力：

- 素材上传到公网：可用。
- 阿里云 CosyVoice 声音复刻：可用。
- 黄丽数字人声音复刻：已完成并写回 `voice_id`。

尚未真实打通或仍需验证的能力：

- FFmpeg 通用 concat 链路：未作为主链路启用；当前真实专业包装主链路是 Remotion。
- 链接素材采集：粘贴链接保存已可用；自动解析下载依赖第三方/自有链接解析服务。公开视频号 worker `https://sph.litao.workers.dev/api/fetch_video_profile` 在本机可解析测试链接，但生产服务器访问该域名报 `Network is unreachable` 或超时，不能作为稳定线上解析服务。
- 爆款采集：功能链路已可用，支持平台采集配置 `purpose=trending`，也内置 TikHub 抖音搜索预设；线上仍未配置真实采集 token，所以当前真实状态为 `mock`/待接入。
- 真实接口的费用/配额/失败重试策略：数字人、Seedance、TTS、ASR 已显示真实 API 可用，但正式批量跑之前仍要确认费用阈值、并发限制和失败重试策略。

## 已经验证的功能

### 总览页面

- 线上页面：`https://media.tech-ark.com/#overview`。
- “最新脚本”和“最近视频任务”已合并为“最近动态”面板，用 Tab 切换查看。
- 两个 Tab 都使用轻量分页表格，每页最多 6 条，只显示关键字段；长标题单行省略，不在总览撑开内容。
- 点击“详情”复用右侧抽屉查看完整脚本或视频任务详情。

### 全站列表规范

- 所有主要列表统一为每页最多 6 条，超过 6 条显示上一页/下一页。
- 已接入分页的列表包括：候选脚本、总览脚本、总览视频任务、视频任务页脚本、视频任务表、素材、参考素材、数字人、发布记录、平台账号、模型配置、模型用量、成片存储记录、系统账号、采集配置、爆款参考、转写任务、深度拆解任务。
- 表格和卡片列表只展示关键字段，长内容进入详情抽屉或详情区域。

### 数字人素材

- 线上页面：`https://media.tech-ark.com/#humans`
- 已改成抽屉形式：
  - 主页面只显示紧凑清单。
  - 点“查看”后在右侧抽屉显示头像、口播视频、声音 ID 和素材地址。
- 已同步本地历史素材到线上：
  - 李明亮
  - 梁欣欣
  - 黄丽
  - 视频号参考素材

### 链接素材采集

- 线上页面：`https://media.tech-ark.com/#analysis` 的“导入参考”，以及 `#settings` 的“短视频采集接入/链接解析测试”。
- 已支持的入口：
  - 粘贴视频链接保存为参考素材。
  - 配置链接解析服务后自动解析下载视频文件。
  - 解析失败时保存链接，不假装已经下载。
- 本次实测链接：`https://weixin.qq.com/sph/ARzjCDiEUH`。
  - 本机直接调用 `https://sph.litao.workers.dev/api/fetch_video_profile` 可解析出作者、描述、点赞/评论和 `finder.video.qq.com/.../stodownload` 视频地址。
  - 线上服务器和平台容器访问 `sph.litao.workers.dev` 不可达/超时，所以系统只能保存为参考链接，不能自动下载。
  - 测试时线上生成参考素材 `#13`，状态为“需上传源文件”。
- 已改进：
  - 链接解析测试会返回并展示 `diagnostics`，能看到具体是“解析服务不可达、超时、缺 Token、未返回视频地址”等原因。
  - 链接解析服务支持 `timeout=秒数` 备注，默认不再长时间卡住页面。
  - 后端新增 `provider=justone` 支持，可直接配置 Just One 视频号解析：`api_base=http://47.117.133.51:30015`，Access Token 填 Just One token。
- 下一步要把线上解析从公开视频号 worker 切换到服务器可访问的正式 provider，例如 Just One、TikHub 或自有解析中转。

### 爆款采集

- 线上页面：`https://media.tech-ark.com/#trending`。
- 已支持以主题为线索创建采集任务：
  - 平台、关键词、行业/分类。
  - 采集数量，默认 20，最多 100。
  - 最低点赞、最低评论过滤。
  - 按综合互动、点赞、评论或播放排序。
- 采集结果列表会展示播放、点赞、评论、分享等关键指标，并可把条目保存到“参考拆解”的素材库中。
- 后端支持两类真实来源：
  - 环境变量 `TRENDING_SEARCH_PROVIDER=http-json` + `TRENDING_SEARCH_API_BASE`。
  - 系统设置里的平台采集配置 `purpose=trending`，激活后优先使用数据库配置。
- 已内置 TikHub 抖音搜索预设：
  - `api_base=https://api.tikhub.io`
  - `notes` 中 `provider=tikhub`、`method=post`、`path=/api/v1/douyin/search/fetch_video_search_v2`
  - `Access Token` 填 TikHub API Key。
- 当前线上真实状态：没有激活可用的真实爆款采集配置时，系统会返回 mock 示例，不会假装已经从抖音/视频号真实采集。

### 内容创作页面

- 线上页面：`https://media.tech-ark.com/#creation`
- 已修复按钮溢出问题。
- 参数栏会自动换行，不会再把“AI 生成候选方案”挤出右侧。
- 脚本详情底部已改成审核操作台：左侧选择成片方式，中间显示生成条件/提醒，右侧放重新生成、审核通过并自动生成视频、查看生成进度。
- 操作台在桌面横向排布，窄屏自动堆叠，避免说明文字被挤成竖排。
- 一键生成视频会根据真实接口状态自动选择可执行路线：
  - 已选择数字人且真实数字人驱动可用：默认 `数字人口播模板`。
  - 真实视频生成模型可用：默认 `Seedance AI 实景/B-roll`。
  - 真实数字人/视频生成都不可用：默认 `图文草稿预览`，这条链路会生成服务器本地 MP4，并继续触发自动字幕烧录，便于完整验证任务、预览、保存和发布准备流程。
- `/api/integrations/status` 的视频生成状态已修正：Seedance 只有同时配置 API Base 和 API Key 才会被视为真实可用；视频合成只有 `ffmpeg` 才标记为真实后处理。

### 视频任务页面

- 线上页面：`https://media.tech-ark.com/#tasks`。
- “已生成脚本”列表已改为轻量分页表格，每页最多 6 条，只展示脚本编号/标题、平台/时长、视频任务数、创建时间和操作。
- 口播稿、分镜、视频提示词、标题建议、合规提醒等长内容不在表格里展开，点击“详情”在右侧抽屉查看。
- 视频任务已接入自动字幕引擎：
  - 新建任务默认启用字幕，字幕风格可选 `AI 自动选择`、`商务清晰`、`爆款大字`、`数字人口播`、`教程说明`、`极简底栏`。
  - 后端会为生成出的本地视频自动产出 `captions.srt`、`captions.ass` 和 `captioned-video.mp4`。
  - 任务字段会记录真实状态：`subtitle_status`、`subtitle_style`、`subtitle_srt_path`、`subtitle_ass_path`、`captioned_output_path`。
  - 预览、视频存储和发布校验优先使用 `captioned_output_path`；删除成片时会一并清理字幕文件。
  - 当前版本字幕时间轴来自脚本口播稿和视频时长自动分配；真实 ASR/字级时间戳接入后，可替换为逐词高亮和更精确时间轴。

### 专业包装/Remotion

- 已新增 `services/remotion-renderer`，作为独立 Node/Remotion 渲染服务。
- 已新增后端 `ProfessionalRenderClient`，当 `COMPOSITION_PROVIDER=remotion` 且 `REMOTION_RENDER_API_BASE` 可用时，会在任务最终阶段调用 Remotion 做专业包装。
- 第一版模板：`business_talking`，包含基础视频主体、顶部标题、品牌水印、卖点卡片、底部字幕区、进度条和轻动态背景。
- 线上已启用：
  - 生产配置：`COMPOSITION_PROVIDER=remotion`，`REMOTION_RENDER_API_BASE=http://remotion-renderer:3100`。
  - 生产容器：`server-remotion-renderer-1`。
  - 镜像：`new-media-remotion-renderer:20260628-professional`。
  - `/api/integrations/status` 已显示 `composition.provider=remotion`、`real_api=true`。
  - 已在线上通过平台容器调用 `http://remotion-renderer:3100/render`，生成测试文件：`/opt/new-media-ai-platform/backend/data/remotion-test/output.mp4`。
- 本地也已验证：
  - Remotion 服务 `/health` 正常。
  - 无源模板渲染 MP4 成功。
  - 基础 MP4 二次包装渲染成功。
- 发布注意：
  - 生产机存在保护标记 `/opt/factory-manager/shared/state/.production-no-docker-build`，禁止直接 Docker build。
  - 本次发布采用本机构建 linux/amd64 镜像 tar、上传生产机 `docker load`、`docker compose up -d --no-build` 的方式启用。
  - 后续正式发布仍建议通过 CI/构建机预构建镜像并推送仓库，然后生产机只执行 `docker compose pull && docker compose up -d`。

### 视频存储位置

- 线上页面：`https://media.tech-ark.com/#settings` 的“视频存储位置”。
- 页面面向操作人员提供“选择电脑文件夹”，使用浏览器本机文件夹权限保存成片。
- 选择后的文件夹句柄保存在浏览器本地权限里，不写入服务器数据库，也不展示服务器内部目录。
- 可开启“生成后自动保存到这个文件夹”。注意：自动保存依赖页面打开并拥有浏览器文件夹写入权限；在“视频任务”或“视频存储位置”页面时，前端会定时检查新成片。
- 成片列表提供“保存到电脑”按钮，会把服务器成片文件写入用户选择的本机文件夹，不走普通下载弹窗。
- 服务器底层仍保留统一保存根目录，用于预览、发布和系统留档，并自动按类型归档：
  - 成片库
  - 分段视频库
  - 数字人口播库
  - 音频库
  - 素材库
- 原来的后端 `/settings/video-storage/choose-folder` 已移除。线上 Docker/服务器环境无法替用户电脑弹出文件夹选择窗口。
- 视频任务列表只显示业务保存位置、文件状态和“保存到电脑”操作，不再给操作人员展示或复制真实路径。

### 全站布局

已用浏览器自动检查这些页面，确认没有横向溢出：

- 总览
- 数字人素材
- 内容创作
- 参考拆解
- 视频任务
- 爆款采集
- 发布中心
- 系统设置：模型用量、AI 模型接入、视频存储位置、短视频采集接入、账号管理

## 部署与静态文件注意事项

线上容器只挂载了：

```text
/opt/new-media-ai-platform/backend/data -> /app/data
```

所以只改宿主机上的：

```text
/opt/new-media-ai-platform/backend/app/static/
```

不会立刻影响线上页面。更新前端静态文件后，需要执行：

```bash
docker cp backend/app/static/index.html server-platform-api-1:/app/app/static/index.html
docker cp backend/app/static/app.js server-platform-api-1:/app/app/static/app.js
docker cp backend/app/static/styles.css server-platform-api-1:/app/app/static/styles.css
```

更稳妥的做法是重新构建并重启平台容器。

## 素材上传说明

平台后台“视频存储位置/素材服务器上传”当前应保持：

```text
启用：是
上传接口：https://media.tech-ark.com/asset-upload/api/upload
访问域名：https://media.tech-ark.com/asset-uploads
文件字段名：file
Token：已保存
```

不要再使用旧地址：

```text
http://82.156.2.200:8099/api/upload
http://82.156.2.200:8099/uploads
```

旧地址曾导致本地补传失败，错误表现为 `ReadError`。

## 接手排查顺序

1. 先确认当前浏览器地址是本地还是线上。
2. 查线上接口状态：

```bash
curl https://media.tech-ark.com/api/health
curl https://media.tech-ark.com/api/integrations/status
```

3. 登录后查模型配置、素材上传配置和数据量：

```bash
/api/settings/models
/api/settings/remote-upload
/api/dashboard
/api/digital-humans
/api/materials
```

4. 如果页面看不到数据，但接口有数据，优先检查静态文件是否已经同步进容器。
5. 如果声音复刻失败，优先检查源视频素材是否有公网 `source_url`。
6. 如果视频生成失败，要先确认“数字人驱动”和“视频生成”是否已经从 mock 切到真实 API。

## 下一步建议

优先补齐这些真实接口，系统才算能从“素材/脚本管理”走到“真实成片”：

1. 接入真实脚本模型：火山方舟 Doubao 或阿里云 Qwen。
2. 接入真实 TTS：阿里云 CosyVoice 普通语音合成。
3. 接入真实数字人驱动：阿里云数字人、D-ID、HeyGen、SadTalker/MuseTalk 服务其一。
4. 接入真实视频生成：Seedance。
5. 接入 FFmpeg 合成，替换 mock 合成。
6. 接入 ASR，支持参考视频转写。

任何新接入的真实 API，都必须同步更新本文件的“API 与模型接入状态”表。

## 维护规则

- 每次修改功能、接口、模型配置、部署方式、关键数据同步方式后，必须同步更新本文件。
- 新增或切换真实模型 API 后，必须更新“API 与模型接入状态”。
- 线上新增关键数据、素材同步方式或部署方式变化后，必须更新“线上环境”“当前数据”或“部署与静态文件注意事项”。
- 新增或调整模型/API 适配方式后，同时更新 `docs/integrations.md`。
- 如果只是写了适配方案，还没有在线上配置并验证，不要在本文件里标记为“真实 API：是”。
