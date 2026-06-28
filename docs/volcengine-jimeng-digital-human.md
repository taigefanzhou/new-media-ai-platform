# 火山即梦数字人接入状态

## 当前状态

- 系统已增加模型供应商：`volcengine-jimeng-digital-human`。
- 系统已增加平台凭证类型：`platform=volcengine`，`purpose=digital_human`。
- 本地和线上已配置火山 `AccessKeyID/SecretAccessKey` 凭证模板，状态为启用。
- 火山即梦数字人使用火山 OpenAPI AK/SK 体系，不复用当前火山方舟 `ark-*` / `sk-*` 模型 API Key。
- 当前已完成配置入口、AK/SK 保存、防误用校验和真实 Submit/GetResult 适配器。
- 已用同一套 AK/SK 和签名代码调用 IAM 接口，返回标准 IAM `AccessDenied`，说明密钥和签名链路有效。
- 火山侧开通小云雀服务后，已真实提交并生成测试视频；当前仍需人工确认画质和人物稳定性后再决定是否切为默认数字人模型。
- 测试样片：`https://media.tech-ark.com/asset-uploads/volcengine-jimeng-sample-20260628.mp4`
- 火山任务 ID：`1fd5262a72c711f1a494043f72b46be0`

## 当前适配的接口

```text
Service=cv
Region=cn-north-1
Submit Action=CVSync2AsyncSubmitTask
Result Action=CVSync2AsyncGetResult
Version=2022-08-31
app_id=101606596
req_key=pippit_iv2v_v20_cvtob_with_vinput
```

提交任务会传入公网可访问的头像图片 URL 和参考视频 URL：

```json
{
  "req_key": "pippit_iv2v_v20_cvtob_with_vinput",
  "app_id": 101606596,
  "prompt": "根据参考视频生成自然人物视频",
  "img_url_list": ["https://..."],
  "video_url_list": ["https://..."]
}
```

注意：这一路是“照片 + 参考视频”的有参考生视频/动作参考路线，不是严格音频驱动口型同步。当前系统仍会生成音频，但该火山接口本身不会按音频做精确唇形。

按当前火山接口文档和探测结果，`app_id` 放在提交任务请求中；查询结果请求仍使用 `req_key` 和 `task_id`。

## 配置方式

1. 在火山控制台开通即梦 AI 小云雀/动作模仿有参考生视频能力，并确认 `app_id=101606596` 和 `req_key=pippit_iv2v_v20_cvtob_with_vinput` 对账号可用。
2. 在火山访问控制里创建或获取 `AccessKeyID` 和 `SecretAccessKey`。
3. 进入系统设置，打开“短视频采集接入”，点击“火山即梦 AK/SK”预设。
4. 将 `AccessKeyID` 填到 `Client ID`，将 `SecretAccessKey` 填到 `Client Secret`，保持启用。
5. 进入“AI 模型接入”，点击“火山即梦数字人”预设并保存。

## 官方链接

- 即梦 AI 文档入口：https://www.volcengine.com/docs/85621
- 小云雀-智能生视频 Agent 2.0 有参考接口文档：https://www.volcengine.com/docs/85621/2359610
- 动作模仿 2.0 产品介绍：https://www.volcengine.com/docs/85621/2205633
- 火山 OpenAPI 签名调用指南：https://www.volcengine.com/docs/6369/67265
- 火山 OpenAPI 签名示例：https://github.com/volcengine/volc-openapi-demos/blob/main/signature/python/sign.py
- 方舟 Base URL 及鉴权：https://www.volcengine.com/docs/82379/1298459
- 访问控制/密钥管理控制台：https://console.volcengine.com/iam/keymanage/

## 接入备注

火山侧如果再次返回 `50400 Access Denied`，需要在工单或控制台里确认账号已开通：

```text
产品/能力：即梦 AI 小云雀-智能生视频 Agent 2.0 有参考
OpenAPI：CVSync2AsyncSubmitTask / CVSync2AsyncGetResult
Service/Region：cv / cn-north-1
app_id：101606596
req_key：pippit_iv2v_v20_cvtob_with_vinput
```
