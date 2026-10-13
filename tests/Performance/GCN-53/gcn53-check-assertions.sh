#!/usr/bin/env bash
# Offline: compiles every Groovy script of the plan and runs the plan's own assertion scripts against correct and corrupted responses. No JMeter run, no HTTP, no server, no database.
set -u -o pipefail
. "$(dirname "$0")/gcn53-common.sh"
LIB="$(brew --prefix jmeter 2>/dev/null)/libexec/lib"; [ -d "$LIB" ] || gcn53_die "JMeter libraries not found (brew install jmeter)"
JAVA="$(brew --prefix openjdk@21 2>/dev/null)/bin/java"; [ -x "$JAVA" ] || JAVA="$(command -v java)"      # Groovy 3 needs Java 21 or older
CP="$(ls "$LIB"/groovy*-3.*.jar | tr '\n' ':')"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
FX="${1:-}"; if [ -z "$FX" ]; then python3 "$GCN53_DIR/gen_gcn53_fixtures.py" --out-dir "$T/fx" >/dev/null || gcn53_die "fixture generation failed"; FX="$T/fx/fixtures.json"; fi
python3 "$GCN53_DIR/gcn53_extract_scripts.py" "$GCN53_DIR/GCN53AdminDashboardTest.jmx" "$T/src" || exit 1
n=0; for f in "$T"/src/*.groovy; do "$JAVA" -cp "$CP" groovy.ui.GroovyMain -e "new GroovyShell().parse(new File('$f'))" >/dev/null 2>&1 || gcn53_die "script does not compile: $(basename "$f")"; n=$((n+1)); done; echo "$n Groovy scripts compile"
GCN53_JWT_SECRET="offline-dummy-secret-for-token-structure-checks-only" "$JAVA" -cp "$CP" groovy.ui.GroovyMain "$GCN53_DIR/gcn53_assertion_harness.groovy" "$FX" "$T/src"
