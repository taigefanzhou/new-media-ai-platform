# 视频号链接解析服务接入

目标：运营人员在“参考拆解”里粘贴视频号链接，系统自动解析出真实视频地址，下载为参考素材，然后继续做脚本、拍摄方式和剪辑方式拆解。

## 内部处理流程

后端收到视频号分享链接后，直接执行授权开源方案的两步解析流程：

1. 使用服务器保存的腾讯元宝 Web Cookie 解析分享链接。
2. 使用返回的临时凭据读取视频号 feed，提取视频、标题和作者信息。

平台会从返回 JSON 中查找视频地址，兼容这些字段：

- `data.feedInfo.h264VideoInfo.videoUrl`
- `data.feedInfo.h265VideoInfo.videoUrl`
- `data.feedInfo.videoUrl`
- `video_url`
- `media_url`
- `download_url`
- 其他嵌套字段中的 `finder.video.qq.com/.../stodownload` 地址

## 服务端配置

解析能力只在服务端配置，不在业务页面展示供应方、接口地址或 Cookie：

```text
WECHAT_CHANNELS_RESOLVER_COOKIE=<yuanbao web cookie>
```

运营人员只需在“参考拆解”粘贴视频号链接，系统会自动完成解析和下载。

这条路线不调用 Just One 或其他按次收费解析 API。核心解析流程参考已获授权的
[`ltaoo/wx_channels_download`](https://github.com/ltaoo/wx_channels_download)；Cookie 失效后需要更新服务器密钥。
