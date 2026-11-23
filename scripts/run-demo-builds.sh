#!/usr/bin/env bash
# Runs the remaining demo builds one after another and saves the evidence for the report
# in ~/aceest-evidence/, so the screenshots can be taken afterwards.
#
#   bash run-demo-builds.sh            # from part C: rollback demo, then the final green build
#   bash run-demo-builds.sh --from-b   # also part B first: a normal build showing every strategy
#
# Then show a saved result with:  cat ~/aceest-evidence/<file>.txt   and take the screenshot.
set -euo pipefail

JENKINS_URL="${JENKINS_URL:-http://localhost:8080}"
JOB_NAME="${JOB_NAME:-aceest-fitness-2025tm93178}"
REPO_DIR="${REPO_DIR:-$HOME/ACEest-Fitness-Gym-Devops}"
OUT="${OUT:-$HOME/aceest-evidence}"
JOB_URL="$JENKINS_URL/job/$JOB_NAME"
FROM_B=0
case "${1:-}" in
    --from-b) FROM_B=1 ;;
    "") ;;
    *) echo "usage: bash run-demo-builds.sh [--from-b]" >&2; exit 1 ;;
esac

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[32mok\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }
json() { python3 -c "import sys,json; d=json.load(sys.stdin); print($1)"; }

[ -d "$REPO_DIR" ] || git clone -q https://github.com/2025tm93178/ACEest-Fitness-Gym-Devops.git "$REPO_DIR"
cd "$REPO_DIR"
git pull -q || true
mkdir -p "$OUT"

read -rp "Jenkins username [cloud]: " JUSER; JUSER="${JUSER:-cloud}"
read -rsp "Jenkins password: " JPASS; echo

COOKIES="$(mktemp)"; trap 'rm -f "$COOKIES"' EXIT
jcurl() { curl -s -g -u "$JUSER:$JPASS" -b "$COOKIES" -c "$COOKIES" "$@"; }
crumb() { jcurl "$JENKINS_URL/crumbIssuer/api/json" 2>/dev/null \
          | json 'd["crumbRequestField"] + ":" + d["crumb"]' 2>/dev/null || true; }
[ "$(jcurl "$JENKINS_URL/whoAmI/api/json" | json 'd.get("authenticated") and not d.get("anonymous")' 2>/dev/null)" = True ] \
    || die "Jenkins login failed for '$JUSER'"

build() {  # build "PARAM=value&..." "description" -> waits; sets NUM and RESULT
    local h loc n=""
    h="$(crumb)"
    loc="$(jcurl ${h:+-H "$h"} -X POST -D - -o /dev/null "$JOB_URL/buildWithParameters?$1" \
           | tr -d '\r' | awk 'tolower($1) == "location:" {print $2}' | sed -E 's#^https?://[^/]+##')"
    [ -n "$loc" ] || die "Jenkins did not start the build"
    for _ in $(seq 1 120); do
        n="$(jcurl "$JENKINS_URL${loc%/}/api/json" | json '(d.get("executable") or {}).get("number", "")' 2>/dev/null || true)"
        [ -n "$n" ] && break
        sleep 5
    done
    [ -n "$n" ] || die "the build stayed in the queue"
    NUM="$n"
    printf '    build #%s (%s) running' "$NUM" "$2"
    while :; do
        sleep 15; printf '.'
        [ "$(jcurl "$JOB_URL/$NUM/api/json?tree=building" | json 'd["building"]' 2>/dev/null)" = False ] && break
    done
    RESULT="$(jcurl "$JOB_URL/$NUM/api/json?tree=result" | json 'd["result"]')"
    echo " $RESULT"
}

save() {  # save NAME "command" ...  -> runs each command, shows it and saves it as a terminal transcript
    local f="$OUT/$1.txt"; shift
    : > "$f"
    for c in "$@"; do
        { echo "[$(whoami)@$(hostname -s) ACEest-Fitness-Gym-Devops]\$ $c"; bash -c "$c" 2>&1 || true; echo; } | tee -a "$f"
    done
    ok "saved $f"
}

