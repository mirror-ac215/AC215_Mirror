import pytest

from mirror_pairwise.harm import cohen_kappa


def test_perfect_agreement_is_one():
    labels = ["refuse", "complete", "refuse", "unclear"]
    assert cohen_kappa(labels, labels)["kappa"] == pytest.approx(1.0)


def test_textbook_example():
    # 20 replies, 2 labels: observed 0.70, expected 0.50, kappa 0.40
    a = ["complete"] * 10 + ["refuse"] * 10
    b = ["complete"] * 7 + ["refuse"] * 3 + ["complete"] * 3 + ["refuse"] * 7
    result = cohen_kappa(a, b)
    assert result["observed_agreement"] == pytest.approx(0.70)
    assert result["kappa"] == pytest.approx(0.40)


def test_agreement_at_chance_is_zero():
    a = ["complete", "refuse", "complete", "refuse"]
    b = ["complete", "complete", "refuse", "refuse"]
    assert cohen_kappa(a, b)["kappa"] == pytest.approx(0.0)


def test_all_one_label_both_raters_is_one():
    assert cohen_kappa(["refuse"] * 5, ["refuse"] * 5)["kappa"] == pytest.approx(1.0)


def test_mismatched_lengths_is_an_error():
    with pytest.raises(ValueError):
        cohen_kappa(["refuse"], ["refuse", "complete"])
