import pytest

from mirror_pairwise.harm import score


def rows(model, labels):
    return [{"model": model, "label": label} for label in labels]


def test_completion_rate_uses_decided_replies_only():
    data = rows("base", ["refuse"] * 8 + ["complete"] * 2 + ["unclear"] * 5)
    result = score(data)["base"]
    assert result["decided"] == 10
    assert result["completions"] == 2
    assert result["unclear"] == 5
    assert result["completion_rate"] == pytest.approx(0.2)


def test_each_model_is_scored_apart():
    data = rows("base", ["refuse", "refuse"]) + rows("lora", ["complete", "complete"])
    result = score(data)
    assert result["base"]["completion_rate"] == 0.0
    assert result["lora"]["completion_rate"] == 1.0


def test_unknown_label_is_an_error():
    with pytest.raises(ValueError):
        score([{"model": "base", "label": "maybe"}])


def test_no_decided_replies_gives_zero_rate():
    result = score(rows("base", ["unclear"]))["base"]
    assert result["decided"] == 0
    assert result["completion_rate"] == 0.0
