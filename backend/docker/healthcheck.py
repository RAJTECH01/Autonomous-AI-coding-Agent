#!/usr/bin/env python3
"""Container health check for the API.

Why this exists instead of `curl -f`:

  GET /api/v1/readiness always answers HTTP 200. It reports failure in the body
  (`{"status": "unhealthy", "database": "unavailable: ..."}`), so an
  HTTP-status-based probe such as `curl -f` would report healthy even with the
  database down. This script inspects the payload.

It also keeps the runtime image smaller: no curl or wget needs installing, only
the Python standard library.

Exit codes: 0 healthy, 1 unhealthy (Docker's expected convention).
"""

import json
import os
import sys
import urllib.error
import urllib.request

HOST = os.environ.get("HEALTHCHECK_HOST", "127.0.0.1")
PORT = os.environ.get("HEALTHCHECK_PORT", "8000")
API_PREFIX = os.environ.get("API_V1_STR", "/api/v1")
PATH = os.environ.get("HEALTHCHECK_PATH", f"{API_PREFIX}/readiness")
TIMEOUT = float(os.environ.get("HEALTHCHECK_TIMEOUT", "5"))

# Values that mean "serving traffic". /readiness returns "ready"; /health
# returns "healthy", so both endpoints work as a probe target.
OK_STATUSES = {"ready", "healthy"}


def main() -> int:
    url = f"http://{HOST}:{PORT}{PATH}"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            if response.status != 200:
                print(f"unhealthy: {url} returned HTTP {response.status}", file=sys.stderr)
                return 1
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        print(f"unhealthy: cannot reach {url}: {exc.reason}", file=sys.stderr)
        return 1
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"unhealthy: {url} returned unparseable body: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - a probe must never raise
        print(f"unhealthy: unexpected error probing {url}: {exc}", file=sys.stderr)
        return 1

    status = str(payload.get("status", "")).lower()
    if status in OK_STATUSES:
        return 0

    detail = {k: v for k, v in payload.items() if k in ("database", "disk_storage")}
    print(f"unhealthy: status={status!r} detail={detail}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
