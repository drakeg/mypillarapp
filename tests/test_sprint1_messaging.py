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


def test_admin_dashboard_pages_use_sidebar_layout(monkeypatch, tmp_path):
    os.environ["MADMALLARD_DATA_DIR"] = str(tmp_path)
    os.environ["MADMALLARD_ADMIN_USERNAME"] = "admin"
    os.environ["MADMALLARD_ADMIN_PASSWORD_HASH"] = make_test_hash("secret")
    os.environ["MADMALLARD_ADMIN_SESSION_SECRET"] = "session-secret-for-tests"
    import server
    importlib.reload(server)

    class FakeHandler:
        command = "GET"
        def __init__(self): self.rendered = {}
        def send_response(self, status): self.rendered["status"] = status
        def send_header(self, key, value): self.rendered.setdefault("headers", {})[key] = value
        def end_headers(self): pass
        @property
        def wfile(self):
            outer = self
            class W:
                def write(_, data): outer.rendered["body"] = data.decode("utf-8")
            return W()

    for method, expected in [
        ("render_admin_dashboard", "Operations dashboard"),
        ("render_admin_sites", "Managed sites"),
        ("render_admin_settings", "Platform settings"),
    ]:
        h = FakeHandler()
        getattr(server.Handler, method)(h)
        assert h.rendered["status"] == 200
        assert "admin-sidebar" in h.rendered["body"]
        assert expected in h.rendered["body"]
        assert "Mad Mallards Adventures" in h.rendered["body"] or method != "render_admin_sites"


def test_sites_admin_supports_edit_delete_and_crm(monkeypatch, tmp_path):
    os.environ["MADMALLARD_DATA_DIR"] = str(tmp_path)
    os.environ["MADMALLARD_ADMIN_USERNAME"] = "admin"
    os.environ["MADMALLARD_ADMIN_PASSWORD_HASH"] = make_test_hash("secret")
    os.environ["MADMALLARD_ADMIN_SESSION_SECRET"] = "session-secret-for-tests"
    import server
    import messaging
    importlib.reload(messaging)
    importlib.reload(server)

    class FakeHandler:
        command = "GET"
        def __init__(self): self.rendered = {}
        def send_response(self, status): self.rendered["status"] = status
        def send_header(self, key, value): self.rendered.setdefault("headers", {})[key] = value
        def end_headers(self): pass
        @property
        def wfile(self):
            outer = self
            class W:
                def write(_, data): outer.rendered["body"] = data.decode("utf-8")
            return W()

    h = FakeHandler()
    server.Handler.render_admin_sites(h)
    assert h.rendered["status"] == 200
    assert "Add site" in h.rendered["body"]
    assert "/edit" in h.rendered["body"]

    h = FakeHandler()
    server.Handler.render_admin_site_form(h, "solutions")
    assert "Save site" in h.rendered["body"]
    assert "Delete site" in h.rendered["body"]

    messaging.create_conversation(kind="project_request", name="Greg", email="greg@example.com", company="Mad Mallard", subject="AWS", body="Need help", tags=["AWS"])
    h = FakeHandler()
    server.Handler.render_admin_crm(h, {})
    assert h.rendered["status"] == 200
    assert "Customer relationship manager" in h.rendered["body"]
    assert "greg@example.com" in h.rendered["body"]
