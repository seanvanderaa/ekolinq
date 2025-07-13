import time
from flask import Flask
import helpers.monitoring as mon

def _capture_emails(monkeypatch):
    sent = []
    monkeypatch.setattr(mon, "send_error_report", lambda *a, **kw: sent.append((a, kw)))
    return sent

def test_login_failure_spike(monkeypatch):
    emails = []
    monkeypatch.setattr(mon, "send_error_report",
                        lambda *a, **kw: emails.append((a, kw)))

    threshold = 3

    for _ in range(threshold):
        mon.record_login_failure()

    assert mon._login_failure_check(threshold=threshold) is True
    assert any("Login failures threshold" in kw["error_type"] for _, kw in emails)

