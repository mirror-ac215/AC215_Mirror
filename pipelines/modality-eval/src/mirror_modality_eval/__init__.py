"""M4-09 modality comparison: what the face reading and the text reading each add."""

# Mirror's four labels with enough rows to score (README: fear 40 and disgust 2 are too rare).
SCORED = ("neutral", "joy", "anger", "sadness")

# The gateway's own mapping (services/api-gateway/app/fusion.py, TEXT_TO_FACE), inverted.
FACE_TO_MIRROR = {"angry": "anger", "happy": "joy", "sad": "sadness"}
MIN_TEXT_PROB = 0.40  # same bar as the text reading in the prompt (M3-08)
