"""Tests for the fetch shim."""

from fetcher import client


def test_success_on_first_attempt_does_not_sleep():
    sends: list[str] = []
    sleeps: list[float] = []
    out = client.fetch(lambda url: (sends.append(url), "body")[1], "http://x/1",
                       sleep=sleeps.append)
    assert out == "body"
    assert sends == ["http://x/1"] and sleeps == []


def test_transient_responses_are_retried_with_backoff():
    responses = iter([client.RETRY_MARKER, client.RETRY_MARKER, "payload"])
    sends: list[str] = []
    sleeps: list[float] = []

    def send(url: str) -> str:
        sends.append(url)
        return next(responses)

    out = client.fetch(send, "http://x/2", sleep=sleeps.append)
    assert out == "payload"
    assert sends == ["http://x/2"] * 3
    assert sleeps == list(client.DELAYS_S)
