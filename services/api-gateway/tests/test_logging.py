import json
import logging

from app.logging_config import JsonFormatter


def test_json_formatter_includes_request_metadata() -> None:
    record = logging.LogRecord(
        name="mirror",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request_completed",
        args=(),
        exc_info=None,
    )
    record.path = "/health"
    record.status_code = 200

    payload = json.loads(JsonFormatter().format(record))

    assert payload["path"] == "/health"
    assert payload["status_code"] == 200
