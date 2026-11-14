import pytest

from mirror_pairwise.split import held_out


def rows(n, prefix="t"):
    return [{"prompt_id": f"{prefix}{i:03d}", "prompt": f"question {prefix}{i}"} for i in range(n)]


def test_same_seed_same_prompts():
    test = rows(50)
    assert held_out(test, set(), 10, seed=7) == held_out(test, set(), 10, seed=7)


def test_training_prompts_are_excluded():
    test = rows(20)
    train = {"question t0", "question t1"}
    picked = held_out(test, train, 10, seed=1)
    assert all(r["prompt"] not in train for r in picked)


def test_training_match_ignores_case_and_spaces():
    test = [{"prompt_id": "x", "prompt": "  Hello there "}, *rows(20)]
    picked = held_out(test, {"hello there"}, 5, seed=2)
    assert all(r["prompt_id"] != "x" for r in picked)


def test_too_few_candidates_is_an_error():
    with pytest.raises(ValueError):
        held_out(rows(5), set(), 10, seed=3)
