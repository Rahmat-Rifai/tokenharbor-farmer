import pytest
from th_action_resolver import parse_action_from_html, resolve_signup_action, invalidate_action_cache

def test_parse_action_from_html():
    sample_html = """
    <form class="space-y-4" action="" encType="multipart/form-data" method="POST">
    <input type="hidden" name="$ACTION_REF_1"/>
    <input type="hidden" name="$ACTION_1:0" value="{&quot;id&quot;:&quot;601deb87587212e262e9f8b231f1cf29b6a227a0ad&quot;,&quot;bound&quot;:&quot;$@1&quot;}"/>
    <input type="hidden" name="$ACTION_1:1" value="[&quot;$undefined&quot;]"/>
    <input type="hidden" name="$ACTION_KEY" value="kb3df6a1d48e1a01307dd1ff043d81c6e"/>
    <input type="hidden" name="device_fingerprint" value=""/>
    </form>
    """
    res = parse_action_from_html(sample_html)
    assert res is not None
    assert res["action_id"] == "601deb87587212e262e9f8b231f1cf29b6a227a0ad"
    assert res["action_key"] == "kb3df6a1d48e1a01307dd1ff043d81c6e"
    assert res["next_action"] == "601deb87587212e262e9f8b231f1cf29b6a227a0ad"

def test_parse_action_from_html_invalid():
    assert parse_action_from_html("<html><body>No form</body></html>") is None

def test_resolve_signup_action_fallback(monkeypatch, tmp_path):
    cache_path = tmp_path / ".test_cache.json"
    monkeypatch.setattr("th_action_resolver.CACHE_FILE", str(cache_path))
    # Mock requests to test fallback when network fails
    def mock_get(*args, **kwargs):
        raise ConnectionError("Network offline")
    monkeypatch.setattr("requests.get", mock_get)

    res = resolve_signup_action(force_refresh=True)
    assert "action_id" in res
    assert "action_key" in res
    assert "next_action" in res
    assert res["action_id"] == "601deb87587212e262e9f8b231f1cf29b6a227a0ad"

def test_resolve_signup_action_cache(monkeypatch, tmp_path):
    cache_path = tmp_path / ".test_cache.json"
    cache_path.write_text('{"action_id": "cached_id", "action_key": "cached_key", "next_action": "cached_id"}', encoding="utf-8")
    monkeypatch.setattr("th_action_resolver.CACHE_FILE", str(cache_path))
    res = resolve_signup_action(force_refresh=False)
    assert res["action_id"] == "cached_id"
    assert res["action_key"] == "cached_key"

def test_resolve_signup_action_live_parse(monkeypatch, tmp_path):
    cache_path = tmp_path / ".test_cache.json"
    monkeypatch.setattr("th_action_resolver.CACHE_FILE", str(cache_path))
    html_content = """
    <input type="hidden" name="$ACTION_1:0" value="{&quot;id&quot;:&quot;new_id_123&quot;}"/>
    <input type="hidden" name="$ACTION_KEY" value="new_key_456"/>
    """
    class MockResponse:
        status_code = 200
        text = html_content
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: MockResponse())
    res = resolve_signup_action(force_refresh=True)
    assert res["action_id"] == "new_id_123"
    assert res["action_key"] == "new_key_456"
    assert res["next_action"] == "new_id_123"


def test_invalidate_action_cache(monkeypatch, tmp_path):
    cache_path = tmp_path / ".test_cache.json"
    cache_path.write_text('{"action_id": "cached_id"}', encoding="utf-8")
    monkeypatch.setattr("th_action_resolver.CACHE_FILE", str(cache_path))

    assert cache_path.exists() is True
    ok = invalidate_action_cache()
    assert ok is True
    assert cache_path.exists() is False

    # Calling again when file is already gone returns False and does not crash
    assert invalidate_action_cache() is False
