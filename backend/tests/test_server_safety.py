"""The small things a live server needs (13 Nov): safety headers, the API docs page
off unless turned on, and server errors written to a log without any ID number."""

import logging

import pytest
from fastapi.testclient import TestClient

from app.config import config
from app.main import app
from tests.helpers import ID_NUMBER, PASSWORD


@pytest.fixture
def a_route_that_breaks():
    """An address that fails like a bug would, added for one test and then taken away."""

    async def breaks(request_body: dict) -> dict:
        raise RuntimeError("a bug in our code")

    app.add_api_route("/api/test-only/breaks", breaks, methods=["POST"])
    yield "/api/test-only/breaks"
    app.router.routes = [route for route in app.router.routes if getattr(route, "path", "") != "/api/test-only/breaks"]


def test_every_answer_has_the_safety_headers(client):
    headers = client.get("/api/pickup-days").headers

    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "same-origin"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert "script-src 'self'" in headers["Content-Security-Policy"]
    assert headers["Permissions-Policy"].startswith("camera=()")
    # Over https (the tests pretend to be), browsers are told to keep using https.
    assert headers["Strict-Transport-Security"] == "max-age=31536000"


def test_an_error_answer_has_them_too(client):
    # A refusal from the rules, not a server error: the same headers.
    answer = client.get("/api/my-booking")

    assert answer.status_code == 401
    assert answer.headers["X-Frame-Options"] == "DENY"


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_the_api_docs_are_off_unless_turned_on(client, monkeypatch, path):
    monkeypatch.setattr(config, "api_docs", False)
    assert client.get(path).status_code == 404

    monkeypatch.setattr(config, "api_docs", True)
    assert client.get(path).status_code == 200


def test_a_server_error_says_so_in_words_and_is_logged_without_the_body(db, caplog, a_route_that_breaks):
    caplog.set_level(logging.ERROR, logger="app.errors")
    # raise_server_exceptions=False: answer the way the real server would, instead of
    # passing the error on to the test.
    browser = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)

    answer = browser.post(a_route_that_breaks, json={"id_number": ID_NUMBER, "password": PASSWORD})

    assert answer.status_code == 500
    assert answer.json() == {"detail": "Something went wrong on our side. Please try again in a minute."}
    assert "RuntimeError: a bug in our code" not in answer.text
    [line] = [record for record in caplog.records if record.name == "app.errors"]
    assert line.getMessage() == f"POST {a_route_that_breaks} failed"
    assert "RuntimeError: a bug in our code" in caplog.text  # the traceback, for whoever fixes it
    # P10: nothing that was sent ends up in the log or the answer.
    assert ID_NUMBER not in caplog.text and ID_NUMBER not in answer.text
    assert PASSWORD not in caplog.text


def test_the_error_log_never_drops_a_line_when_it_cant_start_a_new_file(tmp_path, monkeypatch):
    # Windows: another server process has the file open, so it can't be renamed.
    from app.main import ErrorLogFile

    log_file = tmp_path / "errors.log"
    handler = ErrorLogFile(log_file, maxBytes=100, backupCount=5, encoding="utf-8")

    def in_use(source, dest):
        raise PermissionError("The process cannot access the file because it is being used by another process")

    monkeypatch.setattr(handler, "rotate", in_use)
    logger = logging.getLogger("test.error_log")
    logger.addHandler(handler)
    logger.propagate = False
    try:
        for n in range(5):
            logger.error("POST /api/bookings failed, number %d, padded to pass 100 bytes quickly" + "." * 40, n)
    finally:
        logger.removeHandler(handler)
        handler.close()

    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert [line.split("number ")[1][0] for line in lines] == ["0", "1", "2", "3", "4"]
