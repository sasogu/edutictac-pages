"""EduTicTac Pages: static site hosting from public Forgejo repos.

Serves the contents of public repositories hosted at a Forgejo instance
(git.edutictac.es) as static websites, addressed by path instead of by
wildcard subdomain: ``pages.edutictac.es/<owner>/<repo>/<path>``.

No Forgejo credentials are used anywhere in this service. It only ever
proxies what Forgejo's raw-content endpoint already serves anonymously,
which means it can never leak content from a private repository.
"""

from __future__ import annotations

import mimetypes
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse, RedirectResponse

GITEA_ROOT = os.environ.get("PAGES_GITEA_ROOT", "https://git.edutictac.es").rstrip("/")
BRANCH_CANDIDATES = [
    b.strip()
    for b in os.environ.get("PAGES_BRANCH_CANDIDATES", "pages,main,master").split(",")
    if b.strip()
]
CACHE_TTL_SECONDS = float(os.environ.get("PAGES_CACHE_TTL_SECONDS", "60"))
BRANCH_CACHE_TTL_SECONDS = float(os.environ.get("PAGES_BRANCH_CACHE_TTL_SECONDS", "300"))
CACHE_MAX_ENTRIES = int(os.environ.get("PAGES_CACHE_MAX_ENTRIES", "500"))
MAX_FILE_BYTES = int(os.environ.get("PAGES_MAX_FILE_BYTES", str(20 * 1024 * 1024)))
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("PAGES_REQUEST_TIMEOUT_SECONDS", "5"))
USER_AGENT = "edutictac-pages/1.0 (+https://pages.edutictac.es)"

@asynccontextmanager
async def _lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(headers={"User-Agent": USER_AGENT})
    yield
    await app.state.http_client.aclose()


app = FastAPI(title="EduTicTac Pages", lifespan=_lifespan)


@dataclass
class CacheEntry:
    status: int
    content: bytes
    content_type: str
    expires_at: float


_content_cache: dict[str, CacheEntry] = {}
_branch_cache: dict[str, tuple[str | None, float]] = {}


def _cache_get(cache: dict[str, CacheEntry], key: str) -> CacheEntry | None:
    entry = cache.get(key)
    if entry is None:
        return None
    if entry.expires_at < time.monotonic():
        cache.pop(key, None)
        return None
    return entry


def _cache_set(cache: dict, key: str, value) -> None:
    if len(cache) >= CACHE_MAX_ENTRIES:
        oldest_key = next(iter(cache))
        cache.pop(oldest_key, None)
    cache[key] = value


def _is_safe_path(path: str) -> bool:
    segments = path.split("/")
    return ".." not in segments and "\x00" not in path


def _guess_content_type(path: str) -> str:
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"


async def _resolve_branch(client: httpx.AsyncClient, owner: str, repo: str) -> str | None:
    cache_key = f"{owner}/{repo}"
    cached = _branch_cache.get(cache_key)
    if cached is not None and cached[1] >= time.monotonic():
        return cached[0]

    resolved: str | None = None
    for branch in BRANCH_CANDIDATES:
        url = f"{GITEA_ROOT}/{owner}/{repo}/raw/branch/{branch}/index.html"
        try:
            resp = await client.head(url, timeout=REQUEST_TIMEOUT_SECONDS)
        except httpx.HTTPError:
            continue
        if resp.status_code == 200:
            resolved = branch
            break

    _branch_cache[cache_key] = (resolved, time.monotonic() + BRANCH_CACHE_TTL_SECONDS)
    return resolved


async def _fetch_raw(client: httpx.AsyncClient, owner: str, repo: str, branch: str, path: str) -> tuple[int, bytes]:
    url = f"{GITEA_ROOT}/{owner}/{repo}/raw/branch/{branch}/{path}"
    try:
        resp = await client.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    except httpx.HTTPError:
        return 502, b""
    if resp.status_code != 200:
        return resp.status_code, b""
    content = resp.content[: MAX_FILE_BYTES + 1]
    if len(content) > MAX_FILE_BYTES:
        return 413, b""
    return 200, content


def _get_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


@app.get("/_health")
async def health() -> dict:
    return {"status": "ok"}


@app.api_route("/{owner}/{repo}", methods=["GET", "HEAD"])
async def redirect_to_trailing_slash(owner: str, repo: str) -> RedirectResponse:
    return RedirectResponse(url=f"/{owner}/{repo}/", status_code=301)


@app.api_route("/{owner}/{repo}/{path:path}", methods=["GET", "HEAD"])
async def serve_page(owner: str, repo: str, path: str, request: Request) -> Response:
    if path == "" or path.endswith("/"):
        path = f"{path}index.html"

    if not _is_safe_path(path):
        return PlainTextResponse("400 Bad Request", status_code=400)

    cache_key = f"{owner}/{repo}@{path}"
    cached = _cache_get(_content_cache, cache_key)
    if cached is not None:
        if cached.status != 200:
            return PlainTextResponse("404 Not Found", status_code=404)
        return Response(content=cached.content, media_type=cached.content_type)

    client = _get_client(request)
    branch = await _resolve_branch(client, owner, repo)
    if branch is None:
        _cache_set(
            _content_cache,
            cache_key,
            CacheEntry(404, b"", "text/plain", time.monotonic() + CACHE_TTL_SECONDS),
        )
        return PlainTextResponse("404 Not Found", status_code=404)

    status, content = await _fetch_raw(client, owner, repo, branch, path)
    content_type = _guess_content_type(path)
    _cache_set(
        _content_cache,
        cache_key,
        CacheEntry(status, content, content_type, time.monotonic() + CACHE_TTL_SECONDS),
    )
    if status != 200:
        return PlainTextResponse("404 Not Found", status_code=404)
    return Response(content=content, media_type=content_type)
