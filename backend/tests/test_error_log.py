from backend.src.error_log import redact

def test_error_log_redacts_credentials_and_nested_secrets():
    payload = {
        "Authorization": "Bearer secret",
        "password": "very-secret",
        "nested": {"access_token": "token-value", "safe": "ok"},
        "items": [{"api_key": "abc", "name": "x"}],
    }
    result = redact(payload)
    assert result["Authorization"] == "[REDACTED]"
    assert result["password"] == "[REDACTED]"
    assert result["nested"]["access_token"] == "[REDACTED]"
    assert result["nested"]["safe"] == "ok"
    assert result["items"][0]["api_key"] == "[REDACTED]"
