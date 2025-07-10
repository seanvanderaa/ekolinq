import logging
import threading
from datetime import datetime, timedelta
from flask import request, current_app
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
            # Gather record info
            error_type    = record.levelname
            error_message = record.getMessage()

            # Traceback if available
            if record.exc_info:
                traceback_info = "".join(traceback.format_exception(*record.exc_info))
            else:
                traceback_info = record.stack_info or ""

            # Request context
            try:
                req_method  = request.method
                req_path    = request.path
                form_data   = request.form.to_dict()
                args_data   = request.args.to_dict()
                user_agent  = request.headers.get("User-Agent", "")
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
        except Exception:
            pass

# ──────────────────────────────────────────────────────────────────────────
# Login failure monitoring (background thread)
# ──────────────────────────────────────────────────────────────────────────
_login_fail_count = 0
_login_fail_window_start = datetime.utcnow()
_login_fail_lock = threading.Lock()

THRESHOLDS = {
    'login_fail': {'count': lambda: _login_fail_count, 'threshold': 5, 'window': timedelta(minutes=5)}
}

def record_login_failure():
    """
    Increment login failure counter for sliding window.
    """
    global _login_fail_count
    with _login_fail_lock:
        _login_fail_count += 1

# Background monitor thread for login failures (fires every 5 minutes)
def _monitor_login_failures(interval_min=5, threshold=5):
    global _login_fail_count, _login_fail_window_start
    while True:
        threading.Event().wait(interval_min * 60)
        with _login_fail_lock:
            now = datetime.utcnow()
            if _login_fail_count > threshold:
                subject = f"⚠️ High login failures: {_login_fail_count} in {interval_min}m"
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
            _login_fail_count = 0
            _login_fail_window_start = now

# Start the login failure monitor thread on import
threading.Thread(
    target=_monitor_login_failures,
    args=(5, 5),
    daemon=True
).start()

# ──────────────────────────────────────────────────────────────────────────
# Sliding-window monitors for HTTP events
# ──────────────────────────────────────────────────────────────────────────
# Configuration
_WINDOW = timedelta(minutes=5)
_404_THRESHOLD = 50
_5XX_THRESHOLD = 10
_SLOW_COUNT_THRESHOLD = 20
_SLOW_DURATION_THRESHOLD = 0.5  # seconds

# State for each event
_404_state = {'count': 0, 'window_start': datetime.utcnow(), 'alerted': False}
_5xx_state = {'count': 0, 'window_start': datetime.utcnow(), 'alerted': False}
_slow_state = {'count': 0, 'window_start': datetime.utcnow(), 'alerted': False}

# Helper to reset state
def _reset_state(state):
    state['count'] = 0
    state['window_start'] = datetime.utcnow()
    state['alerted'] = False

# Record functions

def record_404():
    """Call on each 404 response to detect spikes."""
    now = datetime.utcnow()
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
            error_type="404 spike",
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
    """Call on each 5xx response to detect spikes."""
    now = datetime.utcnow()
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
    """Call with request duration (s) to detect slow-response spikes."""
    if duration < _SLOW_DURATION_THRESHOLD:
        return
    now = datetime.utcnow()
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
