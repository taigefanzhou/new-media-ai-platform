from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.ai_clients import ScriptGenerator
from app.services.video_skills import video_skill_manifest
from app.api.modules.system import list_video_production_skills


def main() -> None:
    skills = {item["key"]: item for item in video_skill_manifest()}
    editor = skills["jianying_professional_editing"]
    reference_analysis = skills["reference_video_analysis"]
    storyboard = skills["storyboard_generation"]
    assert "J/L Cut" in " ".join(editor["workflow_rules"])
    assert "证据" in " ".join(reference_analysis["workflow_rules"])
    assert "最多安排一个主动作" in " ".join(storyboard["workflow_rules"])
    assert "专业剪辑" in list_video_production_skills()["pipeline"]

    plan = ScriptGenerator()._normalize_storyboard_plan(
        [
            {
                "start_second": 0,
                "end_second": 3,
                "shot_type": "close_up",
                "visual": "智能门锁亮起",
                "caption_emphasis": ["门锁"],
            }
        ],
        "",
        10,
    )
    shot = plan[0]
    assert shot["transition"] == "hard_cut"
    assert shot["edit_intent"]
    assert shot["caption_emphasis"] == ["门锁"]
    assert shot["color_note"]

    skill_root = ROOT.parent / "skills" / "jianying-professional-editor"
    assert (skill_root / "SKILL.md").exists()
    assert (skill_root / "references" / "editing-rules.md").exists()
    assert (ROOT.parent / "skills" / "reference-video-deep-analysis" / "SKILL.md").exists()

    print("professional editing skill smoke ok")


if __name__ == "__main__":
    main()
