import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from app.api.video_tasks_support import _build_video_task
from app.models.entities import DigitalHuman, Script, VideoSegment
from app.services.ai_clients import MediaGenerationClient
from app.services.export_profiles import resolve_export_profile
from app.services.pipeline import VideoPipeline
from app.services.video_quality import VideoQualityResult
from app.services.video_skills import he_yiyi_hotel_template_manifest


def test_he_yiyi_reference_template_is_executable() -> None:
    template = he_yiyi_hotel_template_manifest()
    assert template["key"] == "he_yiyi_hotel_v1"
    assert template["reference_analysis_id"] == 8
    assert len(template["sections"]) == 7
    assert template["asset_policy"] == "owned_or_licensed_only"
    assert template["identity"]["source"] == "active_volcengine_enterprise_asset_only"
    assert template["identity"]["forbidden_material_ids"] == (10, 25, 31)
    assert template["audio"]["voice_gender"] == "female"

    profile = resolve_export_profile("wechat_channels_portrait")
    assert (profile.width, profile.height, profile.aspect_ratio) == (1080, 1920, "9:16")

    script = Script(
        id=1,
        hook="酒店经营干货",
        voiceover="酒店智能客控需要从真实运营问题出发。",
        storyboard="人物口播",
        seedance_prompt="clean plate",
        title_options="酒店经营干货",
        hashtags="#酒店",
    )
    task = _build_video_task(script, 6, production_mode="reference_clone")
    assert task.target_platform == "wechat_channels"
    assert task.export_profile == "wechat_channels_portrait"
    assert (task.export_width, task.export_height) == (1080, 1920)


def test_trusted_asset_uses_seedance_reference_format() -> None:
    human = DigitalHuman(
        name="黄丽的数字人",
        volcengine_asset_status="active",
        volcengine_asset_uri="asset-20260711223536-zgjjn",
    )

    assert VideoPipeline._trusted_asset_uri(human) == "asset://asset-20260711223536-zgjjn"
    item = MediaGenerationClient()._seedance_reference_content_item(
        {"kind": "portrait", "source_url": VideoPipeline._trusted_asset_uri(human)}
    )
    assert item == {
        "type": "image_url",
        "image_url": {"url": "asset://asset-20260711223536-zgjjn"},
        "role": "reference_image",
    }
    continuity = MediaGenerationClient()._seedance_reference_content_item(
        {
            "kind": "image",
            "source_url": "https://media.example.com/generation-inputs/a/continuity.jpg",
            "role": "reference_image",
        }
    )
    assert continuity and continuity["role"] == "reference_image"
    audio = MediaGenerationClient()._seedance_reference_content_item(
        {
            "kind": "audio",
            "source_url": "https://media.example.com/generation-inputs/a/speech.wav",
            "role": "reference_audio",
        }
    )
    assert audio == {
        "type": "audio_url",
        "audio_url": {"url": "https://media.example.com/generation-inputs/a/speech.wav"},
        "role": "reference_audio",
    }


def test_reference_clone_rejects_old_portrait_fallback() -> None:
    old_portrait_only = DigitalHuman(name="旧黄丽头像", portrait_material_id=25)
    try:
        VideoPipeline._require_reference_clone_asset(old_portrait_only)
    except RuntimeError as exc:
        assert "最新火山企业数字资产" in str(exc)
    else:
        raise AssertionError("旧头像不应通过企业数字资产校验")

    latest_asset = DigitalHuman(
        name="黄丽的数字人",
        volcengine_asset_status="active",
        volcengine_asset_uri="asset://asset-20260711223536-zgjjn",
    )
    assert VideoPipeline._require_reference_clone_asset(latest_asset) == "asset://asset-20260711223536-zgjjn"


def test_portrait_export_requests_1080p() -> None:
    payload = MediaGenerationClient()._seedance_request_payload(
        "doubao-seedance-2-0-260128",
        "hotel presenter --ratio 1:1 --dur 5",
        15,
        "douyin_portrait",
    )
    assert payload["resolution"] == "1080p"
    assert payload["ratio"] == "9:16"
    assert payload["duration"] == 15
    assert payload["generate_audio"] is False
    assert payload["watermark"] is False
    assert payload["content"][0]["text"] == "hotel presenter"


def test_visual_quality_drives_one_targeted_retry() -> None:
    local = VideoQualityResult(100, "passed", "基础检查通过", 5, 1080, 1920)
    review = {
        "score": 60,
        "decision": "review",
        "summary": "手指结构异常",
        "issues": ["双手手指畸形", "没有完成回头动作"],
    }
    merged = VideoPipeline._quality_with_visual_review(local, review)
    assert merged.score == 60
    assert merged.status == "review"
    repair = VideoPipeline._visual_repair_instruction(review)
    assert "双手手指畸形" in repair
    assert "没有完成回头动作" in repair


def test_completed_segment_can_be_reused_after_failure() -> None:
    with tempfile.TemporaryDirectory(prefix="segment-resume-") as directory:
        clip = Path(directory) / "segment.mp4"
        clip.write_bytes(b"completed")
        segment = VideoSegment(video_task_id=29, segment_index=1, title="第一段", prompt="same", output_path=str(clip))
        assert VideoPipeline._reusable_segment_output(segment)
        clip.unlink()
        assert not VideoPipeline._reusable_segment_output(segment)


def main() -> None:
    test_he_yiyi_reference_template_is_executable()
    test_trusted_asset_uses_seedance_reference_format()
    test_reference_clone_rejects_old_portrait_fallback()
    test_portrait_export_requests_1080p()
    test_visual_quality_drives_one_targeted_retry()
    test_completed_segment_can_be_reused_after_failure()
    print("he yiyi pipeline smoke ok")


if __name__ == "__main__":
    main()
