import hashlib
import socket

import pytest

from slice_and_dice.api_client import ApiClient, auth_cookie


def test_auth_cookie_is_sha256_of_password_and_nonce():
    assert auth_cookie("pw", 42) == hashlib.sha256(b"pw-42").hexdigest()


def test_build_query_signs_and_encodes(client):
    query = client.build_query({"value": "a b&c", "skip": None, "n": 3})
    assert "value=a%20b%26c" in query
    assert "n=3" in query
    assert "skip" not in query
    assert "nonce=" in query
    assert "cookie=" in query


def test_call_returns_decoded_json(client, server):
    assert client.call("/healthcheck", {"cid": 7}) == {"status": "ok", "started": 1}
    assert server.last("/healthcheck")["cid"] == "7"
    assert client.last_request.startswith("/healthcheck?cid=7&")


def test_wrong_password_is_rejected_by_the_server(server):
    client = ApiClient("127.0.0.1", server.port, "wrong")
    assert client.call("/healthcheck") == {"status": "unauthorized"}


def test_connection_is_reused(client, server):
    client.call("/healthcheck")
    connection = client._connection
    client.call("/healthcheck")
    assert client._connection is connection


def test_http_errors_yield_none(client, server, caplog):
    server.handlers["/boom"] = lambda params: (500, {"error": "kaput"})
    assert client.call("/boom") is None
    assert "500" in caplog.text


def test_non_json_responses_yield_none(client, server, caplog):
    server.handlers["/text"] = lambda params: (200, b"<html>")
    assert client.call("/text") is None
    assert "not JSON" in caplog.text


def test_non_object_responses_yield_none(client, server):
    server.handlers["/list"] = lambda params: [1, 2]
    assert client.call("/list") is None


def test_unreachable_server_yields_none(caplog):
    with socket.socket() as probe:  # find a port nobody listens on
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    client = ApiClient("127.0.0.1", port, "pw")
    assert client.call("/healthcheck", timeout=2) is None
    assert "failed" in caplog.text


def test_set_address_reconnects(client, server):
    client.call("/healthcheck")
    client.set_address("127.0.0.1", server.port + 1)
    assert client._connection is None
    assert client.address == f"127.0.0.1:{server.port + 1}"


@pytest.mark.parametrize("endpoint", ["/scope/narrow", "/scope/breakdown"])
def test_requests_reach_the_endpoint(client, server, endpoint):
    client.call(endpoint, {"scope_id": 1, "startfrom": 0, "limit": 1})
    assert server.endpoints()[-1] == endpoint
