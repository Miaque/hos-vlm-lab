from hos_vlm_lab.gateway import calculate_cost, normalize_usage


PRICE = {
    "currency": "CNY",
    "source": "test",
    "valid_from": "2026-01-01T00:00:00+00:00",
    "valid_until": "2027-01-01T00:00:00+00:00",
    "input_per_million": "2",
    "output_per_million": "8",
    "cache_read_per_million": "0.2",
}


def test_reasoning_not_counted_twice_and_decimal():
    usage = normalize_usage(
        {
            "prompt_tokens": 1000,
            "completion_tokens": 200,
            "completion_tokens_details": {"reasoning_tokens": 150},
            "prompt_tokens_details": {"cached_tokens": 100},
        }
    )
    assert usage == {"input": 1000, "output": 200, "reasoning": 150, "cache_read": 100}
    assert calculate_cost(usage, PRICE, "2026-09-11T00:00:00+00:00") == "0.00342"


def test_unknown_zero_and_period():
    assert (
        calculate_cost(normalize_usage(None), PRICE, "2026-09-11T00:00:00+00:00")
        is None
    )
    zero = {"input": 0, "output": 0, "cache_read": 0, "reasoning": 0}
    assert calculate_cost(zero, PRICE, "2026-09-11T00:00:00+00:00") == "0"
    assert calculate_cost(zero, PRICE, "2027-09-11T00:00:00+00:00") is None
    assert (
        calculate_cost(zero | {"cache_read": None}, PRICE, "2026-09-11T00:00:00+00:00")
        is None
    )
    assert normalize_usage({"prompt_tokens": True})["input"] is None
