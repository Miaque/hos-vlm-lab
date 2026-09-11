import json

import pytest
from pydantic import ValidationError

from hos_vlm_lab.models import Controls, RoundRequest, parse_events, parse_prompt


PROMPT = json.dumps({"events": [{"code": "person", "name": "人员"}]})


def test_prompt_keeps_explicit_identity():
    assert parse_prompt(PROMPT) == {"person": "人员"}
    with pytest.raises(ValueError):
        parse_prompt('{"events": []}')


@pytest.mark.parametrize(
    "raw",
    [
        "{}",
        "not json",
        '{"events":[{"canonical_event_code":"unknown","confidence":0.5,"evidence":"人"}]}',
        '{"events":[{"canonical_event_code":"person","confidence":true,"evidence":"人"}]}',
        '{"events":[{"canonical_event_code":"person","confidence":NaN,"evidence":"人"}]}',
        '{"events":[{"canonical_event_code":"person","confidence":0.5,"evidence":" "}]}',
    ],
)
def test_invalid_response_is_not_empty(raw):
    with pytest.raises(ValueError):
        parse_events(raw, {"person": "人员"})


def test_valid_empty_and_event():
    assert parse_events('{"events":[]}', {"person": "人员"}) == []
    event = {
        "canonical_event_code": "person",
        "confidence": 0.8,
        "evidence": "左侧可见人员",
    }
    assert parse_events(json.dumps({"events": [event]}), {"person": "人员"}) == [event]
    with pytest.raises(ValueError):
        parse_events(json.dumps({"events": [event, event]}), {"person": "人员"})


@pytest.mark.parametrize(
    "changes",
    [
        {"thinking_budget": 1},
        {"max_tokens": True},
        {"thinking": True},
        {"temperature": float("inf")},
    ],
)
def test_controls_reject_invalid(changes):
    data = dict(thinking=False, thinking_budget=None, max_tokens=1000, temperature=0.6)
    with pytest.raises(ValidationError):
        Controls(**(data | changes))


@pytest.mark.parametrize("size,valid", [(0, False), (1, True), (20, True), (21, False)])
def test_round_image_limit(size, valid):
    data = dict(
        request_id="r1",
        image_ids=[str(i) for i in range(size)],
        model_keys=["one"],
        prompt_text=PROMPT,
        controls=dict(thinking=False, max_tokens=1000, temperature=0.6),
    )
    if valid:
        assert len(RoundRequest(**data).image_ids) == size
    else:
        with pytest.raises(ValidationError):
            RoundRequest(**data)
