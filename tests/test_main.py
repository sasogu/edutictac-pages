from __future__ import annotations

import respx
from fastapi.testclient import TestClient
from httpx import Response

import main

GITEA_ROOT = main.GITEA_ROOT


def _reset_caches() -> None:
    main._content_cache.clear()
    main._branch_cache.clear()


def test_health() -> None:
    with TestClient(main.app) as client:
        resp = client.get("/_health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_head_is_allowed() -> None:
    with TestClient(main.app) as client:
        resp = client.head("/owner/repo", follow_redirects=False)
    assert resp.status_code == 301


def test_redirect_without_trailing_slash() -> None:
    with TestClient(main.app) as client:
        resp = client.get("/owner/repo", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"] == "/owner/repo/"


@respx.mock
def test_serves_index_html_from_main_branch() -> None:
    _reset_caches()
    respx.head(f"{GITEA_ROOT}/owner/repo/raw/branch/pages/index.html").mock(
        return_value=Response(404)
    )
    respx.head(f"{GITEA_ROOT}/owner/repo/raw/branch/main/index.html").mock(
        return_value=Response(200)
    )
    respx.get(f"{GITEA_ROOT}/owner/repo/raw/branch/main/index.html").mock(
        return_value=Response(200, content=b"<h1>Hola</h1>")
    )

    with TestClient(main.app) as client:
        resp = client.get("/owner/repo/")

    assert resp.status_code == 200
    assert resp.content == b"<h1>Hola</h1>"
    assert resp.headers["content-type"].startswith("text/html")


@respx.mock
def test_404_when_no_branch_has_content() -> None:
    _reset_caches()
    for branch in main.BRANCH_CANDIDATES:
        respx.head(f"{GITEA_ROOT}/owner/missing/raw/branch/{branch}/index.html").mock(
            return_value=Response(404)
        )

    with TestClient(main.app) as client:
        resp = client.get("/owner/missing/")

    assert resp.status_code == 404


def test_is_safe_path_rejects_dot_dot_segments() -> None:
    assert main._is_safe_path("assets/style.css") is True
    assert main._is_safe_path("../etc/passwd") is False
    assert main._is_safe_path("assets/../../etc/passwd") is False


def test_path_traversal_is_rejected_over_http() -> None:
    _reset_caches()
    # Percent-encoded so httpx's own URL normalization doesn't collapse the
    # ".." segments before the request ever reaches the app.
    with TestClient(main.app) as client:
        resp = client.get("/owner/repo/%2e%2e/%2e%2e/etc/passwd")

    assert resp.status_code == 400
