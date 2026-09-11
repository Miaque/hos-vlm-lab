import json
from pathlib import Path

from hos_vlm_lab.models import parse_prompt


def test_versioned_seed_contract():
    path = Path(__file__).parents[1] / "src/hos_vlm_lab/default-prompt.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    identities = parse_prompt(path.read_text(encoding="utf-8"))
    assert len(identities) == len(data["events"])
    assert data["source"]["seed_commit"] == "755f31a"
    assert all(
        set(e) == {"code", "name", "match", "exclude", "uncertain"}
        for e in data["events"]
    )
    assert set(data["output"]["events"][0]) == {
        "canonical_event_code",
        "confidence",
        "evidence",
    }
