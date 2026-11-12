from mirror_pairwise.pairwise import length_report, sentence_count


def test_counts_sentences():
    assert sentence_count("I hear you. That sounds hard.") == 2
    assert sentence_count("Are you safe right now?") == 1
    assert sentence_count("") == 0


def test_one_blunt_sentence_counts_as_one():
    assert sentence_count("Try harder.") == 1


def test_length_report_per_model():
    rows = [
        {"model": "base", "reply": "One. Two. Three."},
        {"model": "base", "reply": "Only one."},
        {"model": "lora", "reply": "Short."},
    ]
    report = length_report(rows)
    assert report["base"]["median_sentences"] == 2
    assert report["base"]["under_2_share"] == 0.5
    assert report["lora"]["median_sentences"] == 1
    assert report["lora"]["under_2_share"] == 1.0
