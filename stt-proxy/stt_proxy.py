#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AQing STT proxy (v1.40) — OpenAI-compatible /v1/audio/transcriptions with
automatic primary->fallback model failover.

Why: SiliconFlow SenseVoiceSmall intermittently returns HTTP 500 (~3 min
outages, seen 20:16 and 09:23). The folotoy "brain" is closed-source Cython
(.so), so its retry logic cannot be patched. This sidecar sits between the
brain and SiliconFlow: same OpenAI wire protocol, brain needs no code change.

Design constraints (honoured):
  * ZERO third-party deps — stdlib only (http.server + urllib). Tiny image.
  * The brain's own Authorization header is forwarded verbatim to upstream;
    the API key is never stored here, never logged, never echoed.
  * multipart body is passed through byte-for-byte; ONLY the `model` form
    field value is rewritten when failing over. Audio payload is untouched.
  * Non-2xx / timeout / network error on primary -> retry once on fallback.
    If both fail -> return a JSON 502 (never silently swallow).
  * Structured logs record model/status/duration/bytes only — no text/audio/key.

Env:
  PRIMARY_MODEL   default TeleAI/TeleSpeechASR
  FALLBACK_MODEL  default FunAudioLLM/SenseVoiceSmall
  UPSTREAM_URL    default https://api.siliconflow.cn/v1/audio/transcriptions
  UPSTREAM_KEY    optional fallback key if the caller sends no Authorization
  UPSTREAM_TIMEOUT seconds per attempt, default 30
  PORT            default 8000
  STT_ALLOW_TEST  "1" enables X-STT-Test-Fail hook (off in production)

Test hook (only when STT_ALLOW_TEST=1), header X-STT-Test-Fail:
  primary -> force primary attempt to fail (verify failover to fallback)
  all     -> force both attempts to fail (verify clean 502, no false success)
"""
import json
import os
import sys
import time
import uuid
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PRIMARY = os.getenv("PRIMARY_MODEL", "TeleAI/TeleSpeechASR")
FALLBACK = os.getenv("FALLBACK_MODEL", "FunAudioLLM/SenseVoiceSmall")
UPSTREAM = os.getenv(
    "UPSTREAM_URL",
    "https://api.siliconflow.cn/v1/audio/transcriptions",
)
UPSTREAM_KEY = os.getenv("UPSTREAM_KEY", "")
try:
    TIMEOUT = float(os.getenv("UPSTREAM_TIMEOUT", "30"))
except ValueError:
    TIMEOUT = 30.0
PORT = int(os.getenv("PORT", "8000"))
ALLOW_TEST = os.getenv("STT_ALLOW_TEST", "0") == "1"


def log(**fields):
    """Single-line structured log to stdout. Never include keys/audio/text."""
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    parts = ["ts=" + ts]
    for k, v in fields.items():
        parts.append("%s=%s" % (k, v))
    sys.stdout.write("[stt-proxy] " + " ".join(parts) + "\n")
    sys.stdout.flush()


def replace_model(body, model):
    """Rewrite ONLY the value of the multipart `model` form field, in bytes.
    Audio and all other fields stay byte-identical. If the field is absent,
    return body unchanged (upstream uses whatever the caller sent)."""
    key = b'name="model"'
    i = body.find(key)
    if i < 0:
        return body
    j = body.find(b"\r\n\r\n", i)
    if j < 0:
        return body
    vstart = j + 4
    vend = body.find(b"\r\n", vstart)
    if vend < 0:
        return body
    return body[:vstart] + model.encode("utf-8") + body[vend:]


def call_upstream(body, content_type, auth, model, timeout):
    """POST one transcription attempt. Returns (status, resp_bytes, ctype).
    Raises urllib.error.HTTPError for non-2xx; other exceptions propagate."""
    payload = replace_model(body, model)
    headers = {
        "Content-Type": content_type,
        "Authorization": auth,
        "Accept": "application/json",
    }
    req = urllib.request.Request(UPSTREAM, data=payload, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read(), r.headers.get("Content-Type", "application/json")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "AQingSTTProxy/1.40"

    def log_message(self, fmt, *args):
        # Silence the default stderr access log; we emit structured logs.
        pass

    def _send(self, status, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        if self.path.rstrip("/") in ("/health", "/v1/health"):
            self._send(200, json.dumps({
                "status": "ok",
                "primary": PRIMARY,
                "fallback": FALLBACK,
                "upstream": UPSTREAM,
                "test_hook": ALLOW_TEST,
            }, ensure_ascii=False))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        path = self.path.split("?", 1)[0].rstrip("/")
        if path not in ("/v1/audio/transcriptions", "/audio/transcriptions"):
            self._send(404, json.dumps({"error": "not found"}))
            return

        req_id = uuid.uuid4().hex[:8]
        t0 = time.time()
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        body = self.rfile.read(length) if length > 0 else b""
        content_type = self.headers.get("Content-Type", "multipart/form-data")

        auth = self.headers.get("Authorization", "")
        if not auth and UPSTREAM_KEY:
            auth = "Bearer " + UPSTREAM_KEY

        force = ""
        if ALLOW_TEST:
            force = self.headers.get("X-STT-Test-Fail", "").strip().lower()

        log(event="req", id=req_id, path=path, bytes=len(body),
            auth="yes" if auth else "no", test=force or "-")

        attempts = []
        models = [("primary", PRIMARY), ("fallback", FALLBACK)]
        for idx, (role, model) in enumerate(models):
            # Deterministic test hook: forge a failure without touching upstream.
            if (force == "primary" and idx == 0) or force == "all":
                log(event="attempt", id=req_id, role=role, model=model,
                    status=500, dur="0.00", note="forced-test-fail")
                attempts.append("%s:%s" % (model, 500))
                continue
            t1 = time.time()
            try:
                status, resp, ctype = call_upstream(
                    body, content_type, auth, model, TIMEOUT
                )
                dur = time.time() - t1
                if 200 <= status < 300:
                    log(event="attempt", id=req_id, role=role, model=model,
                        status=status, dur="%.2f" % dur, ok=1,
                        resp_bytes=len(resp))
                    log(event="done", id=req_id, result="ok", model=model,
                        total="%.2f" % (time.time() - t0), attempts="->".join(attempts))
                    self._send(status, resp, ctype)
                    return
                # non-2xx -> record and fall through to next model
                log(event="attempt", id=req_id, role=role, model=model,
                    status=status, dur="%.2f" % dur, ok=0)
                attempts.append("%s:%s" % (model, status))
            except urllib.error.HTTPError as e:
                dur = time.time() - t1
                try:
                    e.read()
                except Exception:
                    pass
                log(event="attempt", id=req_id, role=role, model=model,
                    status=e.code, dur="%.2f" % dur, ok=0)
                attempts.append("%s:%s" % (model, e.code))
            except Exception as e:
                dur = time.time() - t1
                log(event="attempt", id=req_id, role=role, model=model,
                    status="ERR", dur="%.2f" % dur, ok=0,
                    exc=type(e).__name__)
                attempts.append("%s:%s" % (model, type(e).__name__))

        # Both attempts failed.
        log(event="done", id=req_id, result="fail",
            total="%.2f" % (time.time() - t0), attempts="->".join(attempts))
        self._send(502, json.dumps({
            "error": "all STT models failed",
            "attempts": attempts,
        }, ensure_ascii=False))


def main():
    log(event="boot", primary=PRIMARY, fallback=FALLBACK,
        upstream=UPSTREAM, timeout=TIMEOUT, port=PORT, test=ALLOW_TEST)
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
