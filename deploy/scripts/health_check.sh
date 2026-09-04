#!/usr/bin/env bash
###############################################################################
# Post-deploy health verification.
#
#   health_check.sh [BASE_URL]
#   BASE_URL=https://agent.example.com ./health_check.sh
#
# Exit code 0 means the deployment is serving correctly. Any non-zero exit means
# it is not, and the caller must treat that as a failed deploy and roll back.
# The release workflow calls this as its gate, and the PR pipeline calls it
# against the ephemeral stack, so CI and production verify identically.
#
# Environment
#   BASE_URL              default http://localhost:8080
#   TIMEOUT               total seconds to keep retrying   (default 120)
#   INTERVAL              seconds between attempts         (default 5)
#   EXPECT_DOCS_BLOCKED   1 = assert /api/v1/docs is NOT public (production)
#   EXPECT_METRICS_BLOCKED 1 = assert /api/v1/metrics is NOT public (production)
#   INSECURE_TLS          1 = allow self-signed certificates (staging only)
#
# WHY THE READINESS CHECK PARSES THE BODY
#   GET /api/v1/readiness always answers HTTP 200, reporting failure inside the
#   payload ({"status":"unhealthy","database":"unavailable: ..."}). A status-code
#   probe such as `curl -f` therefore passes with the database down. Every check
#   below asserts on content, not just the code.
###############################################################################

set -euo pipefail

BASE_URL="${1:-${BASE_URL:-http://localhost:8080}}"
BASE_URL="${BASE_URL%/}"   # strip any trailing slash
TIMEOUT="${TIMEOUT:-120}"
INTERVAL="${INTERVAL:-5}"
EXPECT_DOCS_BLOCKED="${EXPECT_DOCS_BLOCKED:-0}"
EXPECT_METRICS_BLOCKED="${EXPECT_METRICS_BLOCKED:-0}"
INSECURE_TLS="${INSECURE_TLS:-0}"

CURL_OPTS=(--silent --show-error --max-time 10)
[[ "$INSECURE_TLS" == "1" ]] && CURL_OPTS+=(--insecure)

PASS=0
FAIL=0

c_red=''; c_green=''; c_yellow=''; c_reset=''
if [[ -t 1 ]]; then
    c_red=$'\033[31m'; c_green=$'\033[32m'; c_yellow=$'\033[33m'; c_reset=$'\033[0m'
fi

log()  { echo "[health] $(date -u +%H:%M:%SZ) $*"; }
ok()   { echo "  ${c_green}PASS${c_reset}  $*"; PASS=$((PASS + 1)); }
bad()  { echo "  ${c_red}FAIL${c_reset}  $*"; FAIL=$((FAIL + 1)); }
warn() { echo "  ${c_yellow}WARN${c_reset}  $*"; }

# ---------------------------------------------------------------------------
# Wait for the stack to answer at all before asserting anything specific,
# so a slow start is not reported as a broken deploy.
# ---------------------------------------------------------------------------
wait_for_ready() {
    local deadline=$((SECONDS + TIMEOUT))
    local attempt=0
    log "waiting up to ${TIMEOUT}s for ${BASE_URL}/api/v1/readiness"

    while (( SECONDS < deadline )); do
        attempt=$((attempt + 1))
        local body
        if body="$(curl "${CURL_OPTS[@]}" "${BASE_URL}/api/v1/readiness" 2>/dev/null)"; then
            if [[ "$body" == *'"status":"ready"'* ]]; then
                log "ready after ${attempt} attempt(s)"
                return 0
            fi
            log "attempt ${attempt}: not ready yet -> ${body:0:160}"
        else
            log "attempt ${attempt}: no response yet"
        fi
        sleep "$INTERVAL"
    done

    bad "service did not become ready within ${TIMEOUT}s"
    return 1
}

# status_of URL -> prints HTTP status code
status_of() {
    curl "${CURL_OPTS[@]}" -o /dev/null -w '%{http_code}' "$1" 2>/dev/null || echo "000"
}

check_body_contains() {
    local name="$1" url="$2" needle="$3"
    local body
    if ! body="$(curl "${CURL_OPTS[@]}" "$url" 2>/dev/null)"; then
        bad "${name}: request to ${url} failed"
        return
    fi
    if [[ "$body" == *"$needle"* ]]; then
        ok "${name}"
    else
        bad "${name}: expected to find '${needle}' in response -> ${body:0:200}"
    fi
}

