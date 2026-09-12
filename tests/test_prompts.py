import json
from pathlib import Path

from hos_vlm_lab.prompts import render_prompt


def test_render_preserves_rules_and_custom_fields_without_provenance():
    data = json.loads((Path(__file__).parents[1] / "src/hos_vlm_lab/default-prompt.json").read_text(encoding="utf-8"))
    data["scene_context"] = {"region": "用户指定区域"}
    data["events"][0]["custom_rule"] = "额外判定条件"
    text = render_prompt(json.dumps(data, ensure_ascii=False))
    assert text.startswith("# 任务")
    for event in data["events"]:
        for value in event.values():
            assert value in text
    assert all(rule in text for rule in data["instructions"])
    assert "用户指定区域" in text
    assert data["source"]["source_commit"] not in text
    assert "# 输出" in text
    assert '"canonical_event_code"' in text


def test_minimal_and_structured_custom_values_are_retained():
    text = render_prompt('{"events":[{"code":"a","name":"事件","match":["规则一","规则二"]}],"instructions":"只看左侧"}')
    assert "规则一" in text and "规则二" in text
    assert "只看左侧" in text
    assert '{"events":[]}' in text