# ---------------------------------------------------------------- part B (optional)
if [ "$FROM_B" = 1 ]; then
    step "B. Normal build: a new version through every strategy"
    save fig09-bluegreen-before "curl -s http://bluegreen.aceest.local/version"
    build "DEPLOY_STRATEGY=all" "all strategies"
    [ "$RESULT" = SUCCESS ] || die "build #$NUM failed: $JOB_URL/$NUM/console"
    sleep 20   # let the ingress pick up the new endpoints
    save fig08-rolling          "curl -s http://rolling.aceest.local/version"
    save fig09-bluegreen-after  "curl -s http://bluegreen.aceest.local/version"
    save fig10-canary-traffic   "python3 k8s/deployctl.py traffic canary --ip \$(minikube ip) --count 50"
    save fig11-ab-testing       "curl -s http://ab.aceest.local/version" \
                                "curl -s -H 'X-Variant: B' http://ab.aceest.local/version"
    save fig12-shadow           "curl -s http://shadow.aceest.local/version" \
                                "python3 k8s/deployctl.py status"
    B_NUM="$NUM"
fi

# ---------------------------------------------------------------- part C
step "C. Rollback demo: canary with a simulated failure (this build goes red on purpose)"
build "DEPLOY_STRATEGY=canary&SIMULATE_FAILURE=true" "canary + SIMULATE_FAILURE"
C_NUM="$NUM"
[ "$RESULT" = FAILURE ] || die "expected the demo build #$C_NUM to fail, got $RESULT: $JOB_URL/$C_NUM/console"
{
    echo "Jenkins build #$C_NUM console (rollback part): $JOB_URL/$C_NUM/console"
    echo
    jcurl "$JOB_URL/$C_NUM/consoleText" \
        | grep -E "deployctl.py deploy|== canary|smoke (attempt|test failed)|ROLLING BACK|rollback complete|!! " \
        | grep -v "smoke ok"
} | tee "$OUT/fig13a-rollback-console.txt"
grep -q "rollback complete" "$OUT/fig13a-rollback-console.txt" \
    || die "the console of build #$C_NUM has no rollback; check $JOB_URL/$C_NUM/console"
ok "saved $OUT/fig13a-rollback-console.txt"
save fig13c-after-rollback "python3 k8s/deployctl.py status"

# ---------------------------------------------------------------- part D
step "D. Final build: everything green again"
build "DEPLOY_STRATEGY=all" "all strategies"
D_NUM="$NUM"
[ "$RESULT" = SUCCESS ] || die "build #$D_NUM failed: $JOB_URL/$D_NUM/console"
save fig07-final-cluster "python3 k8s/deployctl.py status" "kubectl get pods,svc,ingress -n aceest"
jcurl "$JOB_URL/api/json?tree=builds[number,result,displayName]{0,10}" \
    | json '"\n".join("#{:<4} {:<8} {}".format(b["number"], b["result"] or "RUNNING", b["displayName"]) for b in d["builds"])' \
    | tee "$OUT/extra-build-history.txt"
ok "saved $OUT/extra-build-history.txt"

# ---------------------------------------------------------------- what to screenshot
cat <<EOF

==> All builds done. Evidence is in $OUT/

  Show a file with  cat $OUT/<name>.txt  and take the screenshot:
$(ls "$OUT" | sed 's/^/    /')

  In Jenkins ($JOB_URL):
    Fig 13a/13b : build #$C_NUM -> Console Output (rollback lines) and the Stage View (red Deploy stage)
    Fig 3       : Stage View showing build #$D_NUM all green
    Extra       : build history ($( [ "$FROM_B" = 1 ] && echo "#$B_NUM ok, " )#$C_NUM failed on purpose, #$D_NUM ok)
  Docker Hub (Fig 6): https://hub.docker.com/r/2025tm93178anwesa/aceest-fitness/tags
EOF
