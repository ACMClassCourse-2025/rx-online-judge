import hmac
import json
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .auth import COOKIE_NAME, password_hash, public_user, token_hash, verify_password
from .catalog import Catalog, load_languages
from .config import Settings
from .db import Database, QueueFull
from .http_limits import RequestBoundary
from .repositories import RepositoryError, validate_repository
from .scoring import baseline_status, leaderboard, score_submission


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=256)


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, max_length=80)
    language: str = Field(min_length=1, max_length=40)
    repository_url: str = Field(min_length=1, max_length=500)
    git_ref: str = Field(default="HEAD", min_length=1, max_length=200)
    suite: Literal["semantic", "ir", "codegen", "optimization"]


def create_app(settings: Settings | None = None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        settings.uploads_dir.mkdir(parents=True, exist_ok=True)
        app.state.db = Database(settings.db_path)
        app.state.catalog = Catalog(settings.tests_dir)
        app.state.languages = load_languages(settings.languages_file)
        yield

    app = FastAPI(
        title="Rx Online Judge", version="0.2.0", lifespan=lifespan, docs_url=None, redoc_url=None
    )
    app.add_middleware(RequestBoundary, max_body_bytes=8192)

    def authenticate(request: Request):
        token = request.cookies.get(COOKIE_NAME, "")
        user = app.state.db.session(token_hash(token)) if token else None
        if not user:
            raise HTTPException(401, "Sign in with your judge account")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            csrf = request.headers.get("X-CSRF-Token", "")
            if not hmac.compare_digest(csrf.encode(), user["csrf_token"].encode()):
                raise HTTPException(403, "Invalid CSRF token; reload the page and try again")
        return user

    Authenticated = Annotated[dict, Depends(authenticate)]

    def visibility(user):
        return None if user["is_admin"] else user["id"]

    @app.middleware("http")
    async def security_headers(request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    {"detail": "Cross-origin requests are not allowed"}, status_code=403
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/auth/login")
    def login(body: Login, request: Request, response: Response):
        db = app.state.db
        name = body.username.strip().lower()
        address = request.client.host if request.client else "unknown"
        attempt = db.reserve_login(name, address)
        if attempt is None:
            raise HTTPException(429, "Too many login attempts; try again in five minutes")
        user = db.user_by_name(name)
        valid = verify_password(body.password, user["password_hash"] if user else None)
        if not valid or not user["active"]:
            raise HTTPException(401, "Incorrect username or password")
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        if not db.start_session(
            token_hash(token),
            user["id"],
            csrf,
            settings.session_seconds,
            attempt,
            user["password_hash"],
        ):
            raise HTTPException(401, "Account changed during sign-in; try again")
        response.set_cookie(
            COOKIE_NAME,
            token,
            max_age=settings.session_seconds,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="strict",
            path="/",
        )
        return {"user": public_user(user), "csrf_token": csrf}

    @app.get("/api/auth/me")
    def me(user: Authenticated):
        return {"user": public_user(user), "csrf_token": user["csrf_token"]}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response, user: Authenticated):
        app.state.db.end_session(token_hash(request.cookies[COOKIE_NAME]))
        response.delete_cookie(
            COOKIE_NAME, httponly=True, secure=settings.secure_cookies, samesite="strict", path="/"
        )
        return {"ok": True}

    @app.post("/api/auth/password")
    def change_password(body: PasswordChange, response: Response, user: Authenticated):
        account = app.state.db.user_by_name(user["username"])
        attempt = app.state.db.reserve_login(user["username"], "password-change:" + user["id"])
        if attempt is None:
            raise HTTPException(429, "Too many password attempts; try again in five minutes")
        if not verify_password(body.current_password, account["password_hash"]):
            raise HTTPException(400, "Current password is incorrect")
        app.state.db.reset_password(user["id"], password_hash(body.new_password))
        response.delete_cookie(COOKIE_NAME, path="/")
        return {"ok": True, "message": "Password changed. Sign in again."}

    @app.get("/api/health")
    def health(user: Authenticated):
        result = app.state.db.health()
        if not user["is_admin"]:
            result["workers"] = [{"connected": True} for _ in result["workers"]]
        return result

    @app.get("/api/catalog")
    def catalog(user: Authenticated):
        return {**app.state.catalog.public(), "git_hosts": list(settings.git_hosts)}

    @app.get("/api/catalog/summary")
    def catalog_summary():
        catalog = app.state.catalog.public()
        return {"total": catalog["total"], "stages": catalog["stages"]}

    @app.get("/api/languages")
    def languages(user: Authenticated):
        return [
            {k: v for k, v in entry.items() if k != "image"}
            for entry in app.state.languages.values()
        ]

    @app.get("/api/submissions")
    def submissions(
        user: Authenticated,
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        return app.state.db.listing(limit, offset, visibility(user))

    @app.get("/api/leaderboard")
    def rankings(user: Authenticated):
        return leaderboard(app.state.db, app.state.catalog, user)

    @app.get("/api/submissions/{submission_id}")
    def submission(submission_id: str, user: Authenticated):
        result = app.state.db.get(submission_id, owner_id=visibility(user))
        if result is None:
            raise HTTPException(404, "Submission not found")
        baseline = app.state.db.baseline()
        result["optimization_score"] = score_submission(result, baseline, app.state.catalog)
        result["optimization_baseline_status"] = baseline_status(baseline, app.state.catalog)
        return result

    @app.post("/api/submissions/{submission_id}/cancel")
    def cancel(submission_id: str, user: Authenticated):
        if app.state.db.get(submission_id, details=False, owner_id=visibility(user)) is None:
            raise HTTPException(404, "Submission not found")
        app.state.db.cancel(submission_id)
        return app.state.db.get(submission_id, owner_id=visibility(user))

    @app.post("/api/submissions", status_code=202)
    def submit(body: Submission, user: Authenticated):
        if body.language not in app.state.languages:
            raise HTTPException(422, "Unknown compiler language")
        try:
            validate_repository(body.repository_url, body.git_ref, settings.git_hosts)
            cases = app.state.catalog.select_suite(body.suite)
        except (ValueError, RepositoryError) as exc:
            raise HTTPException(422, str(exc)) from exc
        submission_id = uuid.uuid4().hex
        try:
            app.state.db.enqueue(
                {
                    "id": submission_id,
                    "name": body.name or f"Run {submission_id[:8]}",
                    "language": body.language,
                    "stage": body.suite,
                    "filter": "",
                    "catalog_version": app.state.catalog.version,
                    "case_ids": json.dumps([case.id for case in cases]),
                    "created_at": time.time(),
                    "total": len(cases),
                    "owner_id": user["id"],
                    "repository_url": body.repository_url,
                    "git_ref": body.git_ref,
                },
                settings.max_pending,
            )
        except QueueFull as exc:
            raise HTTPException(429, str(exc)) from exc
        return app.state.db.get(submission_id, owner_id=visibility(user))

    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(static / "index.html")

    return app


app = create_app()
