#!/usr/bin/env bash
# STATIC validation of the GCN-46 helper scripts, fixtures generator, summarizer and JMeter plan. It only READS files (and writes to a temp folder):
# it executes none of the helper scripts, connects to no database and sends no request.
set -u
D="$(cd "$(dirname "$0")" && pwd)"; cd "$D" || exit 1
V="$(basename "$0")"
SH="gcn46-common.sh gcn46-make-test-secrets.sh gcn46-create-database.sh gcn46-preview-migrations.sh gcn46-apply-migrations.sh gcn46-seed-fixtures.sh start-gcn46-env.sh stop-gcn46-env.sh gcn46-validate-env.sh run-gcn46-jmeter.sh gcn46-db-evidence.sh"
PY="gen_gcn46_fixtures.py gen_gcn46_jmx.py summarize.py gcn46_monitor.py gcn46_token.py"
FAIL=0; SKIPPED=0; ok() { printf '  PASS  %s\n' "$1"; }; bad() { printf '  FAIL  %s\n' "$1"; FAIL=$((FAIL+1)); }
code() { grep -vE '^[[:space:]]*#' "$@"; }
chk() { local label="$1" pat="$2"; if code $SH | grep -nE "$pat" >/dev/null 2>&1; then bad "$label: $(code $SH | grep -nE "$pat" | head -3 | tr '\n' ' ')"; else ok "$label"; fi; }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
echo "1. Syntax"
for f in $SH; do bash -n "$f" 2>/dev/null && ok "bash -n $f" || bad "bash -n $f"; done
for f in $PY; do python3 -m py_compile "$f" 2>/dev/null && ok "python compile $f" || bad "python compile $f"; done; rm -rf __pycache__
echo "2. Destructive commands (code lines only, comments excluded)"
chk "no DROP DATABASE / USER / TABLE" 'DROP[[:space:]]+(DATABASE|USER|TABLE|SCHEMA)'
chk "no DELETE FROM / TRUNCATE / UPDATE statements" '(DELETE[[:space:]]+FROM|TRUNCATE[[:space:]]+TABLE|UPDATE[[:space:]]+[A-Za-z`])'
chk "no rm -r / rm -rf" 'rm[[:space:]]+-[a-zA-Z]*r'
chk "no mysqldump, no git commit/push/add/reset/checkout/clean" '(mysqldump|git[[:space:]]+(commit|push|add|reset|checkout|clean))'
chk "no dotnet ef database drop/update" 'dotnet[[:space:]]+ef[[:space:]]+database'
chk "no IF NOT EXISTS on CREATE DATABASE / USER (an existing one must stop the run)" 'CREATE[[:space:]]+(DATABASE|USER)[[:space:]]+IF'
echo "3. Isolation from GCN-45, GCN-49 and shared databases"
if code $SH | grep -vE 'GCN46_PROTECTED_PORTS=|\*gcn45\*|ISOLATION FAILED|GCN45(AppointmentPayments|AppointmentReceipts|OnlinePaymentAttempts)|Untouched:|info  port' | grep -nE '(gcn45|GCN-45|GCN45|carenova_appointment_qa|carenova_appointment_integration|carenova_pharmacy|carenova_user|carenova_doctor|5235|5236|5237|5136|5199)' >/dev/null; then bad "a GCN-45 / shared name or port appears in a code line: $(code $SH | grep -vE 'GCN46_PROTECTED_PORTS=|\*gcn45\*|ISOLATION FAILED|GCN45(AppointmentPayments|AppointmentReceipts|OnlinePaymentAttempts)|Untouched:|info  port' | grep -nE '(gcn45|GCN-45|GCN45|carenova_appointment_qa|5235|5236|5237|5136|5199)' | head -3 | tr '\n' ' ')"; else ok "GCN-45 / shared names and ports appear only in the protection lists and refusal guards"; fi
grep -q 'readonly GCN46_DB_NAME="carenova_appointment_gcn46_qa"' gcn46-common.sh && grep -q 'readonly GCN46_DB_USER="gcn46_qa"' gcn46-common.sh && grep -q 'readonly GCN46_PORT=5246' gcn46-common.sh && ok "database, user and port are readonly constants with the approved values" || bad "approved constants missing"
grep -q 'carenova-gcn46-secrets' gcn46-common.sh && grep -q 'carenova-gcn46-run' gcn46-common.sh && ok "own secrets and run folders (not the GCN-45 ones)" || bad "folder constants"
chk "no mysql connection with an inline password" '(--password|[[:space:]]-p[A-Za-z0-9]{3,}|Password=[A-Za-z0-9]+;)'
chk "no kill/stop that mentions a protected port" '(kill|pkill|killall)[^#]*(3000|5136|5199|5235|5236|5237)'
echo "4. Process termination"
chk "no pkill / killall / kill -9 / kill by lsof" '(pkill|killall|kill[[:space:]]+-9|kill[^#]*lsof)'
grep -q 'case "\$cmd" in \*"AppointmentIntegration.Api.dll"\*)' stop-gcn46-env.sh && ok "stop script verifies the command line of the pid before SIGTERM" || bad "stop script has no command-line check"
grep -q 'never stops anything' start-gcn46-env.sh && ok "start script refuses a busy port instead of stopping its owner" || bad "start script port policy"
grep -q 'StopTestNow' gcn46_monitor.py && ! grep -qE 'os\.kill|killall|pkill|signal\.' gcn46_monitor.py && ok "the monitor stops JMeter only through its own control port (UDP), never by killing a process" || bad "monitor uses a kill"
echo "5. Secret exposure"
chk "no echo/printf of a secret variable" '(echo|printf)[^#|>]*\$\{?(GCN46_JWT_SECRET|GCN46_DB_PASSWORD|MYSQL_PWD)'
chk "no set -x / bash -x tracing" '(set[[:space:]]+-[a-z]*x|bash[[:space:]]+-x)'
chk "no secret passed as 'env VAR=...' argument" 'env[[:space:]]+[A-Za-z_]*(SECRET|PASSWORD|Password)'
grep -q 'gcn46_assert_outside_git "\$GCN46_SECRET_DIR"' gcn46-common.sh && grep -q 'GCN46_SECRETS_DIR' gcn46-common.sh && ok "secrets live outside every git work tree (guard in code, folder configurable with GCN46_SECRETS_DIR)" || bad "secret location guard"
if grep -rEl '[0-9a-f]{40,}' . --include='*.sh' --include='*.py' --include='*.md' --include='*.example' >/dev/null 2>&1; then bad "long hex string (possible secret) in: $(grep -rEl '[0-9a-f]{40,}' . --include='*.sh' --include='*.py' --include='*.md' --include='*.example' | tr '\n' ' ')"; else ok "no long hex strings (possible secrets) in scripts, docs or config example"; fi
grep -qE 'eyJ[A-Za-z0-9_-]{20,}' GCN46PatientAppointmentsTest.jmx && bad "a JWT is embedded in the JMX" || ok "no token or secret value in the JMX (only environment variable names)"
grep -q 'GCN46_JWT_SECRET' GCN46PatientAppointmentsTest.jmx && ok "the plan reads the signing secret from the process environment" || bad "plan does not use the environment secret"
[ -f .gitignore ] && grep -q '^results/' .gitignore && ok ".gitignore keeps results, logs, evidence and generated fixtures out of git" || bad ".gitignore missing"
echo "6. Seed data and fixture generator"
python3 gen_gcn46_fixtures.py --out-dir "$T/fx" --now 2026-10-12T08:00:00Z > "$T/gen.txt" 2>&1 && ok "generator self-test and generation: $(tail -1 "$T/gen.txt" | cut -c1-110)" || bad "fixture generation failed"
. ./gcn46-common.sh 2>/dev/null
gcn46_seed_is_insert_only "$T/fx/seed-gcn46.sql" && ok "seed SQL contains only INSERT INTO Appointments / AppointmentPayments plus transaction control" || bad "seed SQL is not insert-only"
gcn46_sql_is_safe "$T/fx/seed-gcn46.sql" && ok "seed SQL passes the forbidden-statement scan" || bad "seed SQL forbidden statement"
printf 'DELETE FROM `Appointments`;\n' > "$T/neg.sql"; if ! gcn46_seed_is_insert_only "$T/neg.sql" >/dev/null && ! gcn46_sql_is_safe "$T/neg.sql" >/dev/null; then ok "negative control: a DELETE statement is rejected by BOTH scans"; else bad "negative control: a DELETE statement was not rejected by both scans"; fi
python3 - "$T/fx/fixtures.json" <<'PY' && ok "fixtures are synthetic: all patients 46a0..., references CN-APT-*, no real names or emails" || bad "fixtures contain non-synthetic looking data"
import json, re, sys
d = json.load(open(sys.argv[1])); assert d["synthetic"] is True
for p in d["patients"].values():
    assert p["id"].startswith("46a00000-"), p["id"]
    for a in p["appointments"]: assert a["reference"].startswith("CN-APT-") and a["doctorName"].startswith("Dr Synthetic") and "@" not in json.dumps(a)
