import sqlite3
from dataclasses import replace

from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from rx_oj.api import create_app
from rx_oj.auth import COOKIE_NAME, password_hash, token_hash, username, verify_password
from rx_oj.db import Database


def test_login_logout_cookie_flags_and_no_registration(settings, accounts, sign_in):
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/auth/register", json={}).status_code == 404
        response = client.post("/api/auth/login", json={"username": "alice", "password": "wrong"})
        assert response.status_code == 401
        response = client.post("/api/auth/login", json={"username": "missing", "password": "wrong"})
        assert (
            response.status_code == 401
            and response.json()["detail"] == "Incorrect username or password"
        )
        sign_in(client, "ALICE")
        cookie = client.cookies.get(COOKIE_NAME)
        with Database(settings.db_path).connect() as conn:
            stored = conn.execute("SELECT token_hash FROM sessions").fetchone()[0]
        assert stored == token_hash(cookie) and stored != cookie
        assert client.get("/api/auth/me").json()["user"]["username"] == "alice"
        assert client.post("/api/auth/logout").status_code == 200
        assert client.get("/api/auth/me").status_code == 401
        client.cookies.set(COOKIE_NAME, cookie)
        assert client.get("/api/auth/me").status_code == 401


def test_username_accepts_unicode_letters_and_rejects_invalid_punctuation():
    assert username(" 靳泊楠 ") == "靳泊楠"
    assert username("Élodie-2") == "élodie-2"
    for value in ("_靳泊楠", "靳 泊楠", "靳/泊楠", "ab"):
        try:
            username(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid username accepted: {value!r}")


def test_csrf_and_cross_origin_rejected(settings, accounts, sign_in):
    with TestClient(create_app(settings)) as client:
        sign_in(client)
        csrf = client.headers.pop("X-CSRF-Token")
        assert client.post("/api/auth/logout").status_code == 403
        client.headers["X-CSRF-Token"] = csrf
        assert (
            client.post("/api/auth/logout", headers={"Origin": "https://evil.test"}).status_code
            == 403
        )
        assert (
            client.post("/api/auth/logout", headers={"Origin": "http://testserver"}).status_code
            == 200
        )
        assert (
            client.post(
                "/api/auth/login",
                json={"username": "alice", "password": "wrong"},
                headers={"Origin": "https://evil.test"},
            ).status_code
            == 403
        )


def test_password_changes_reset_all_sessions(settings, accounts, sign_in):
    with TestClient(create_app(settings)) as first, TestClient(create_app(settings)) as second:
        sign_in(first)
        sign_in(second)
        response = first.post(
            "/api/auth/password",
            json={
                "current_password": "correct horse battery staple",
                "new_password": "a much better new password",
            },
        )
        assert response.status_code == 200
        assert first.get("/api/auth/me").status_code == 401
        assert second.get("/api/auth/me").status_code == 401
        sign_in(first, password="a much better new password")
        db = Database(settings.db_path)
        db.set_active(accounts["alice"], False)
        assert first.get("/api/auth/me").status_code == 401
        assert (
            first.post(
                "/api/auth/login",
                json={"username": "alice", "password": "a much better new password"},
            ).status_code
            == 401
        )
        db.set_active(accounts["alice"], True)
        db.reset_password(accounts["alice"], password_hash("operator reset password"))
        sign_in(first, password="operator reset password")
        with db.connect() as conn:
            conn.execute("UPDATE sessions SET expires_at=0")
        assert first.get("/api/auth/me").status_code == 401


def test_login_throttle(settings, accounts):
    with TestClient(create_app(settings)) as client:
        for _ in range(10):
            assert (
                client.post(
                    "/api/auth/login", json={"username": "alice", "password": "bad"}
                ).status_code
                == 401
            )
        assert (
            client.post(
                "/api/auth/login", json={"username": "alice", "password": "bad"}
            ).status_code
            == 429
        )


def test_secure_cookies_and_password_salt(settings, accounts):
    with TestClient(
        create_app(replace(settings, secure_cookies=True)), base_url="https://testserver"
    ) as client:
        response = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "correct horse battery staple"},
        )
        cookie = response.headers["set-cookie"].lower()
        assert all(flag in cookie for flag in ("httponly", "secure", "samesite=strict"))
        assert client.get("/api/auth/me").status_code == 200
    a, b = password_hash("same password twice"), password_hash("same password twice")
    assert a != b and verify_password("same password twice", a)
    assert not verify_password("wrong", a)


def test_password_reset_racing_with_login_cannot_restore_old_session(settings, accounts):
    db = Database(settings.db_path)
    old = db.user_by_name("alice")["password_hash"]
    db.reset_password(accounts["alice"], password_hash("operator replaced password"))
    assert not db.start_session("old-token", accounts["alice"], "csrf", 3600, "attempt", old)
    assert db.session("old-token") is None


def test_existing_user_schema_gets_repository_lock_columns(settings, encoded_password):
    with sqlite3.connect(settings.db_path) as conn:
        conn.execute(
            """CREATE TABLE users (
            id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL
            )"""
        )
    db = Database(settings.db_path)
    user_id = db.create_user("alice", encoded_password)
    user = db.user_by_name("alice")
    assert user["id"] == user_id
    assert user["repository_url"] == "" and user["repository_locked"] == 0


def test_https_tunnel_preserves_origin_and_csrf_checks(settings, accounts):
    app = create_app(replace(settings, secure_cookies=True))
    forwarded = {
        "Origin": "https://judge.example.com",
        "X-Forwarded-Proto": "https",
        "X-Forwarded-For": "203.0.113.10",
    }
    credentials = {"username": "alice", "password": "correct horse battery staple"}
    # The connector reaches Uvicorn over HTTP from another container, not loopback.
    with TestClient(
        ProxyHeadersMiddleware(app, trusted_hosts="127.0.0.1"),
        base_url="http://judge.example.com",
    ) as client:
        assert (
            client.post("/api/auth/login", json=credentials, headers=forwarded).status_code == 403
        )
    with TestClient(
        ProxyHeadersMiddleware(app, trusted_hosts="*"), base_url="http://judge.example.com"
    ) as client:
        response = client.post("/api/auth/login", json=credentials, headers=forwarded)
        assert response.status_code == 200
        assert "secure" in response.headers["set-cookie"].lower()
        # A browser sends the Secure cookie to the HTTPS edge; the connector relays it over HTTP.
        client.headers.update(forwarded)
        client.headers["Cookie"] = f"{COOKIE_NAME}={response.cookies.get(COOKIE_NAME)}"
        assert client.get("/api/auth/me").status_code == 200
        assert client.post("/api/auth/logout").status_code == 403
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        assert (
            client.post("/api/auth/logout", headers={"Origin": "https://evil.test"}).status_code
            == 403
        )
        assert client.post("/api/auth/logout").status_code == 200
