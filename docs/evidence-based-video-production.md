# 证据驱动的视频生成与剪辑流程

## 目标

系统不再通过连续生成样片来猜提示词，而是在调用付费视频模型前完成分镜约束、参考素材分工和调用次数预检；生成后只针对失败镜头处理，最后使用确定性后期完成声音、字幕和包装。

## 研究结论

### 1. 生成模型只负责可控底片

火山引擎说明 Seedance 2.0 支持文字、图片、音频和视频混合参考，图片适合锁定主体、元素和场景，视频适合控制镜头语言、动作和节奏，音频适合提供声音与节拍参考。模型最长生成 15 秒，因此长视频应由短镜头和确定性后期组成，不能要求模型一次完成整条成片。

系统规则：

- 每个镜头只有一个叙事意图、一个主动作、一个运镜和一个结束状态。
- 每份参考素材只有一个主要职责，避免身份、动作、场景和节奏互相争夺控制权。
- 真人单镜头若选择行走口播，就不再同时安排回头、操作道具、定时灯光变化或表情突变。
- 模型生成干净底片；字幕、标题、Logo、UI 和 CTA 由系统后期生成。

来源：

- [火山引擎 Seedance 2.0 官方介绍](https://developer.volcengine.com/articles/7606009619928449070)
- [Doubao Seedance 2.0 系列提示词指南](https://www.volcengine.com/docs/82379/2222480?lang=zh)
- [Seedance 2.0 功能页](https://www.volcengine.com/activity/seedance2)
- [Seedance 2.0 社区工作流](https://github.com/Emily2040/seedance-2.0)

### 2. 内容结构先于画面复杂度

短视频先完成 Hook、核心信息和 CTA。TikTok 官方创意指南强调开头 3-6 秒对吸引注意至关重要，并建议竖屏、全屏、高分辨率和声音参与。系统因此先删问候、品牌片头和重复表达，再生成画面。

系统规则：

- 前 3-6 秒直接给痛点、冲突、结果或利益点。
- 中段只保留支撑一个核心观点的证据和动作。
- 结尾使用与内容一致的行动引导，不突然插入无关广告卡。

来源：

- [TikTok Creative Tips](https://ads.tiktok.com/business/creativecenter/quicktok/online/creative-tips-for-home-and-lifestyle/pc/en)
- [TikTok Creative Best Practices](https://ads.tiktok.com/business/en-US/blog/creative-best-practices-top-performing-ads)

### 3. 剪辑是独立生产阶段

Adobe 对 J Cut 和 L Cut 的定义说明，声音与画面不必在同一帧切换：下一镜声音可提前进入，上一镜声音也可延续到下一画面。FFmpeg 已提供字幕、交叉转场和 EBU R128 响度归一化能力，现有系统无需为这些基础后期另接付费 API。

系统固定执行七遍后期：

1. 主叙事粗剪。
2. 对白、停顿和语速整理。
3. 按语义覆盖 B-roll。
4. J/L Cut、环境声、音乐和音效。
5. 中文字幕和关键词强调。
6. 曝光、白平衡、肤色和镜头匹配。
7. 技术、视觉、内容和版权质检。

来源：

- [Adobe J Cut / L Cut 官方说明](https://helpx.adobe.com/cn/premiere/desktop/edit-projects/trim-clips/perform-j-cuts-and-l-cuts.html)
- [FFmpeg Filters Documentation](https://ffmpeg.org/ffmpeg-filters.html)
- [OpenTimelineIO](https://opentimelineio.readthedocs.io/en/latest/index.html)

### 4. 字幕使用可验证规则

Netflix 简体中文字幕规范规定每行最多 16 个汉字、最多两行，并要求字幕避开画面文字、嘴、脸和重要动作。短视频平台还需额外避开右侧操作区和底部说明区。

系统规则：

- 默认每行不超过 16 个汉字、最多两行。
- 优先按语义和停顿断句，不按固定字数生硬切断。
- 不使用大面积黑底块；使用字重、描边和少量关键词色彩保证可读性。
- 字幕位置连续稳定，不随镜头上下跳动。

来源：

- [Netflix 简体中文字幕规范](https://partnerhelp.netflixstudios.com/hc/en-us/articles/215986007-Chinese-Simplified-Timed-Text-Style-Guide)

### 5. 质检必须分项，不靠单一总分

VBench 2.0 将生成视频质量拆成人物真实性、可控性、物理规律、常识和创造性等维度；VideoScore2 进一步强调视觉质量、文图对齐和物理/常识一致性。系统采用适合当前业务的六项检查：

- 人物真实性。
- 脚本和提示词对齐。
- 时序与场景连续性。
- 物理合理性。
- 文字与水印。
- 最终音频与字幕。

任一关键维度低于门槛即进入人工复核。系统最多针对明确的严重缺陷重做一次当前镜头，不重新生成已经通过的镜头，也不因一般风格偏好自动烧第二次费用。

来源：

- [VBench 2.0](https://vchitect.github.io/VBench-2.0-project/)
- [VideoScore2](https://arxiv.org/abs/2509.22799)

## 系统执行顺序

```text
主题/参考视频
  -> 原创脚本与 Hook 检查
  -> 镜头合同与参考素材角色检查
  -> 生成段数、候选数和参数合法性检查
  -> 按镜头生成干净底片
  -> 本地技术检查 + 视觉分项检查
  -> 仅重做失败镜头一次
  -> 确定性剪辑、声音、字幕和包装
  -> 最终分项质检
  -> 人工终审/发布
```

## 暂不引入的能力

- 不引入新的自动剪辑服务 API。现有 FFmpeg、素材库、模型理解和任务系统足以完成第一阶段。
- 不引入 OpenTimelineIO，仅保留为未来需要导出 Premiere、DaVinci 或剪映交换时间线时的候选。
- 不在生产服务器部署 WhisperX；当前转写链路足够使用，只有字幕时间误差成为稳定问题时再评估词级强制对齐。
- 不把生成候选数量当作质量策略。默认一个候选，仅严重可修复问题允许一次定向重做。
