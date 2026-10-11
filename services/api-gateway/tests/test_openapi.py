"""The generated /docs must match our hand-written contract (docs/contracts).

If someone changes an endpoint and forgets the contract (or the other way round),
this test fails in CI instead of the frontend finding out later.
"""

from pathlib import Path

import yaml

from app.main import app

# tests/ -> api-gateway/ -> services/ -> repo root
CONTRACT = Path(__file__).parents[3] / "docs" / "contracts" / "api-gateway.openapi.yaml"

# The complete set of response codes each v0 endpoint must document.
# FastAPI adds 422 (validation error) automatically, so it is ignored below.
EXPECTED_CODES = {
    ("post", "/auth/login"): {"200", "401"},
    ("post", "/sessions"): {"201", "401", "403"},
    ("post", "/sessions/{session_id}/frames"): {"202", "401", "403", "404", "409", "413", "415"},
    ("post", "/sessions/{session_id}/messages"): {"200", "401", "403", "404"},
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
        in_docs = set(generated["paths"][path][method]["responses"]) - {"422"}
        assert in_contract == expected, f"{path}: contract has {in_contract}"
        assert in_docs == expected, f"{path}: /docs has {in_docs}"