PY
echo "7. JMeter plan"
python3 - <<'PY' && ok "plan structure (hosts, ports, methods, scenarios JM-01..JM-07, phase gates, JM-07 peak = 20)" || bad "plan structure"
import json, xml.etree.ElementTree as ET, sys
t = ET.parse("GCN46PatientAppointmentsTest.jmx"); root = t.getroot()
hosts, ports, methods, paths = set(), set(), set(), []
for e in root.iter("HTTPSamplerProxy"):
    g = {c.get("name"): c.text for c in e}; hosts.add(g["HTTPSampler.domain"]); ports.add(g["HTTPSampler.port"]); methods.add(g["HTTPSampler.method"]); paths.append(g["HTTPSampler.path"])
print("    samplers:", len(paths), "hosts:", sorted(hosts), "ports:", sorted(ports), "methods:", sorted(methods))
assert hosts == {"localhost"} and ports == {"5246"} and methods == {"GET"}, "plan must target only localhost:5246 and send only GET"
assert not any("payment" in p.lower() for p in paths), "no payment endpoint may be used"
sc = json.load(open("scenarios.json"))["scenarios"]; ids = sorted(k for k in sc if k.startswith("JM-"))
assert ids == [f"JM-0{i}" for i in range(1, 8)], ids
names = [e.get("testname") for e in root.iter("ThreadGroup")]
for i in range(1, 8): assert any(n.startswith(f"JM-0{i}") for n in names), f"thread group for JM-0{i} missing"
assert sum(1 for e in root.iter("IfController") if "phase functional" in e.get("testname")) == 6 and sum(1 for e in root.iter("IfController") if "phase load" in e.get("testname")) == 4
assert sc["JM-07"]["steps"]["JM-07c"]["min_samples"] > 0 and "20 users" in sc["JM-07"]["steps"]["JM-07c"]["name"], "JM-07 peak must be capped at 20 users"
peak = [e for e in root.iter("ThreadGroup") if e.get("testname").startswith("JM-07c")][0]
assert [c.text for c in peak if c.get("name") == "ThreadGroup.num_threads"][0] == "20"
print("    thread groups:", len(names), "| phase gates: 6 functional + 4 load | JM-07 peak threads: 20")
PY
txt="$(cat GCN46PatientAppointmentsTest.jmx)"; for s in "payhere" "localhost:5136" "localhost:5199" "localhost:523" ":3000/" "carenova_appointment_qa" "gcn45"; do case "$txt" in *"$s"*) bad "plan mentions $s";; *) ok "plan does not mention $s";; esac; done
grep -qE 'name="HTTPSampler.method">(POST|PUT|PATCH|DELETE)' GCN46PatientAppointmentsTest.jmx && bad "plan contains a write method" || ok "plan contains no write method (every HTTP sampler is GET)"
# --- Java and Groovy: find a JVM between 11 and 21 (JMeter's bundled Groovy 3 does not run on newer Java) and JMeter's libraries, wherever they are installed
JMLIB=""; for c in "${JMETER_HOME:-/nonexistent}/lib" "${JMETER_HOME:-/nonexistent}/libexec/lib"; do [ -d "$c" ] && JMLIB="$c" && break; done
if [ -z "$JMLIB" ] && command -v jmeter >/dev/null 2>&1; then
  real="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$(command -v jmeter)")"; base="$(dirname "$(dirname "$real")")"
  for c in "$base/lib" "$base/libexec/lib"; do [ -d "$c" ] && JMLIB="$c" && break; done
