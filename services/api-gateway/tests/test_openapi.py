"""The generated /docs must match our hand-written contract (docs/contracts).

If someone changes an endpoint and forgets the contract (or the other way round),
this test fails in CI instead of the frontend finding out later.
"""

from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from app.main import app
from app.schemas import FrameAck

# tests/ -> api-gateway/ -> services/ -> repo root
CONTRACT = Path(__file__).parents[3] / "docs" / "contracts" / "api-gateway.openapi.yaml"

# The complete set of response codes each v0 endpoint must document.
# FastAPI adds 422 (validation error) automatically, so it is ignored below.
EXPECTED_CODES = {
    ("post", "/auth/login"): {"200", "401", "429"},
    ("post", "/auth/refresh"): {"200", "401"},
    ("post", "/sessions"): {"201", "401", "403"},
    ("post", "/sessions/{session_id}/frames"): {
        "202",
        "401",
        "403",
        "404",
        "409",
        "413",
        "415",
        "503",
    },
    ("post", "/sessions/{session_id}/messages"): {"200", "401", "403", "404"},
    ("get", "/clinician/patients"): {"200", "401", "403"},
    ("get", "/clinician/patients/{patient_id}/trend"): {"200", "401", "403"},
    ("patch", "/clinician/review-flags/{flag_id}"): {"200", "401", "403", "422"},
}


def load_contract() -> dict:
    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


def test_responses_match_contract():
    contract = load_contract()
    generated = app.openapi()
    for method, path in EXPECTED_CODES:
        expected = contract["paths"][path][method]["responses"]
        actual = generated["paths"][path][method]["responses"]
        for code, response in expected.items():
            assert code in actual, f"{path}: {code} is in the contract but not in /docs"
            for media_type in response.get("content", {}):
                assert media_type in actual[code].get("content", {}), (
                    f"{path}: {code} should be {media_type}"
                )


def test_security_scheme_name_matches_contract():
    contract = load_contract()
    generated = app.openapi()
    assert set(generated["components"]["securitySchemes"]) == set(
        contract["components"]["securitySchemes"]
    )


def test_response_codes_are_exactly_as_expected():
    contract = load_contract()
    generated = app.openapi()
    for (method, path), expected in EXPECTED_CODES.items():
        in_contract = set(contract["paths"][path][method]["responses"])
        ignored_automatic_422 = set() if "422" in expected else {"422"}
        in_docs = set(generated["paths"][path][method]["responses"]) - ignored_automatic_422
        assert in_contract == expected, f"{path}: contract has {in_contract}"
        assert in_docs == expected, f"{path}: /docs has {in_docs}"


def test_review_flag_validation_error_matches_contract():
    contract = load_contract()
    generated = app.openapi()
    expected = contract["paths"]["/clinician/review-flags/{flag_id}"]["patch"]["responses"]["422"]
    actual = generated["paths"]["/clinician/review-flags/{flag_id}"]["patch"]["responses"]["422"]
    assert expected == actual


def frame_ack_validator() -> Draft202012Validator:
    contract = load_contract()
    response = contract["paths"]["/sessions/{session_id}/frames"]["post"]["responses"][
        "202"
    ]
    schema = response["content"]["application/json"]["schema"]
    return Draft202012Validator({**schema, "components": contract["components"]})


def test_frame_ack_matches_the_published_top2_shape():
    validator = frame_ack_validator()
    ack = FrameAck(visual_status="ok", top2=[("happy", 0.8), ("neutral", 0.1)])
    assert not list(
        validator.iter_errors(ack.model_dump(mode="json", exclude_none=True))
    )


@pytest.mark.parametrize(
    "top2",
    [
        [["happy", 0.8]],  # only one label
        [["happy", 0.7], ["neutral", 0.2], ["sad", 0.1]],  # three labels
        [["happy", 1.2], ["neutral", 0.1]],  # probability above 1
        [["happy", -0.1], ["neutral", 0.1]],  # probability below 0
        [["happy", "high"], ["neutral", 0.1]],  # probability is not a number
        [["message_fragment", 0.5], ["neutral", 0.1]],  # not an emotion label
        [["happy", 0.8, "extra"], ["neutral", 0.1]],  # extra item in a pair
    ],
)
def test_contract_rejects_a_malformed_top2(top2):
    assert list(
        frame_ack_validator().iter_errors({"visual_status": "ok", "top2": top2})
    )
