"""CORS: the frontend origin may call the API; other origins may not."""

from tests.test_phase8_hardening import anon


def _preflight(origin):
    return anon.options(
        "/api/auth/token",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )


def test_local_frontend_origin_is_allowed():
    res = _preflight("http://localhost:5173")
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "authorization" in res.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in res.headers


def test_unknown_origin_is_not_allowed():
    res = _preflight("https://evil.example")
    assert "access-control-allow-origin" not in res.headers


def test_simple_request_carries_cors_header():
    res = anon.get("/api/system/health", headers={"Origin": "http://localhost:3000"})
    assert res.headers["access-control-allow-origin"] == "http://localhost:3000"
