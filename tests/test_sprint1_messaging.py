import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOLUTIONS = ROOT / "site" / "solutions"
sys.path.insert(0, str(SOLUTIONS))


def load_modules(tmp_path):
    os.environ["MADMALLARD_DATA_DIR"] = str(tmp_path)
    os.environ["MADMALLARD_ENABLE_EMAIL"] = "false"
    import messaging
    import form_config
    importlib.reload(messaging)
    importlib.reload(form_config)
    return messaging, form_config


def test_request_payload_validation(tmp_path):
    _, form_config = load_modules(tmp_path)
    cleaned, errors = form_config.validate_request_payload({"name": "Greg"})
    assert "email" in errors
    assert "message" in errors

    cleaned, errors = form_config.validate_request_payload({
        "name": "Greg",
        "email": "greg@example.com",
        "service": "AWS / cloud setup",
        "message": "Need help",
    })
    assert errors == {}
    assert cleaned["service"] == "AWS / cloud setup"


def test_conversation_and_customer_requests(tmp_path):
    messaging, _ = load_modules(tmp_path)
    convo = messaging.create_conversation(
        kind="project_request",
        name="Greg",
        email="greg@example.com",
        company="Mad Mallard",
        subject="AWS / cloud setup",
        body="Need help with AWS",
        tags=["AWS / cloud setup"],
        lead={"service": "AWS / cloud setup"},
    )
    assert convo["status"] == "new"
    token_url = messaging.customer_dashboard_url("greg@example.com")
    dashboard_token = token_url.rsplit("/", 1)[-1]
    requests = messaging.get_customer_requests(dashboard_token)
    assert len(requests) == 1
    assert requests[0]["token"] == convo["token"]


def test_message_status_transitions_and_feedback(tmp_path):
    messaging, _ = load_modules(tmp_path)
    convo = messaging.create_conversation(
        kind="chat",
        name="Visitor",
        email="visitor@example.com",
        subject="Website chat",
        body="Hello",
    )
    updated = messaging.add_message(convo["token"], body="Admin reply", sender="Greg", sender_type="admin")
    assert updated["status"] == "waiting_on_client"
    updated = messaging.add_message(convo["token"], body="Visitor reply", sender="Visitor", sender_type="visitor")
    assert updated["status"] == "waiting_on_me"
    assert messaging.record_feedback_by_conversation(convo["token"], "good", "Helpful") is True
    convo2, _ = messaging.get_conversation(convo["token"])
    assert convo2["last_feedback_rating"] == "good"


def make_test_hash(password: str, salt: str = "testsalt", iterations: int = 1000) -> str:
    import hashlib
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def test_admin_login_uses_username_password_not_token(monkeypatch, tmp_path):
    os.environ["MADMALLARD_DATA_DIR"] = str(tmp_path)
    os.environ["MADMALLARD_ADMIN_USERNAME"] = "admin"
    os.environ["MADMALLARD_ADMIN_PASSWORD_HASH"] = make_test_hash("secret")
    os.environ["MADMALLARD_ADMIN_SESSION_SECRET"] = "session-secret-for-tests"
    os.environ["MADMALLARD_ADMIN_TOKEN"] = "automation-token"
    import server
    importlib.reload(server)

    assert server.admin_auth_configured() is True
    assert server.verify_password("secret", server.ADMIN_PASSWORD_HASH) is True
    assert server.verify_password("wrong", server.ADMIN_PASSWORD_HASH) is False

    rendered = {}

    class FakeHandler:
        command = "GET"
        def send_response(self, status): rendered["status"] = status
        def send_header(self, key, value): rendered.setdefault("headers", {})[key] = value
        def end_headers(self): pass
        @property
        def wfile(self):
            class W:
                def write(_, data): rendered["body"] = data.decode("utf-8")
            return W()

    server.Handler.render_login(FakeHandler())
    assert rendered["status"] == 200
    assert "name='username'" in rendered["body"]
    assert "name='password'" in rendered["body"]
    assert "Admin token" not in rendered["body"]


def test_customer_request_summary_tracks_latest_message_and_reply_needed(tmp_path):
    messaging, _ = load_modules(tmp_path)
    convo = messaging.create_conversation(
        kind="project_request",
        name="Greg",
        email="greg@example.com",
        company="Mad Mallard",
        subject="Terraform help",
        body="Initial request",
        tags=["Terraform"],
    )
    messaging.add_message(convo["token"], body="Can you send more detail?", sender="Greg", sender_type="admin")
    dashboard_token = messaging.customer_dashboard_url("greg@example.com").rsplit("/", 1)[-1]
    summary = messaging.customer_request_summary(dashboard_token)
    assert len(summary) == 1
    assert summary[0]["needs_customer"] is True
    assert summary[0]["state_label"] == "Reply requested"
    assert summary[0]["latest_message"]["body"] == "Can you send more detail?"


def test_project_request_response_includes_my_requests_link(monkeypatch, tmp_path):
    os.environ["MADMALLARD_DATA_DIR"] = str(tmp_path)
    os.environ["MADMALLARD_ENABLE_EMAIL"] = "false"
    import server
    importlib.reload(server)

    payload = {
        "name": "Greg",
        "email": "greg@example.com",
        "company": "Mad Mallard",
        "service": "AWS / cloud setup",
        "timeline": "This month",
        "budget": "Not sure yet",
        "message": "Need help with AWS",
    }
    sent = {}
    def fake_json_response(handler, status, body):
        sent["status"] = status
        sent["body"] = body
    monkeypatch.setattr(server, "json_response", fake_json_response)
    monkeypatch.setattr(server.messaging, "notify_new_conversation", lambda *a, **k: None)
    monkeypatch.setattr(server.messaging, "notify_visitor_link", lambda *a, **k: None)

    class FakeHandler:
        pass

    server.Handler.handle_project_request(FakeHandler(), payload)
    assert sent["status"] == 200
    assert sent["body"]["ok"] is True
    assert sent["body"]["conversation_url"].startswith("/chat/")
    assert "/my-requests/" in sent["body"]["my_requests_url"]
