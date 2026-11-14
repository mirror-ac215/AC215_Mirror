from mirror_load.sse import time_reply


def clock_from(times):
    it = iter(times)
    return lambda: next(it)


def test_times_first_token_and_done():
    lines = ["event: token", 'data: {"text": "Hi"}', "", "event: token", "event: done", "data: {}"]
    timing = time_reply(lines, started=0.0, clock=clock_from([0.25, 1.5]))
    assert timing.first_token_ms == 250.0
    assert timing.complete_ms == 1500.0
    assert timing.outcome == "done"
    assert timing.tokens == 2


def test_crisis_has_no_first_token():
    timing = time_reply(["event: crisis", "data: {}"], started=0.0, clock=clock_from([0.1]))
    assert timing.first_token_ms is None
    assert timing.outcome == "crisis"


def test_stream_that_stops_early_is_incomplete():
    timing = time_reply(["event: token"], started=0.0, clock=clock_from([0.2, 0.3]))
    assert timing.outcome == "incomplete"
    assert timing.complete_ms == 300.0


def test_data_lines_never_count_as_events():
    timing = time_reply(
        ['data: {"text": "event: done"}', "event: done"], started=0.0, clock=clock_from([0.4])
    )
    assert timing.tokens == 0
    assert timing.outcome == "done"
