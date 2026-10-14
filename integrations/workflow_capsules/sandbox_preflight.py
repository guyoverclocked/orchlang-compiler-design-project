#!/usr/bin/env python3
"""Non-source probe for the exact Seatbelt restrictions used by capsules."""
from __future__ import annotations

import errno
import json
import os
import socket


def denied(error: OSError) -> bool:
    return error.errno in (errno.EPERM, errno.EACCES)


checks: dict[str, bool] = {}

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    sock.connect(("127.0.0.1", 9))
except OSError as error:
    checks["network_denied"] = denied(error)
else:
    checks["network_denied"] = False
finally:
    sock.close()

try:
    with open("/dev/null", "w", encoding="utf-8"):
        pass
except OSError as error:
    checks["writes_denied"] = denied(error)
else:
    checks["writes_denied"] = False

unlisted_file = (
    "/Users/nambi/Documents/ChatGPT/Compiler Project/"
    "orchlang-publication-upgrade/output/publication_upgrade/corpus/sources/"
    "didilili/ai-agents-from-zero/9de20be80dad6d410268ae75f75cf94c355dd364/LICENSE"
)
try:
    with open(unlisted_file, "rb"):
        pass
except OSError as error:
    checks["unlisted_user_file_denied"] = denied(error)
else:
    checks["unlisted_user_file_denied"] = False

try:
    pid = os.fork()
except OSError as error:
    checks["fork_denied"] = denied(error)
else:
    if pid == 0:
        os._exit(0)
    os.waitpid(pid, 0)
    checks["fork_denied"] = False

print("PREFLIGHT_JSON:" + json.dumps(checks, sort_keys=True, separators=(",", ":")))
raise SystemExit(0 if all(checks.values()) else 3)
