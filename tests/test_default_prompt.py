import json
from pathlib import Path

from hos_vlm_lab.models import parse_prompt


def test_versioned_seed_contract():
    path = Path(__file__).parents[1] / "src/hos_vlm_lab/default-prompt.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    identities = parse_prompt(path.read_text(encoding="utf-8"))
    assert len(identities) == len(data["events"])
    assert len(identities) == 22
    assert data["source"]["template"] == "default_visual_scene_template/default"
    assert data["source"]["prompt_version"] == "2026-09-10.v1"
    assert "city.order.animal_detected" in identities
    assert "city.traffic.vehicle_detected" not in identities
    assert all(
        set(e) == {"code", "name", "match", "exclude", "uncertain"}
        for e in data["events"]
    )
    assert set(data["output"]["events"][0]) == {
        "canonical_event_code",
        "confidence",
        "evidence",
    }
