# 视频号链接解析服务接入

目标：运营人员在“参考拆解”里粘贴视频号链接，系统自动解析出真实视频地址，下载为参考素材，然后继续做脚本、拍摄方式和剪辑方式拆解。

## 平台调用格式

后台“短视频采集接入”会把视频号链接发送到解析接口：

```http
POST /api/fetch_video_profile
Content-Type: application/json

{
  "url": "https://weixin.qq.com/sph/..."
}
```

平台会自动从返回 JSON 中查找视频地址，兼容这些字段：

- `data.feedInfo.h264VideoInfo.videoUrl`
- `data.feedInfo.h265VideoInfo.videoUrl`
- `data.feedInfo.videoUrl`
- `video_url`
- `media_url`
- `download_url`
- 其他嵌套字段中的 `finder.video.qq.com/.../stodownload` 地址

## 后台配置

进入：

```text
系统设置 -> 短视频采集接入
```

点击“视频号公开测试”或“视频号自有服务”，系统会自动填好：

```text
平台：视频号
用途：链接解析/下载
备注：method=post
```

保存后，用“链接解析测试”验证。

## 临时测试接口

可以先用公开测试接口验证链路：

```text
https://sph.litao.workers.dev/api/fetch_video_profile
```

公开站点适合验证流程，不建议作为长期生产依赖。

## 正式自有接口

推荐把解析服务部署成自己的接口：

```text
http://82.156.2.200:8099/api/fetch_video_profile
```

解析服务内部需要配置元宝 Web Cookie。这个 Cookie 只放在你的服务器或 Cloudflare Worker 环境变量里，不要填到平台后台，也不要发到聊天窗口。

仓库内置了一个轻量解析代理：

```text
services/link-resolver-proxy
```

它可以先把后台请求转发到公开测试站，保证平台操作链路先跑通；后续只需要把代理服务的 `UPSTREAM_RESOLVER_URL` 换成你的 Cloudflare Worker 或正式解析 API，后台接口地址可以保持不变。

## 推荐部署方式

当前可参考的开源方案是 `ltaoo/wx_channels_download` 的 `sph_deploy` 能力：

- 部署目标：Cloudflare Worker
- 可用接口：`POST /api/fetch_video_profile`
- 必需配置：Cloudflare Account ID、Cloudflare API Token、Worker 名称、元宝 Web Cookie

如果不想用 Cloudflare，可以把同样的接口封装到自己的服务器上，但核心逻辑仍然需要元宝 Cookie 才能解析普通视频号分享链接。
