from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import httpx


ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from app.services.video_analysis import ReferenceAnalysisResult, ReferenceVideoAnalyzer  # noqa: E402
from app.api.reference_learning import _link_resolver_credentials, _supports_ytdlp  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.services.link_resolver import LinkResolverCredential, ShortVideoLinkResolver, detect_short_video_platform  # noqa: E402


def main() -> None:
    assert _supports_ytdlp("https://www.douyin.com/video/123")
    assert _supports_ytdlp("https://www.bilibili.com/video/BV123")
    assert not _supports_ytdlp("https://weixin.qq.com/sph/example")
    assert not _supports_ytdlp("https://example.com/video/123")
    assert detect_short_video_platform("https://b23.tv/example") == "bilibili"
    assert detect_short_video_platform("https://youtu.be/example") == "youtube"

    settings = get_settings()
    original_cookie = settings.wechat_channels_resolver_cookie
    settings.wechat_channels_resolver_cookie = "test-cookie"

    class EmptySession:
        def exec(self, statement):
            return self

        def all(self):
            return []

    internal_credentials = _link_resolver_credentials(EmptySession(), "wechat_channels")
    assert len(internal_credentials) == 1
    assert internal_credentials[0].access_token == "test-cookie"
    assert "provider=yuanbao" in internal_credentials[0].notes
    assert "visibility=internal" in internal_credentials[0].notes
    settings.wechat_channels_resolver_cookie = original_cookie

    resolver = ShortVideoLinkResolver()
    assert resolver._yuanbao_feed_credentials(
        "https://channels.weixin.qq.com/finder-preview/pages/feed?token=general-token&eid=export-id"
    ) == ("export-id", "general-token")
    missing_cookie = asyncio.run(
        resolver._resolve_with_credential(
            "https://weixin.qq.com/sph/example",
            "wechat_channels",
            LinkResolverCredential(
                platform="wechat_channels",
                display_name="系统内置解析",
                api_base="https://yuanbao.tencent.com",
                notes="provider=yuanbao",
            ),
        )
    )
    assert missing_cookie is not None
    assert missing_cookie.needs_manual_upload is True
    assert "Cookie" in missing_cookie.diagnostic_errors[0]

    config = SimpleNamespace(
        provider="volcengine-ark",
        api_base="https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        api_key="test-key",
        model_name="doubao-seed-2-1-pro-260628",
    )
    analyzer = ReferenceVideoAnalyzer(config)
    assert analyzer._is_volcengine_ark(config.provider)
    assert analyzer._ark_api_base(config.api_base) == "https://ark.cn-beijing.volces.com/api/v3"
    assert analyzer._responses_output_text(
        {"output": [{"content": [{"type": "output_text", "text": '{"quality_score": 91}'}]}]}
    ) == '{"quality_score": 91}'
    review_prompt = json.loads(analyzer._deep_review_prompt({"timeline": []}, 60))
    assert review_prompt["video_type"] == "短视频"
    assert "critical_moments" in review_prompt["json_schema"]

    local = ReferenceAnalysisResult(
        duration_seconds=12,
        width=1080,
        height=1920,
        fps=25,
        has_audio=True,
        scene_count=2,
        avg_shot_seconds=6,
        visual_change_frequency="中等",
        contact_sheet_path="contact.jpg",
        dense_contact_sheet_path="dense.jpg",
        timeline_json='[{"start_second":0,"end_second":6,"script_function":"钩子"}]',
        script_analysis="痛点开场",
        shooting_analysis="人物中景",
        editing_analysis="硬切",
        reusable_template="先提出问题",
        reuse_notes="只学习结构",
        transcript="原转写",
    )
    merged = analyzer._merge_model_analysis(
        local,
        {
            "transcript": "模型校对后的完整口播。",
            "transcript_segments": [
                {"start_second": 0, "end_second": 3, "text": "模型校对后的完整口播。", "estimated": False}
            ],
            "timeline": [
                {
                    "start_second": 0,
                    "end_second": 6,
                    "script_function": "钩子",
                    "reuse_instruction": "换成公司痛点",
                }
            ],
            "reference_blueprint": {"hook": "问题开场", "audience": "酒店负责人"},
            "edit_plan": [
                {"start_second": 0, "end_second": 6, "action": "keep", "visual": "数字人口播"}
            ],
            "quality_score": 91,
        },
        {"input_tokens": 100, "output_tokens": 30, "total_tokens": 130},
    )
    assert merged.model_enhanced is True
    assert merged.transcript == "模型校对后的完整口播。"
    assert json.loads(merged.blueprint_json)["audience"] == "酒店负责人"
    assert json.loads(merged.edit_plan_json)[0]["action"] == "keep"
    assert json.loads(merged.transcript_segments_json)[0]["estimated"] is False

    reviewed = analyzer._merge_deep_review_payload(
        {
            "reference_blueprint": {"hook": "问题开场"},
            "timeline": [{"start_second": 0, "end_second": 5}],
        },
        {
            "review_summary": "钩子有证据支持",
            "critical_moments": [
                {
                    "start_second": 0,
                    "end_second": 3,
                    "evidence": {"transcript": "你是不是也遇到这个问题"},
                    "retention_score": 88,
                    "confidence": 92,
                    "recommendation": "前三秒直接展示结果",
                }
            ],
        },
    )
    assert reviewed["reference_blueprint"]["deep_review"]["review_summary"] == "钩子有证据支持"
    assert reviewed["timeline"][0]["retention_score"] == 88
    assert reviewed["timeline"][0]["optimization"] == "前三秒直接展示结果"
    assert analyzer._sum_usage(
        {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
    )["total_tokens"] == 43
    timeout = httpx.ReadTimeout("", request=httpx.Request("POST", "https://example.com"))
    assert (str(timeout).strip() or timeout.__class__.__name__) == "ReadTimeout"

    class FallbackAnalyzer(ReferenceVideoAnalyzer):
        vision_calls = 0

        async def _call_volcengine_video_understanding(self, *args):
            raise httpx.ReadTimeout("", request=httpx.Request("POST", "https://example.com"))

        async def _call_openai_compatible_vision(self, prompt, image_path, max_tokens=5000):
            self.vision_calls += 1
            if self.vision_calls == 1:
                return {"quality_score": 90, "reference_blueprint": {}, "timeline": []}, {"total_tokens": 10}
            return {"review_summary": "抽帧证据复核完成", "critical_moments": []}, {"total_tokens": 5}

    fallback = asyncio.run(
        FallbackAnalyzer(config)._enhance_with_model(
            Path("reference.mp4"),
            replace(local, analysis_source="local", model_enhanced=False),
            "",
        )
    )
    assert fallback.analysis_source == "contact_sheet_deep"
    assert fallback.total_tokens == 15

    estimated = analyzer._default_transcript_segments("第一句。第二句！", 10)
    assert len(estimated) == 2
    assert estimated[-1]["end_second"] == 10
    assert all(item["estimated"] is True for item in estimated)
    print("video understanding smoke ok")


if __name__ == "__main__":
    main()