fi
major() { "$1" -version 2>&1 | sed -nE 's/.*version "([0-9]+)(\.([0-9]+))?.*/\1/p;s/.*version "1\.([0-9]+).*/\1/p' | head -1; }
JAVA=""; for c in "${GCN46_JAVA:-}" "${JAVA_HOME:+$JAVA_HOME/bin/java}" "$( /usr/libexec/java_home -v 21 2>/dev/null | sed 's|$|/bin/java|')" "$( /usr/libexec/java_home -v 17 2>/dev/null | sed 's|$|/bin/java|')" "$(command -v java 2>/dev/null)"; do
  [ -n "$c" ] && [ -x "$c" ] || continue; m="$(major "$c")"; if [ -n "$m" ] && [ "$m" -ge 11 ] && [ "$m" -le 21 ]; then JAVA="$c"; break; fi
done
if [ -n "$JAVA" ] && [ -n "$JMLIB" ] && ls "$JMLIB"/groovy-*.jar >/dev/null 2>&1; then
  mkdir -p "$T/g/src" "$T/g/out"; python3 - "$T/g/src" <<'PY'
import sys, xml.etree.ElementTree as ET
n = 0
for el in ET.parse("GCN46PatientAppointmentsTest.jmx").iter():
    if el.tag.startswith("JSR223"): n += 1; open(f"{sys.argv[1]}/s{n:03d}.groovy", "w").write([c.text for c in el if c.get("name") == "script"][0] or "")
