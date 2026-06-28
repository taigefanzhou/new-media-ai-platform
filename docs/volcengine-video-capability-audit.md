# 火山视频能力接入审计

更新时间：2026-06-28

## 结论

当前系统此前只把 Ark Seedance 当作文生视频使用，实际只传了文本提示词。火山视频能力应按三层接入：

1. Ark Seedance 2.0：默认视频生成通道，优先用于脚本分镜、参考图/参考视频、首尾帧连续生成、B-roll、素材补镜头。
2. Ark 视频理解/豆包视觉：用于参考视频拆解、镜头结构、字幕风格、脚本抽取和合规分析。
3. 小云雀/即梦 Agent：高成本能力，只用于人工确认后的高还原参考生成，不作为默认通道。

## 官方能力入口

- Seedance 2.0 活动页：https://ai.volcengine.com/activity/seedance2
- Seedance 2.0 API 参考：https://www.volcengine.com/docs/82379/1520757
- Seedance SDK 示例：https://www.volcengine.com/docs/82379/2298881
- 火山费用中心账单 API：https://api.volcengine.com/api-docs/view?action=ListBillDetail&serviceCode=billing&version=2022-01-01

## 当前已修正

`MediaGenerationClient._generate_seedance_clip_via_ark` 已从纯文本 content 升级为多模态 content：

- 文本脚本：`type=text`
- 参考图片/头像/产品图：`type=image_url`
- 参考视频/参考素材/口播源视频：`type=video_url`
- 参考音频：`type=audio_url`

`VideoPipeline._run_segment` 已把分段匹配到的素材传给 Seedance 作为参考输入。`reference_only` 素材不会被直接混剪进成片，但可以作为 Seedance 参考输入。

## 计费边界

小云雀账单已确认：

- 产品：小云雀
- 计费项：智能生视频Agent - Seedance 2.0 fast 720p 有参考
- 单价：1.26 元/秒
- 本月已计：523 秒
- 金额：658.98 元

因此默认策略必须是：

- 不默认调用小云雀。
- 默认走 Ark Seedance。
- 小云雀调用前必须展示预计秒数和预计费用。
- 超过 10 秒必须二次确认。

## 推荐生成策略

### 参考素材 + 脚本生成

默认走 `seedance_scene`：

1. 用参考视频分析生成分镜。
2. 自动匹配素材库里的参考图/参考视频。
3. Ark Seedance 按分段生成 4-10 秒视频。
4. 后处理统一裁切、字幕、水印检查。

### 数字人口播

Seedance 可参考人物图和视频风格，但不应承诺严格口型同步。严格口播仍应走专门数字人接口：

- 低成本预览：已有素材包装 + 男声 TTS + 字幕。
- 中等成本：阿里 Wan S2V/VideoRetalk 分段测试。
- 高成本：小云雀/即梦 Agent，人工确认后使用。

## 后续待接能力

1. 首帧/尾帧连续生成：上一段尾帧自动作为下一段参考图。
2. 参考强度/人物一致性参数：等官方 schema 完整确认后接入。
3. 水印控制：优先在 Ark 参数里关闭，后处理做兜底检测。
4. 成本预估：按模型、时长、分辨率计算任务预计费用。
5. 小云雀审计：每次 SubmitTask 写入本地 usage 和 request id。
