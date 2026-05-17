import json

from exopy.audit import AuditLogger, login


def test_audit_logger_writes_structured_json_lines_and_exports(tmp_path):
    session = login("alice")
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path=path, session=session)

    event = logger.record("search", target="TOI178", rows=2)
    exported = logger.export(tmp_path / "exported.jsonl")

    assert event["username"] == "alice"
    assert event["event_type"] == "search"
    assert exported.read_text(encoding="utf-8") == path.read_text(encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["payload"] == {"rows": 2, "target": "TOI178"}
