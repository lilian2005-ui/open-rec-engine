"""P1-2: retries in get_json, on a fake server with no real waiting."""
import json
import logging

import httpx
import pytest

from backend.discovery.http import SourceFetchError, get_json

URL = "https://source.test/jobs"
API_KEY = "secret-key-123"
OK = httpx.Response(200, json={"jobs": ["a"]})


class FakeServer:
    """Plays ``script`` one step per request; the last step repeats. A step is a
    response to return or an exception to raise."""

    def __init__(self, *script):
        self.script = list(script)
        self.requests: list[httpx.Request] = []
        self.waits: list[float] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        step = self.script[min(len(self.requests), len(self.script)) - 1]
        if isinstance(step, Exception):
            raise step
        return step

    def get(self, max_retries: int = 3, **kwargs):
        headers = {"Authorization": f"Bearer {API_KEY}"}
        with httpx.Client(transport=httpx.MockTransport(self), headers=headers) as client:
            return get_json(client, URL, source="himalayas", page=2, max_retries=max_retries,
                            sleep=self.waits.append, **kwargs)

    def fail(self, max_retries: int = 3) -> SourceFetchError:
        with pytest.raises(SourceFetchError) as e:
            self.get(max_retries)
        return e.value


def status(code: int, **headers) -> httpx.Response:
    return httpx.Response(code, headers={k.replace("_", "-"): v for k, v in headers.items()})


# ---------------------------------------------------------------- what is retried

def test_recovers_after_two_failures():
    server = FakeServer(status(503), httpx.ReadTimeout("slow"), OK)
    assert server.get() == {"jobs": ["a"]}
    assert len(server.requests) == 3


def test_always_503_gives_up_after_the_last_retry():
    server = FakeServer(status(503))
    error = server.fail()
    assert len(server.requests) == 4
    assert (error.attempts, error.status, error.error_type) == (4, 503, "http_status")
    assert "503" in str(error)


@pytest.mark.parametrize("step", [status(500), status(429), httpx.ConnectError("refused"),
                                  httpx.ReadError("reset"),
                                  httpx.RemoteProtocolError("disconnected")])
def test_temporary_failures_are_retried(step):
    server = FakeServer(step, OK)
    assert server.get() == {"jobs": ["a"]}
    assert len(server.requests) == 2


def test_last_failure_is_reported_when_it_has_no_status():
    error = FakeServer(status(503), httpx.ConnectTimeout("slow")).fail()
    assert (error.status, error.error_type) == (None, "ConnectTimeout")


# ---------------------------------------------------------------- what is not retried

@pytest.mark.parametrize("code", [301, 400, 401, 403, 404])
def test_permanent_status_is_not_retried(code):
    server = FakeServer(status(code))
    error = server.fail()
    assert len(server.requests) == 1
    assert server.waits == []
    assert (error.attempts, error.status) == (1, code)
    assert str(code) in str(error) and "not retried" in str(error)


@pytest.mark.parametrize("body", [b"<html>not json</html>", b"\xff\xfe"])
def test_invalid_body_is_not_retried(body):
    server = FakeServer(status(503), httpx.Response(200, content=body))
    error = server.fail()
    assert len(server.requests) == 2
    assert (error.error_type, error.status, error.attempts) == ("invalid_body", 200, 2)


def test_other_transport_error_is_not_retried():
    server = FakeServer(httpx.UnsupportedProtocol("bad scheme"))
    error = server.fail()
    assert len(server.requests) == 1
    assert (error.error_type, error.status) == ("UnsupportedProtocol", None)


# ---------------------------------------------------------------- retry rules

def test_waits_double_before_each_retry():
    server = FakeServer(status(503))
    server.fail()
    assert server.waits == [1, 2, 4]


def test_no_retries_means_one_request():
    server = FakeServer(status(503))
    assert server.fail(max_retries=0).attempts == 1
    assert len(server.requests) == 1
    assert server.waits == []


@pytest.mark.parametrize("value, wait", [("5", 5), ("120", 60), ("60", 60), ("0", 0),
                                         ("soon", 1), ("-5", 1),
                                         ("Wed, 21 Oct 2026 07:28:00 GMT", 1)])
def test_429_follows_retry_after(value, wait):
    server = FakeServer(status(429, Retry_After=value), OK)
    server.get()
    assert server.waits == [wait]


def test_429_without_retry_after_uses_the_normal_wait():
    server = FakeServer(status(429), status(429), OK)
    server.get()
    assert server.waits == [1, 2]


def test_retry_after_only_counts_on_429():
    server = FakeServer(status(503, Retry_After="30"), OK)
    server.get()
    assert server.waits == [1]


def test_timeout_and_params_reach_the_request():
    server = FakeServer(OK)
    server.get(params={"limit": 20}, timeout=7.0)
    assert server.requests[0].url.params["limit"] == "20"
    assert server.requests[0].extensions["timeout"]["read"] == 7.0


def test_timeout_defaults_to_10_seconds():
    server = FakeServer(OK)
    server.get()
    assert server.requests[0].extensions["timeout"]["read"] == 10.0


# ---------------------------------------------------------------- the final error

def test_to_dict_is_json_safe_and_complete():
    error = FakeServer(status(503)).fail()
    assert json.loads(json.dumps(error.to_dict())) == {
        "stage": "discovery",
        "source": "himalayas",
        "page": 2,
        "error_type": "http_status",
        "status": 503,
        "attempts": 4,
        "message": "HTTP 503 after 4 attempts",
    }


# ---------------------------------------------------------------- logging and secrets

def test_logs_one_line_per_retry(caplog):
    server = FakeServer(status(503), httpx.ReadTimeout("slow"), OK)
    with caplog.at_level(logging.WARNING, logger="backend.discovery.http"):
        server.get()
    assert [r.getMessage() for r in caplog.records] == [
        "himalayas: page 2 attempt 1 failed (HTTP 503), retrying in 1 s",
        "himalayas: page 2 attempt 2 failed (ReadTimeout), retrying in 2 s",
    ]


@pytest.mark.parametrize("final", [status(401), status(503), httpx.ReadTimeout("slow"),
                                   httpx.UnsupportedProtocol("bad scheme"),
                                   httpx.Response(200, content=b"not json")])
def test_api_key_never_appears(final, caplog):
    server = FakeServer(status(503), final)
    with caplog.at_level(logging.DEBUG):
        error = server.fail()
    assert server.requests[0].headers["Authorization"] == f"Bearer {API_KEY}"
    assert API_KEY not in str(error)
    assert API_KEY not in json.dumps(error.to_dict())
    assert API_KEY not in caplog.text


def test_key_in_a_url_stays_out_of_our_log_and_error(caplog):
    server = FakeServer(status(503))
    with caplog.at_level(logging.DEBUG, logger="backend.discovery.http"):
        with pytest.raises(SourceFetchError) as e:
            server.get(params={"api_key": API_KEY})
    assert API_KEY in str(server.requests[0].url)
    assert API_KEY not in str(e.value)
    assert API_KEY not in json.dumps(e.value.to_dict())
    assert API_KEY not in caplog.text
