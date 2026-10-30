"""约定 / 待续话题（需求 20）测试。"""

from __future__ import annotations


def test_create_and_list_promise(client):
    r = client.post("/api/v1/promises", json={"content": "周末一起看那部电影", "certainty": "confirmed"})
    assert r.status_code == 201
    body = r.json()
    assert body["content"] == "周末一起看那部电影"
    assert body["certainty"] == "confirmed"
    assert body["status"] == "pending"

    listed = client.get("/api/v1/promises").json()
    assert any(p["id"] == body["id"] for p in listed)


def test_promise_status_transitions(client):
    r = client.post("/api/v1/promises", json={"content": "提醒我买牛奶"}).json()
    pid = r["id"]

    done = client.patch(f"/api/v1/promises/{pid}", json={"status": "done"}).json()
    assert done["status"] == "done"

    postponed = client.patch(f"/api/v1/promises/{pid}", json={"status": "postponed"}).json()
    assert postponed["status"] == "postponed"


def test_promise_invalid_status_rejected(client):
    r = client.post("/api/v1/promises", json={"content": "测试"}).json()
    pid = r["id"]
    bad = client.patch(f"/api/v1/promises/{pid}", json={"status": "bogus"})
    assert bad.status_code == 422


def test_promise_empty_content_rejected(client):
    r = client.post("/api/v1/promises", json={"content": "   "})
    assert r.status_code == 422


def test_promise_vague_default(client):
    r = client.post("/api/v1/promises", json={"content": "下次再说"}).json()
    assert r["certainty"] == "vague"


def test_promise_filter_by_status(client):
    client.post("/api/v1/promises", json={"content": "待办A", "status": "pending"}).json()
    done = client.post("/api/v1/promises", json={"content": "完成B"}).json()
    client.patch(f"/api/v1/promises/{done['id']}", json={"status": "done"})

    pending = client.get("/api/v1/promises?status=pending").json()
    assert all(p["status"] == "pending" for p in pending)
    done_list = client.get("/api/v1/promises?status=done").json()
    assert any(p["content"] == "完成B" for p in done_list)


def test_promise_delete(client):
    r = client.post("/api/v1/promises", json={"content": "要删的"}).json()
    pid = r["id"]
    assert client.delete(f"/api/v1/promises/{pid}").status_code == 204
    assert client.get(f"/api/v1/promises/{pid}").status_code in (404, 405)
