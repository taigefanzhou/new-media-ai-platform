from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from app.services.video_analysis import ReferenceAnalysisResult, ReferenceVideoAnalyzer  # noqa: E402


def main() -> None:
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

    estimated = analyzer._default_transcript_segments("第一句。第二句！", 10)
    assert len(estimated) == 2
    assert estimated[-1]["end_second"] == 10
    assert all(item["estimated"] is True for item in estimated)
    print("video understanding smoke ok")


if __name__ == "__main__":
    main()