print("   ", n, "embedded Groovy scripts extracted")
PY
  "$JAVA" -cp "$(ls $JMLIB/groovy-*.jar | tr '\n' ':')" org.codehaus.groovy.tools.FileSystemCompiler -d "$T/g/out" "$T/g/src"/*.groovy >"$T/groovy.txt" 2>&1 && ok "all embedded Groovy scripts compile (Java $(major "$JAVA") + the Groovy shipped with JMeter)" || { bad "Groovy compile errors"; head -5 "$T/groovy.txt"; }
else printf '  SKIP  Groovy compile NOT verified: needs a Java 11-21 runtime (set GCN46_JAVA or JAVA_HOME) and JMeter libraries (set JMETER_HOME or put jmeter on PATH)\n'; SKIPPED=$((SKIPPED+1)); fi

echo "8. Portability (no machine-specific content in the shipped files)"
ME="$(id -un)"; HOST="$(hostname -s 2>/dev/null || hostname)"
SHIPPED="$(ls -1 | grep -vE '^(results|logs|evidence|fixtures|__pycache__)$' | grep -vxF "$V")"   # the validator is excluded from the pattern scans (it contains the patterns) and checked separately below
scan() { local label="$1" pat="$2"; local hits; hits="$(grep -rnIE -- "$pat" $SHIPPED 2>/dev/null | head -3)"; [ -z "$hits" ] && ok "$label" || bad "$label: $(echo "$hits" | cut -c1-120 | tr '\n' ' ')"; }
# positive control: the same patterns must DETECT a planted violation (proves the scans cannot pass vacuously)
PC="$T/pc"; mkdir -p "$PC"; printf 'x=/Users/someone/project\ny=/opt/homebrew/bin/jmeter\nz=~/carenova/qa-reports/a\nk=eyJabcdefghijklmnopqrstuvwx.abcdefghijkl\nPassword=hunter2xx;\n' > "$PC/planted.txt"
pc() { grep -qE -- "$1" "$PC/planted.txt"; }
pc '(/Users/[A-Za-z0-9._-]+|/home/[a-z][A-Za-z0-9._-]+)' && pc '(/opt/homebrew|/usr/local/Cellar|/var/folders|\.dotnet8)' && pc '(qa-reports|~/carenova|\$HOME/carenova)' && pc 'eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}' && pc 'Password=[^;$"[:space:]]{4,};' && ok "positive control: the portability and secret patterns detect planted violations" || bad "positive control failed: a scan pattern would miss a violation"
scan "no absolute home paths (/Users/..., /home/...)" '(/Users/[A-Za-z0-9._-]+|/home/[a-z][A-Za-z0-9._-]+)'
scan "no Homebrew, SDK or temp-folder paths (/opt/homebrew, /usr/local/Cellar, /var/folders, .dotnet8)" '(/opt/homebrew|/usr/local/Cellar|/var/folders|\.dotnet8)'
scan "no QA-workspace path (qa-reports) and no '~/carenova' paths" '(qa-reports|~/carenova|\$HOME/carenova)'
[ -n "$ME" ] && scan "no local user name ($ME) in any file" "$ME"
[ -n "$HOST" ] && scan "no host name ($HOST) in any file" "$HOST"
( [ -n "$ME" ] && ! grep -qF -- "$ME" "$V" && { [ -z "$HOST" ] || ! grep -qF -- "$HOST" "$V"; } ) && ok "the validator itself contains no user or host name" || bad "the validator contains a user or host name"
grep -q 'stat -c' gcn46-common.sh && grep -q "stat -f" gcn46-common.sh && ok "file modes read through one portable helper (GNU stat -c, BSD stat -f)" || bad "portable stat helper missing"
grep -q 'BASH_SOURCE' gcn46-common.sh && grep -q 'rev-parse --show-toplevel' gcn46-common.sh && ok "paths resolve relative to the script's own location and the git root" || bad "relative path resolution missing"
grep -rn 'dirname "\$0"' $SH 2>/dev/null | grep -q . && ok "every script locates gcn46-common.sh relative to itself" || bad "scripts do not locate the library relatively"
for f in $SH; do case "$f" in gcn46-common.sh) ;; *) grep -q 'gcn46-common.sh' "$f" || bad "$f does not source the common library";; esac; done
python3 - <<'PY' && ok "the plan has no absolute file names (only property-driven paths)" || bad "the plan contains an absolute path"
import re, sys
t = open("GCN46PatientAppointmentsTest.jmx").read(); names = re.findall(r'name="filename">([^<]*)<', t)
sys.exit(1 if any(n.strip() for n in names) else 0)
PY

echo "9. Dependencies (tools the suite calls)"
for tool in bash python3 git jmeter java dotnet mysql openssl curl lsof; do
  if command -v "$tool" >/dev/null 2>&1; then printf '  PASS  %-8s %s\n' "$tool" "$(command -v "$tool")" | sed "s|$HOME|~|"; else printf '  WARN  %-8s not found (needed to RUN the suite, not for this static check)\n' "$tool"; fi
done
(dotnet ef --version >/dev/null 2>&1) && ok "dotnet-ef available" || printf '  WARN  dotnet-ef not available (needed only for gcn46-preview-migrations.sh: dotnet tool install --global dotnet-ef --version 8.0.11)\n'
need=$(grep -ohE '\b(jmeter|dotnet|mysql|openssl|curl|lsof|python3|git)\b' $SH | sort -u | tr '\n' ' '); echo "  info  tools referenced by the scripts: $need"

echo "10. Shipped content (what git would add)"
EXPECTED=".gitignore GCN-46-QA-Findings.md GCN46PatientAppointmentsTest.jmx README.md config/gcn46.properties.example gcn46-apply-migrations.sh gcn46-common.sh gcn46-create-database.sh gcn46-db-evidence.sh gcn46-make-test-secrets.sh gcn46-preview-migrations.sh gcn46-seed-fixtures.sh gcn46-validate-env.sh gcn46_monitor.py gcn46_token.py gen_gcn46_fixtures.py gen_gcn46_jmx.py run-gcn46-jmeter.sh scenarios.json start-gcn46-env.sh stop-gcn46-env.sh summarize.py validate-gcn46-helpers.sh"
if git -C "$D" rev-parse --is-inside-work-tree >/dev/null 2>&1; then ACTUAL="$(cd "$D" && git ls-files --cached --others --exclude-standard . | sort | tr '\n' ' ')"; else ACTUAL="$(cd "$D" && find . -type f -not -path './results/*' -not -path './logs/*' -not -path './evidence/*' -not -name '*.jtl' | sed 's|^\./||' | sort | tr '\n' ' ')"; fi
EXP_SORTED="$(echo $EXPECTED | tr ' ' '\n' | sort | tr '\n' ' ')"
if [ "$ACTUAL" = "$EXP_SORTED" ]; then ok "exactly the 23 intended files would be added; nothing else (no results, logs, evidence, fixtures, tokens, dumps, screenshots)"; else bad "unexpected or missing files. extra/missing: $(diff <(echo "$EXP_SORTED" | tr ' ' '\n') <(echo "$ACTUAL" | tr ' ' '\n') | grep '^[<>]' | tr '\n' ' ')"; fi
bad_files="$(cd "$D" && git ls-files --cached --others --exclude-standard . 2>/dev/null | grep -iE '\.(jtl|trx|log|png|jpg|pid|env|bak|sql|dump)$|^(results|logs|evidence|fixtures)/' | tr '\n' ' ')"
[ -z "$bad_files" ] && ok "no .jtl/.trx/.log/.png/.sql/.env/.pid files and no results, logs, evidence or fixtures folders would be committed" || bad "generated or sensitive file types would be committed: $bad_files"
if git -C "$D" rev-parse --is-inside-work-tree >/dev/null 2>&1; then notign=""; for gp in results/x.jtl logs/x.log evidence/x.txt fixtures/fixtures.json fixtures/seed-gcn46.sql gcn46-migrations-preview.sql x.env jmeter.log; do git -C "$D" check-ignore -q -- "$gp" 2>/dev/null || notign="$notign $gp"; done
[ -z "$notign" ] && ok "the suite .gitignore ignores results, logs, evidence, generated fixtures, migration preview, .env and .log files" || bad "not git-ignored:$notign"
else printf '  SKIP  .gitignore effect not verified: this folder is not inside a git work tree (the .gitignore file itself is shipped)\n'; SKIPPED=$((SKIPPED+1)); fi
pat='(eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}|Password=[^;$"[:space:]]{4,};|-----BEGIN [A-Z ]*PRIVATE KEY|[0-9a-f]{40,})'
hits="$(grep -rnIE "$pat" $SHIPPED 2>/dev/null | head -3)"; [ -z "$hits" ] && ok "no JWT, literal connection-string password, private key or long hex secret in any shipped file" || bad "possible secret: $(echo "$hits" | cut -c1-100 | tr '\n' ' ')"
SF="$(ls -d "${GCN46_SECRETS_DIR:-}"/gcn46-test.env 2>/dev/null || ls "$(getconf DARWIN_USER_DIR 2>/dev/null)carenova-gcn46-secrets/gcn46-test.env" 2>/dev/null || true)"
if [ -n "$SF" ] && [ -f "$SF" ]; then
  leaked=0; while IFS='=' read -r k v; do case "$k" in \#*|"") continue;; esac; [ ${#v} -ge 8 ] && grep -rqIF -- "$v" $SHIPPED 2>/dev/null && leaked=$((leaked+1)); done < "$SF"
  [ "$leaked" = 0 ] && ok "none of the actual local secret values (from the secrets file) appears in any shipped file" || bad "$leaked actual secret value(s) found in shipped files"
else printf '  SKIP  actual-secret scan not run: no local secrets file on this machine\n'; SKIPPED=$((SKIPPED+1)); fi

echo; [ "$SKIPPED" = 0 ] || echo "$SKIPPED check(s) were SKIPPED (not verified, see above)"; [ "$FAIL" = 0 ] && echo "ALL CHECKS PASSED" || echo "$FAIL CHECK(S) FAILED"; exit "$FAIL"