check_status() {
    local name="$1" url="$2" expected="$3"
    local code
    code="$(status_of "$url")"
    if [[ "$code" == "$expected" ]]; then
        ok "${name} (HTTP ${code})"
    else
        bad "${name}: expected HTTP ${expected}, got ${code} from ${url}"
    fi
}

check_status_in() {
    local name="$1" url="$2"; shift 2
    local code; code="$(status_of "$url")"
    local want
    for want in "$@"; do
        if [[ "$code" == "$want" ]]; then
            ok "${name} (HTTP ${code})"
            return
        fi
    done
    bad "${name}: expected one of [$*], got ${code} from ${url}"
}

echo
log "verifying deployment at ${BASE_URL}"
echo

wait_for_ready || { echo; log "ABORTING: service never became ready"; exit 1; }

echo
log "--- liveness and readiness ---"
# Reverse proxy answers this itself, so it isolates proxy health from upstreams.
check_body_contains "reverse proxy /healthz"      "${BASE_URL}/healthz"             "ok"
check_body_contains "API liveness /health"        "${BASE_URL}/api/v1/health"       '"status":"healthy"'
# Readiness touches the database, so this is the real proof the data tier works.
check_body_contains "API readiness (database up)" "${BASE_URL}/api/v1/readiness"    '"status":"ready"'
check_body_contains "readiness reports db ok"     "${BASE_URL}/api/v1/readiness"    '"database":"ok"'

echo
log "--- frontend delivery ---"
check_status        "frontend index"              "${BASE_URL}/"                    "200"
check_body_contains "frontend HTML shell"         "${BASE_URL}/"                    "<div id=\"root\""
# The SPA fallback must serve index.html for unknown client-side routes rather
# than 404, or a page refresh on a deep link breaks the app.
check_status        "SPA history fallback"        "${BASE_URL}/some/client/route"    "200"

echo
log "--- routing and authentication ---"
# Proves /api reaches the backend rather than falling through to the SPA. An
# unauthenticated call must be rejected, not served: 401/403 is the correct
# answer here and 200 would mean the endpoint lost its auth dependency.
check_status_in     "protected endpoint rejects anonymous access" \
                    "${BASE_URL}/api/v1/sessions/00000000-0000-0000-0000-000000000000" \
                    "401" "403"
# 404 would mean the proxy sent /api to the frontend container.
check_status_in     "unknown API path handled by backend" \
                    "${BASE_URL}/api/v1/definitely-not-a-route" "404"

if [[ "$EXPECT_METRICS_BLOCKED" == "1" ]]; then
    echo
    log "--- metrics exposure (production expectation) ---"
    # /api/v1/metrics has no authentication dependency in the application, so the
    # proxy must be the thing keeping it private.
    check_status_in "metrics not publicly reachable" "${BASE_URL}/api/v1/metrics" "403" "404"
fi

if [[ "$EXPECT_DOCS_BLOCKED" == "1" ]]; then
    echo
    log "--- API docs exposure (production expectation) ---"
    # FastAPI serves docs unconditionally; the proxy must block them publicly.
    check_status_in "interactive docs not public"  "${BASE_URL}/api/v1/docs"         "403" "404"
    check_status_in "OpenAPI schema not public"    "${BASE_URL}/api/v1/openapi.json" "403" "404"
fi

echo
log "--- security headers ---"
headers="$(curl "${CURL_OPTS[@]}" -D - -o /dev/null "${BASE_URL}/" 2>/dev/null || true)"
for header in "x-content-type-options" "x-frame-options" "referrer-policy"; do
    if grep -qi "^${header}:" <<<"$headers"; then
        ok "header ${header} present"
    else
        bad "header ${header} missing"
    fi
done
if [[ "$BASE_URL" == https://* ]]; then
    if grep -qi '^strict-transport-security:' <<<"$headers"; then
        ok "header strict-transport-security present"
    else
        bad "header strict-transport-security missing on an HTTPS deployment"
    fi
else
    warn "HSTS not checked: BASE_URL is not HTTPS (expected for local/dev runs)"
fi

echo
echo "================================================================"
if (( FAIL > 0 )); then
    echo "  ${c_red}HEALTH CHECK FAILED${c_reset}: ${PASS} passed, ${FAIL} failed"
    echo "  The deployment must not be considered live. Roll back."
    echo "================================================================"
    exit 1
fi
echo "  ${c_green}HEALTH CHECK PASSED${c_reset}: ${PASS} checks passed"
echo "================================================================"
exit 0
