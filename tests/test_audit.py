import json

from shopify_mcp.audit import MutationAuditor


def test_audit_redacts_values_and_hashes_target(tmp_path):
    path = tmp_path / "nested" / "audit.jsonl"
    auditor = MutationAuditor(path)
    arguments = {
        "id": "gid://shopify/Product/123",
        "tags": ["vip-secret", "campaign-secret"],
        "title": "private seo title",
        "confirm": True,
    }
    auditor.record(tool="shopify_add_tags", arguments=arguments, outcome="success")
    raw = path.read_text(encoding="utf-8")
    event = json.loads(raw)
    assert "gid://" not in raw
    assert "vip-secret" not in raw
    assert "private seo title" not in raw
    assert event["argumentSummary"] == {"fields": ["id", "tags", "title"], "tagCount": 2}
    assert len(event["targetHash"]) == 16


def test_disabled_audit_does_not_write(tmp_path):
    MutationAuditor(None).record(tool="shopify_add_tags", arguments={}, outcome="success")
    assert list(tmp_path.iterdir()) == []
