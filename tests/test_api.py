from app import app

OLD = "CREATE TABLE t (id INT PRIMARY KEY, n INT);"
NEW = "CREATE TABLE t (id INT PRIMARY KEY);"


def client():
    return app.test_client()


def test_api_reports_breaking_change():
    r = client().post("/api/diff", json={"old": OLD, "new": NEW})
    assert r.status_code == 200
    body = r.get_json()
    assert body["summary"]["verdict"] == "BREAKING"
    assert body["changes"][0]["kind"] == "column_removed"


def test_api_accepts_json_schema_objects():
    old = {"tables": {"t": {"columns": {"id": {"type": "int", "nullable": False}}}}}
    new = {"tables": {"t": {"columns": {"id": {"type": "bigint", "nullable": False}}}}}
    r = client().post("/api/diff", json={"old": old, "new": new})
    assert r.status_code == 200
    assert r.get_json()["summary"]["verdict"] == "SAFE"


def test_api_rejects_bad_requests():
    assert client().post("/api/diff", data="nope").status_code == 400
    assert client().post("/api/diff", json={"old": OLD}).status_code == 400
    r = client().post("/api/diff", json={"old": "SELECT 1;", "new": NEW})
    assert r.status_code == 422 and "error" in r.get_json()


def test_oversized_request_is_rejected():
    r = client().post("/api/diff", json={"old": "x" * (600 * 1024), "new": NEW})
    assert r.status_code == 413
