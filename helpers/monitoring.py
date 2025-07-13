import logging
import threading
import sys
from datetime import datetime, timedelta
from flask import request
import traceback

from helpers.emailer import send_error_report

# ──────────────────────────────────────────────────────────────────────────
# Email handler for ERROR-level logs
# ──────────────────────────────────────────────────────────────────────────
class EmailErrorHandler(logging.Handler):
    def __init__(self):
        super().__init__()

    def emit(self, record):
        try:
            error_type = record.levelname
            error_message = record.getMessage()

            if record.exc_info:
                traceback_info = "".join(traceback.format_exception(*record.exc_info))
            else:
                traceback_info = record.stack_info or ""

            try:
                req_method = request.method
                req_path = request.path
                form_data = request.form.to_dict()
                args_data = request.args.to_dict()
                user_agent = request.headers.get("User-Agent", "")
                remote_addr = request.remote_addr
            except RuntimeError:
                req_method = req_path = user_agent = remote_addr = ""
                form_data = args_data = {}

            send_error_report(
                error_type,
                error_message,
                traceback_info,
                req_method,
                req_path,
                form_data,
                args_data,
                user_agent,
                remote_addr
            )
        except Exception as exc:
            sys.stderr.write(f"[monitoring] EmailErrorHandler failed: {exc}\n")


# ──────────────────────────────────────────────────────────────────────────
# Login failure monitoring
# ──────────────────────────────────────────────────────────────────────────
_login_fail_count = 0
_login_fail_window_start = datetime.now()
_login_fail_lock = threading.Lock()
_stop_event = threading.Event()

def record_login_failure():
    global _login_fail_count
    with _login_fail_lock:
        _login_fail_count += 1


# ────────────────────────────────────────────────────────────────────
#  Single-shot checker (useful for unit-tests)
# ────────────────────────────────────────────────────────────────────
def _login_failure_check(threshold: int = 5) -> bool:
    """
    Inspect the counter once, send alert if needed, then reset.
    Returns True if an alert was triggered.
    """
    global _login_fail_count, _login_fail_window_start
    now = datetime.now()
    alert_sent = False

    with _login_fail_lock:
        if _login_fail_count >= threshold:
            body = (
                f"{_login_fail_count} login checks failed\n"
                f"from {_login_fail_window_start.isoformat()} to {now.isoformat()}"
            )
            send_error_report(
                error_type="Login failures threshold",
                error_message=body,
                traceback_info="",
                request_method="",
                request_path="",
                form_data={},
                args_data={},
                user_agent="",
                remote_addr="",
            )
            alert_sent = True

        # reset window regardless
        _login_fail_count = 0
        _login_fail_window_start = now

    return alert_sent


def _monitor_login_failures(interval_min=5, threshold=5):
    ev = threading.Event()
    while not _stop_event.is_set():
        ev.wait(interval_min * 60)
        _login_failure_check(threshold)



# ──────────────────────────────────────────────────────────────────────────
# Sliding-window monitors for HTTP events
# ──────────────────────────────────────────────────────────────────────────
_WINDOW = timedelta(minutes=5)
_ALERT_RESET_GRACE = timedelta(minutes=10)

_404_THRESHOLD = 25
_5XX_THRESHOLD = 4
_SLOW_COUNT_THRESHOLD = 20
_SLOW_DURATION_THRESHOLD = 0.5  # seconds

_404_state = {'count': 0, 'window_start': datetime.now(), 'alerted': False}
_5xx_state = {'count': 0, 'window_start': datetime.now(), 'alerted': False}
_slow_state = {'count': 0, 'window_start': datetime.now(), 'alerted': False}

def _reset_state(state):
    state['count'] = 0
    state['window_start'] = datetime.now()
    state['alerted'] = False

def _auto_reset_states():
    """Clears 'alerted' flag on stale state windows even without new events."""
    ev = threading.Event()
    while not _stop_event.is_set():
        now = datetime.now()
        for state in (_404_state, _5xx_state, _slow_state):
            if state['alerted'] and now - state['window_start'] > _WINDOW + _ALERT_RESET_GRACE:
                _reset_state(state)
        ev.wait(_WINDOW.total_seconds())

def record_404():
    now = datetime.now()
    st = _404_state
    if now - st['window_start'] > _WINDOW:
        _reset_state(st)
    st['count'] += 1
    if st['count'] >= _404_THRESHOLD and not st['alerted']:
        st['alerted'] = True
        body = (
            f"{st['count']} 404 responses from {st['window_start'].isoformat()} to {now.isoformat()}\n"
            f"Example path: {request.path}\n"
            f"IP: {request.remote_addr}"
        )
        send_error_report(
            error_type="404 Spike",
            error_message=body,
            traceback_info="",
            request_method=request.method,
            request_path=request.path,
            form_data={},
            args_data={},
            user_agent=request.headers.get("User-Agent", ""),
            remote_addr=request.remote_addr,
        )

def record_5xx():
    now = datetime.now()
    st = _5xx_state
    if now - st['window_start'] > _WINDOW:
        _reset_state(st)
    st['count'] += 1
    if st['count'] >= _5XX_THRESHOLD and not st['alerted']:
        st['alerted'] = True
        body = (
            f"{st['count']} 5xx responses from {st['window_start'].isoformat()} to {now.isoformat()}\n"
            f"Example path: {request.path}\n"
            f"IP: {request.remote_addr}"
        )
        send_error_report(
            error_type="5xx spike",
            error_message=body,
            traceback_info="",
            request_method=request.method,
            request_path=request.path,
            form_data={},
            args_data={},
            user_agent=request.headers.get("User-Agent", ""),
            remote_addr=request.remote_addr,
        )

def record_slow(duration):
    if duration < _SLOW_DURATION_THRESHOLD:
        return
    now = datetime.now()
    st = _slow_state
    if now - st['window_start'] > _WINDOW:
        _reset_state(st)
    st['count'] += 1
    if st['count'] >= _SLOW_COUNT_THRESHOLD and not st['alerted']:
        st['alerted'] = True
        body = (
            f"{st['count']} slow responses (>= {_SLOW_DURATION_THRESHOLD}s) "
            f"from {st['window_start'].isoformat()} to {now.isoformat()}\n"
            f"Example: {duration:.2f}s at {request.path}\n"
            f"IP: {request.remote_addr}"
        )
        send_error_report(
            error_type="Slow-response spike",
            error_message=body,
            traceback_info="",
            request_method=request.method,
            request_path=request.path,
            form_data={},
            args_data={},
            user_agent=request.headers.get("User-Agent", ""),
            remote_addr=request.remote_addr,
        )

# ──────────────────────────────────────────────────────────────────────────
# Start/stop hooks for Flask app lifecycle
# ──────────────────────────────────────────────────────────────────────────

_threads = []

def start_monitoring_threads():
    if _threads:
        return  # already started

    login_thread = threading.Thread(
        target=_monitor_login_failures,
        args=(5, 5),
        daemon=True
    )
    reset_thread = threading.Thread(
        target=_auto_reset_states,
        daemon=True
    )
    _threads.extend([login_thread, reset_thread])
    for t in _threads:
        t.start()

def stop_monitoring_threads():
    _stop_event.set()
