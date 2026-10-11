#!/usr/bin/env python3
"""Generates GCN46PatientAppointmentsTest.jmx (exactly seven scenarios JM-01..JM-07 plus a SETUP check and an ENV observation step) and scenarios.json
(expected sample counts and the PROVISIONAL QA TARGETS read by summarize.py; they are not official product requirements and are never tuned after results).
The plan contains NO secret: tokens are minted at run time inside JMeter from GCN46_JWT_SECRET in the process environment; expected values come from
fixtures/fixtures.json (synthetic, produced by gen_gcn46_fixtures.py from an independent oracle of the documented backend rules).
No script text contains the characters dollar-brace (JMeter would interpolate them); Groovy uses string concatenation."""
import json, os
from xml.sax.saxutils import escape, quoteattr
a = quoteattr
OUT = os.path.dirname(os.path.abspath(__file__))
def ht(x=""): return f"<hashTree>{x}</hashTree>"
PORT = "5246"
EXPECT = {}
def reg(sc, n): EXPECT[sc] = EXPECT.get(sc, 0) + n

# ---------------------------------------------------------------------------------------------------------- JMeter element helpers
def resp_assert(name, field, text, test_type, ignore=False):
    f = {"code": "Assertion.response_code", "body": "Assertion.response_data", "headers": "Assertion.response_headers"}[field]
    return (f'<ResponseAssertion guiclass="AssertionGui" testclass="ResponseAssertion" testname={a(name)} enabled="true">'
            f'<collectionProp name="Asserion.test_strings"><stringProp name="1">{escape(text)}</stringProp></collectionProp>'
            f'<stringProp name="Assertion.custom_message"></stringProp><stringProp name="Assertion.test_field">{f}</stringProp>'
            f'<boolProp name="Assertion.assume_success">{str(ignore).lower()}</boolProp><intProp name="Assertion.test_type">{test_type}</intProp></ResponseAssertion>') + ht()
def code_is(code, name=None): return resp_assert(name or f"Status is {code}", "code", str(code), 8, ignore=not str(code).startswith("2"))
def header_has(text, name=None): return resp_assert(name or f"Header contains: {text}", "headers", text, 16)
def body_has(text, name=None): return resp_assert(name or f"Body contains: {text[:50]}", "body", text, 16)
def duration(ms, name=None):
    return (f'<DurationAssertion guiclass="DurationAssertionGui" testclass="DurationAssertion" testname={a(name or f"No single response slower than {ms} ms (hard cap)")} enabled="true">'
            f'<stringProp name="DurationAssertion.duration">{ms}</stringProp></DurationAssertion>') + ht()
def jsr(kind, name, script):
    assert "${" not in script, "script must not contain dollar-brace"
    tc = {"assert": "JSR223Assertion", "pre": "JSR223PreProcessor", "post": "JSR223PostProcessor", "sampler": "JSR223Sampler"}[kind]
    return (f'<{tc} guiclass="TestBeanGUI" testclass="{tc}" testname={a(name)} enabled="true"><stringProp name="cacheKey">true</stringProp>'
            f'<stringProp name="filename"></stringProp><stringProp name="parameters"></stringProp><stringProp name="script">{escape(script)}</stringProp>'
            f'<stringProp name="scriptLanguage">groovy</stringProp></{tc}>') + ht()
def headers(name, items):
    hs = "".join(f'<elementProp name="" elementType="Header"><stringProp name="Header.name">{escape(k)}</stringProp><stringProp name="Header.value">{escape(v)}</stringProp></elementProp>' for k, v in items)
    return f'<HeaderManager guiclass="HeaderPanel" testclass="HeaderManager" testname={a(name)} enabled="true"><collectionProp name="HeaderManager.headers">{hs}</collectionProp></HeaderManager>' + ht()
def sync(n): return f'<SyncTimer guiclass="TestBeanGUI" testclass="SyncTimer" testname="Release all {n} users together" enabled="true"><intProp name="groupSize">{n}</intProp><longProp name="timeoutInMs">20000</longProp></SyncTimer>' + ht()
def think(ms, rnd): return (f'<UniformRandomTimer guiclass="UniformRandomTimerGui" testclass="UniformRandomTimer" testname="Think time {ms}-{ms + rnd} ms" enabled="true">'
                            f'<stringProp name="ConstantTimer.delay">{ms}</stringProp><stringProp name="RandomTimer.range">{rnd}</stringProp></UniformRandomTimer>') + ht()
def loop(name, n, children):
    return (f'<LoopController guiclass="LoopControlPanel" testclass="LoopController" testname={a(name)} enabled="true"><boolProp name="LoopController.continue_forever">true</boolProp>'
            f'<stringProp name="LoopController.loops">{n}</stringProp></LoopController>') + ht("".join(children))

def sampler(label, path, *, auth=None, asserts=(), pre=(), post=(), timers="", method="GET"):
    s = (f'<HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname={a(label)} enabled="true">'
         f'<stringProp name="HTTPSampler.domain">localhost</stringProp><stringProp name="HTTPSampler.port">{PORT}</stringProp><stringProp name="HTTPSampler.protocol">http</stringProp>'
         f'<stringProp name="HTTPSampler.path">{escape(path)}</stringProp><stringProp name="HTTPSampler.method">{method}</stringProp>'
         '<boolProp name="HTTPSampler.follow_redirects">false</boolProp><boolProp name="HTTPSampler.auto_redirects">false</boolProp><boolProp name="HTTPSampler.use_keepalive">true</boolProp>'
         '<boolProp name="HTTPSampler.DO_MULTIPART_POST">false</boolProp><stringProp name="HTTPSampler.connect_timeout">5000</stringProp><stringProp name="HTTPSampler.response_timeout">30000</stringProp></HTTPSamplerProxy>')
    hm = headers("Authorization", [("Authorization", "${__P(tok." + auth + ",MISSING)}")]) if auth else ""
    return s + ht(hm + "".join(pre) + "".join(asserts) + "".join(post) + timers)
def S(sc, name, path, *, mult=1, **kw):
    reg(sc, mult)
    return sampler(f"{sc} {name}", path, **kw)

def tg(name, comment, threads, ramp, loops, children, kind="ThreadGroup", on_error="continue", seconds=None):
    gui = {"ThreadGroup": "ThreadGroupGui", "SetupThreadGroup": "SetupThreadGroupGui", "PostThreadGroup": "PostThreadGroupGui"}[kind]
    sched = (f'<boolProp name="ThreadGroup.scheduler">true</boolProp><stringProp name="ThreadGroup.duration">{seconds}</stringProp>' if seconds
             else '<boolProp name="ThreadGroup.scheduler">false</boolProp><stringProp name="ThreadGroup.duration"></stringProp>')
    loops_v = "-1" if seconds else loops
    t = (f'<{kind} guiclass="{gui}" testclass="{kind}" testname={a(name)} enabled="true"><stringProp name="TestPlan.comments">{escape(comment)}</stringProp>'
         f'<stringProp name="ThreadGroup.on_sample_error">{on_error}</stringProp><elementProp name="ThreadGroup.main_controller" elementType="LoopController" guiclass="LoopControlPanel" testclass="LoopController" testname="Loop Controller" enabled="true">'
         f'<boolProp name="LoopController.continue_forever">false</boolProp><stringProp name="LoopController.loops">{loops_v}</stringProp></elementProp>'
         f'<stringProp name="ThreadGroup.num_threads">{threads}</stringProp><stringProp name="ThreadGroup.ramp_time">{ramp}</stringProp>{sched}'
         f'<stringProp name="ThreadGroup.delay"></stringProp><boolProp name="ThreadGroup.same_user_on_next_iteration">true</boolProp></{kind}>')
    return t + ht("".join(children))
def gated(phase, name, comment, threads, ramp, loops, children, seconds=None):
    cond = "${__groovy(props.get('phase') == '" + phase + "')}"
    gate = (f'<IfController guiclass="IfControllerPanel" testclass="IfController" testname="Run only in phase {phase}" enabled="true"><stringProp name="IfController.condition">{escape(cond)}</stringProp>'
            '<boolProp name="IfController.evaluateAll">false</boolProp><boolProp name="IfController.useExpression">true</boolProp></IfController>') + ht("".join(children))
    return tg(name, comment, threads, ramp, loops, [gate], seconds=seconds)

# ---------------------------------------------------------------------------------------------------------- Groovy building blocks (no dollar-brace)
MINT = r"""
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec
def b64u = { byte[] b -> java.util.Base64.getUrlEncoder().withoutPadding().encodeToString(b) }
def mint = { String secret, String role, String sub, long expOffset, String iss, String aud, String alg ->
  def header = b64u(('{"alg":"' + alg + '","typ":"JWT"}').getBytes('UTF-8'))
  long exp = (long) (System.currentTimeMillis() / 1000L) + expOffset
  def nameId = 'http://schemas.microsoft.com/ws/2008/06/identity/claims/nameidentifier'
  def roleId = 'http://schemas.microsoft.com/ws/2008/06/identity/claims/role'
  def payload = b64u(('{"sub":"' + sub + '","' + nameId + '":"' + sub + '","' + roleId + '":"' + role + '","iss":"' + iss + '","aud":"' + aud + '","exp":' + exp + '}').getBytes('UTF-8'))
  if (alg == 'none') { return header + '.' + payload + '.' }
  def mac = Mac.getInstance('HmacSHA256'); mac.init(new SecretKeySpec(secret.getBytes('UTF-8'), 'HmacSHA256'))
  header + '.' + payload + '.' + b64u(mac.doFinal((header + '.' + payload).getBytes('UTF-8')))
}
"""
VERIFY = r"""
import groovy.json.JsonSlurper
def REQUIRED = ['id', 'appointmentReference', 'doctorName', 'appointmentStartUtc', 'appointmentEndUtc', 'status', 'section', 'paymentMethod', 'paymentStatus', 'canPay']
def sameInstant = { x, y -> try { java.time.Instant.parse(String.valueOf(x)) == java.time.Instant.parse(String.valueOf(y)) } catch (Exception ex) { false } }
def verifyItem = { Map got, Map e, List fails ->
  def p = 'appointment ' + e.id + ': '
  REQUIRED.each { k -> if (!got.containsKey(k)) { fails << (p + 'missing field ' + k) } }
  if (got.id != e.id) { fails << (p + 'id ' + got.id) }
  if (got.appointmentReference != e.reference) { fails << (p + 'reference ' + got.appointmentReference) }
  if (got.doctorName != e.doctorName) { fails << (p + 'doctor ' + got.doctorName) }
  if (!sameInstant(got.appointmentStartUtc, e.startUtc) || !String.valueOf(got.appointmentStartUtc).endsWith('Z')) { fails << (p + 'start ' + got.appointmentStartUtc) }
  if (!sameInstant(got.appointmentEndUtc, e.endUtc) || !String.valueOf(got.appointmentEndUtc).endsWith('Z')) { fails << (p + 'end ' + got.appointmentEndUtc) }
  if (got.status != e.status) { fails << (p + 'status ' + got.status + ' expected ' + e.status) }
  if (got.section != e.section) { fails << (p + 'section ' + got.section + ' expected ' + e.section) }
  if (got.paymentMethod != e.paymentMethod) { fails << (p + 'paymentMethod ' + got.paymentMethod + ' expected ' + e.paymentMethod) }
  if (got.paymentStatus != e.paymentStatus) { fails << (p + 'paymentStatus ' + got.paymentStatus + ' expected ' + e.paymentStatus) }
  if (got.canPay != e.canPay) { fails << (p + 'canPay ' + got.canPay + ' expected ' + e.canPay) }
}
def verifyList = { List got, String key, List fails, boolean full ->
  def exp = props.get('fx')[key].appointments
  if (got.size() != exp.size()) { fails << ('count ' + got.size() + ' expected ' + exp.size()) }
  def byId = [:]; exp.each { x -> byId[x.id] = x }
  def seen = new HashSet(); def prefix = 'CN-APT-' + key + '-'
  int checked = 0
  got.each { g ->
    if (!seen.add(g.id)) { fails << ('duplicate id ' + g.id) }
    def e = byId[g.id]
    if (e == null) { fails << ('foreign or unknown id ' + g.id) } else if (full || (checked++ < 3)) { verifyItem(g, e, fails) }
    if (!String.valueOf(g.appointmentReference).startsWith(prefix)) { fails << ('reference of another patient: ' + g.appointmentReference) }
  }
  if (!full && seen.size() != exp.size()) { fails << 'id set differs from the expected set' }
}
def finish = { List fails -> if (fails) { AssertionResult.setFailure(true); AssertionResult.setFailureMessage(fails.take(4).join('; ')) } }
"""
def vassert(name, body): return jsr("assert", name, VERIFY + "def fails = []\ndef json = new JsonSlurper().parseText(prev.getResponseDataAsString())\n" + body + "\nfinish(fails)")
LIST_CHECK = "if (!(json instanceof List)) { fails << 'response is not a JSON array' } else { verifyList(json, vars.get('PK'), fails, true) }"
ITEM_CHECK = ("def e = props.get('fx')[vars.get('PK')].appointments[Integer.parseInt(vars.get('IDX'))]\n"
              "if (!(json instanceof Map)) { fails << 'response is not a JSON object' } else { verifyItem(json, e, fails) }")
JSON_CT = header_has("application/json", "Content-Type is JSON")
NOLEAK = jsr("assert", "No appointment data, stack trace or internal names in the response",
             "def b = prev.getResponseDataAsString() ?: ''\ndef bad = ['appointmentReference', 'doctorName', 'CN-APT-', 'Exception', 'StackTrace', 'Stack trace', ' at AppointmentIntegration', 'Microsoft.EntityFramework', 'MySql', 'Pomelo']\n"
             "def hit = bad.find { b.contains(it) }\nif (hit != null) { AssertionResult.setFailure(true); AssertionResult.setFailureMessage('response leaks: ' + hit) }")
def pk_pre(expr, extra=""): return jsr("pre", "Choose patient and appointment", "def n = ctx.getThreadNum()\n" + expr + "\n" + extra)
PK_THREAD = "vars.put('PK', 'L' + String.format('%02d', n + 1))"

# ---------------------------------------------------------------------------------------------------------- SETUP and ENV
SETUP_SCRIPT = MINT + r"""
import groovy.json.JsonSlurper
def phase = props.get('phase')
if (!['functional', 'load'].contains(phase)) { throw new IllegalStateException('property phase must be functional or load') }
def jwt = System.getenv('GCN46_JWT_SECRET')
if (!jwt) { throw new IllegalStateException('GCN46_JWT_SECRET is not in the environment of the JMeter process') }
def code = { String url -> try { def c = new URL(url).openConnection(); c.requestMethod = 'GET'; c.connectTimeout = 3000; c.readTimeout = 8000; c.responseCode } catch (Exception ex) { -1 } }
if (code('http://localhost:5246/api/appointments') != 401) { throw new IllegalStateException('backend on 5246 is not running with authentication on (expected 401 without a token)') }
def f = new File(props.get('fixturesFile') ?: '')
if (!f.exists()) { throw new IllegalStateException('fixtures file missing: generate and seed the synthetic data first') }
def fx = new JsonSlurper().parseText(f.text)
if (java.time.Instant.now().isAfter(java.time.Instant.parse(fx.validUntilUtc))) { throw new IllegalStateException('fixtures are older than 36 hours: upcoming/previous expectations may have drifted; regenerate and re-seed') }
if (fx.synthetic != true) { throw new IllegalStateException('fixtures are not marked synthetic') }
// JsonSlurper returns LAZY maps that are NOT thread-safe: concurrent first reads from several threads can return null (found in run 1, JM-06).
// Materialize everything once, here (single thread), into plain maps and lists that the scenarios only read.
def deep; deep = { x -> x instanceof Map ? x.collectEntries { k, v -> [(k): deep(v)] } : (x instanceof List ? x.collect { deep(it) } : x) }
def patients = deep(fx.patients)
props.put('fx', patients)
props.put('fx.L01.first', String.valueOf(patients['L01'].appointments[0].id))
props.put('jm04.orders', java.util.concurrent.ConcurrentHashMap.newKeySet())
def iss = 'CareNova.UserAuth'; def aud = 'CareNova.Client'
fx.patients.each { k, v -> props.put('tok.' + k, 'Bearer ' + mint(jwt, 'Patient', v.id, 3600L, iss, aud, 'HS256')) }
def l01 = fx.patients['L01'].id
props.put('tok.L01USER', 'Bearer ' + mint(jwt, 'User', l01, 3600L, iss, aud, 'HS256'))
props.put('tok.EXPIRED', 'Bearer ' + mint(jwt, 'Patient', l01, -3600L, iss, aud, 'HS256'))
props.put('tok.WRONGSECRET', 'Bearer ' + mint('this-is-not-the-signing-secret-0123456789', 'Patient', l01, 3600L, iss, aud, 'HS256'))
props.put('tok.WRONGISSUER', 'Bearer ' + mint(jwt, 'Patient', l01, 3600L, 'Other.Issuer', aud, 'HS256'))
props.put('tok.WRONGAUDIENCE', 'Bearer ' + mint(jwt, 'Patient', l01, 3600L, iss, 'Other.Audience', 'HS256'))
props.put('tok.ALGNONE', 'Bearer ' + mint(jwt, 'Patient', l01, 3600L, iss, aud, 'none'))
props.put('tok.BADSUB', 'Bearer ' + mint(jwt, 'Patient', 'not-a-guid', 3600L, iss, aud, 'HS256'))
props.put('tok.EMPTYSUB', 'Bearer ' + mint(jwt, 'Patient', '00000000-0000-0000-0000-000000000000', 3600L, iss, aud, 'HS256'))
props.put('tok.DOCTOR', 'Bearer ' + mint(jwt, 'Doctor', '46e00000-0000-4000-8000-000000000001', 3600L, iss, aud, 'HS256'))
props.put('tok.ADMIN', 'Bearer ' + mint(jwt, 'Admin', '46e00000-0000-4000-8000-000000000002', 3600L, iss, aud, 'HS256'))
props.put('tok.STAFF', 'Bearer ' + mint(jwt, 'PharmacyStaff', '46e00000-0000-4000-8000-000000000003', 3600L, iss, aud, 'HS256'))
props.put('tok.GARBAGE', 'Bearer not-a-jwt')
props.put('tok.BASIC', 'Basic dGVzdDp0ZXN0')
props.put('tok.EMPTY', 'Bearer ')
SampleResult.setResponseData('phase=' + phase + ' patients=' + fx.patients.size() + ' fixtures generated ' + fx.generatedAtUtc, 'UTF-8')
SampleResult.setSuccessful(true)
"""
SETUP = tg("SETUP environment check, fixtures and synthetic tokens", "Checks the local backend on 5246 (401 without a token), loads the synthetic fixtures (and refuses stale ones), mints test tokens from the secret in the process environment. Stops the run if anything is wrong.",
           1, 0, 1, [jsr("sampler", "SETUP environment check, fixtures and synthetic tokens", SETUP_SCRIPT)], kind="SetupThreadGroup", on_error="stoptest")
reg("SETUP", 1)
ENV_SCRIPT = r"""
def dir = props.get('evidenceDir')
def orders = props.get('jm04.orders')
if (dir && orders != null && orders.size() > 0) {
  def f = new File(dir, 'JM-04-order-observation.txt')
  def asc = orders.findAll { o -> o.split(',').collect { Integer.parseInt(it) } == o.split(',').collect { Integer.parseInt(it) }.sort(false) }.size()
  f.text = 'GCN-46 JM-04 ordering observation (not asserted: the backend has no ORDER BY, ordering is not an API guarantee)\n' +
           'distinct id orders seen across all list responses of the edge patient: ' + orders.size() + '\n' + 'of which in ascending id order: ' + asc + '\n'
}
SampleResult.setResponseData('observation written', 'UTF-8'); SampleResult.setSuccessful(true)
"""
ENV = tg("ENV observation (not scored)", "Writes the JM-04 list-order observation. Not an assertion.", 1, 0, 1, [jsr("sampler", "ENV order observation (not scored)", ENV_SCRIPT)], kind="PostThreadGroup")
reg("ENV", 1)

# ---------------------------------------------------------------------------------------------------------- JM-01 .. JM-06
jm01 = gated("functional", "JM-01 Patient appointment list under normal load", "10 users x 30 loops, each user a different synthetic patient (12 appointments each). Read-only.", 10, 5, 30, [
    S("JM-01", "GET /api/appointments (own list)", "/api/appointments", mult=300, auth="${PK}", pre=[pk_pre(PK_THREAD)],
      asserts=[code_is(200), JSON_CT, vassert("The list is exactly this patient's 12 appointments with the seeded values", LIST_CHECK), duration(1500)], timers=think(250, 100))])
jm02 = gated("functional", "JM-02 Patient appointment details under normal load", "10 users x 30 loops, rotating over the patient's own 12 appointment ids. Read-only.", 10, 5, 30, [
    S("JM-02", "GET /api/appointments/{id} (own appointment)", "/api/appointments/${AID}", mult=300, auth="${PK}",
      pre=[pk_pre(PK_THREAD, "int idx = (vars.getIteration() + n) % 12\nvars.put('IDX', String.valueOf(idx))\nvars.put('AID', String.valueOf(props.get('fx')[vars.get('PK')].appointments[idx].id))")],
      asserts=[code_is(200), JSON_CT, vassert("The appointment equals the seeded record", ITEM_CHECK), duration(1500)], timers=think(250, 100))])
jm03 = gated("functional", "JM-03 Concurrent patient appointment list requests", "25 users released together by a synchronizing timer, 4 rounds; 20 distinct patients plus 5 repeats. Read-only.", 25, 0, 4, [
    S("JM-03", "GET /api/appointments (25 simultaneous)", "/api/appointments", mult=100, auth="${PK}", timers=sync(25),
      pre=[pk_pre("vars.put('PK', 'L' + String.format('%02d', (n % 20) + 1))")],
      asserts=[code_is(200), JSON_CT, vassert("Each response is exactly its own patient's data (no cross-contamination)", LIST_CHECK), duration(1500)])])
jm04 = gated("functional", "JM-04 Data integrity and categorization under load", "Edge-case patient S (14 appointments covering every backend rule) read by 5 users x 10 loops: 1 list + 14 details each. Read-only. Order is NOT asserted (no ORDER BY in the backend); it is only observed.", 5, 2, 10, [
    S("JM-04", "list of the edge-case patient", "/api/appointments", mult=50, auth="S",
      pre=[jsr("pre", "Edge-case patient", "vars.put('PK', 'S')\nvars.put('K', '0')")],
      asserts=[code_is(200), JSON_CT, vassert("Every appointment follows the backend rules (section, status, payment labels, canPay, UTC times); unique ids; exact set",
                                              LIST_CHECK + "\nif (json instanceof List) { props.get('jm04.orders').add(json.collect { x -> x.id }.join(',')) }"), duration(1500)]),
    loop("14 details of the edge-case patient", 14, [
        S("JM-04", "details of one edge-case appointment", "/api/appointments/${AID}", mult=700, auth="S",
          pre=[jsr("pre", "Next edge-case appointment", "vars.put('PK', 'S')\nint k = Integer.parseInt(vars.get('K') ?: '0')\nvars.put('IDX', String.valueOf(k))\nvars.put('AID', String.valueOf(props.get('fx')['S'].appointments[k].id))\nvars.put('K', String.valueOf(k + 1))")],
          asserts=[code_is(200), JSON_CT, vassert("The details agree with the backend rules and with the list", ITEM_CHECK), duration(1500)])])], )
LEAK_HDR = header_has("Bearer", "401 carries WWW-Authenticate: Bearer")
def deny401(name, key, path, mult=5): return S("JM-05", name, path, mult=mult, auth=key, asserts=[code_is(401), LEAK_HDR, NOLEAK, duration(1500)])
def deny401_msg(name, key, path, mult=5): return S("JM-05", name, path, mult=mult, auth=key, asserts=[code_is(401), body_has("The token does not identify a valid patient."), NOLEAK, duration(1500)])
def deny403(name, key, path, mult=5): return S("JM-05", name, path, mult=mult, auth=key, asserts=[code_is(403), NOLEAK, duration(1500)])
def jm05_group(path, tag):
    items = [deny401(f"{tag} no token -> 401", None, path)]
    for name, key in (("empty bearer", "EMPTY"), ("garbage token", "GARBAGE"), ("Basic scheme", "BASIC"), ("expired token", "EXPIRED"), ("token signed with another secret", "WRONGSECRET"),
                      ("wrong issuer", "WRONGISSUER"), ("wrong audience", "WRONGAUDIENCE"), ("unsigned token (alg none)", "ALGNONE")):
        items.append(deny401(f"{tag} {name} -> 401", key, path))
    items += [deny401_msg(f"{tag} subject is not a GUID -> 401", "BADSUB", path), deny401_msg(f"{tag} empty GUID subject -> 401", "EMPTYSUB", path),
              deny403(f"{tag} Doctor role -> 403", "DOCTOR", path), deny403(f"{tag} Admin role -> 403", "ADMIN", path), deny403(f"{tag} PharmacyStaff role -> 403", "STAFF", path)]
    return items
L01_FIRST = "vars.put('PK', 'L01')\nvars.put('IDX', '0')"
jm05 = gated("functional", "JM-05 Missing, invalid or expired authentication token handling", "1 user x 5 loops: 9 rejected credentials (401 + WWW-Authenticate), 2 invalid identities (401 + message), 3 other roles (403), and 2 valid controls (Patient, legacy User) on both endpoints. Read-only.", 1, 0, 5,
    jm05_group("/api/appointments", "list") + [
        S("JM-05", "list control: valid Patient token -> 200", "/api/appointments", mult=5, auth="L01", pre=[jsr("pre", "Patient L01", "vars.put('PK', 'L01')")], asserts=[code_is(200), vassert("Control returns exactly L01's data", LIST_CHECK), duration(1500)]),
        S("JM-05", "list control: legacy User role -> 200", "/api/appointments", mult=5, auth="L01USER", pre=[jsr("pre", "Patient L01", "vars.put('PK', 'L01')")], asserts=[code_is(200), vassert("Control returns exactly L01's data", LIST_CHECK), duration(1500)])]
    + jm05_group("/api/appointments/${L01ID}", "details") + [
        S("JM-05", "details control: valid Patient token -> 200", "/api/appointments/${L01ID}", mult=5, auth="L01", pre=[jsr("pre", "Patient L01 first appointment", L01_FIRST)], asserts=[code_is(200), vassert("Control returns the seeded record", ITEM_CHECK), duration(1500)]),
        S("JM-05", "details control: legacy User role -> 200", "/api/appointments/${L01ID}", mult=5, auth="L01USER", pre=[jsr("pre", "Patient L01 first appointment", L01_FIRST)], asserts=[code_is(200), vassert("Control returns the seeded record", ITEM_CHECK), duration(1500)])])
# the details group needs the id of L01's first appointment as a variable for the path: set once per thread before the first details sampler
jm05 = jm05.replace('<stringProp name="HTTPSampler.path">/api/appointments/${L01ID}</stringProp>', '<stringProp name="HTTPSampler.path">/api/appointments/${__P(fx.L01.first,MISSING)}</stringProp>')
OTHER_REFS = ("def other = vars.get('OTHER')\ndef b = prev.getResponseDataAsString() ?: ''\nprops.get('fx')[other].appointments.each { x -> if (b.contains(x.reference)) { AssertionResult.setFailure(true); AssertionResult.setFailureMessage('response contains data of ' + other + ': ' + x.reference) } }")
NOT_FOUND_SAME = jsr("assert", "404 body is IDENTICAL to the body for a never-existing id (no existence leak)", "if (prev.getResponseDataAsString() != vars.get('UNKNOWN_BODY')) { AssertionResult.setFailure(true); AssertionResult.setFailureMessage('different body for a foreign id than for an unknown id: ' + prev.getResponseDataAsString()) }")
jm06 = gated("functional", "JM-06 Cross-patient data isolation", "Patients A and B (two users each, running at the same time) request each other's appointment ids and lists. Zero leaks tolerated. Read-only.", 4, 0, 5, [
    S("JM-06", "unknown appointment id 999999 -> 404", "/api/appointments/999999", mult=20, auth="${OWN}",
      pre=[jsr("pre", "Who is who (threads alternate A and B)", "def n = ctx.getThreadNum()\nvars.put('OWN', (n % 2 == 0) ? 'A' : 'B')\nvars.put('OTHER', (n % 2 == 0) ? 'B' : 'A')")],
      asserts=[code_is(404), body_has('"message":"Appointment not found."', "Standard not-found message"), NOLEAK, duration(1500)],
      post=[jsr("post", "Remember the not-found body", "vars.put('UNKNOWN_BODY', prev.getResponseDataAsString())")]),
    S("JM-06", "own list contains only own data", "/api/appointments", mult=20, auth="${OWN}", pre=[jsr("pre", "Own patient", "vars.put('PK', vars.get('OWN'))")],
      asserts=[code_is(200), vassert("Exactly the own 12 appointments; no reference of the other patient", LIST_CHECK), jsr("assert", "No data of the other patient", OTHER_REFS), duration(1500)]),
    loop("each of the other patient's 12 appointment ids", 12, [
        S("JM-06", "other patient's appointment id -> 404", "/api/appointments/${XID}", mult=240, auth="${OWN}",
          pre=[jsr("pre", "Next foreign id", "int k = Integer.parseInt(vars.get('XK') ?: '0')\nvars.put('XID', String.valueOf(props.get('fx')[vars.get('OTHER')].appointments[k % 12].id))\nvars.put('XK', String.valueOf(k + 1))")],
          asserts=[code_is(404), NOT_FOUND_SAME, jsr("assert", "No data of the other patient", OTHER_REFS), duration(1500)])]),
    S("JM-06", "appointment id of an unrelated load patient -> 404", "/api/appointments/${YID}", mult=20, auth="${OWN}",
      pre=[jsr("pre", "Foreign id of L05", "vars.put('YID', String.valueOf(props.get('fx')['L05'].appointments[0].id))")], asserts=[code_is(404), NOT_FOUND_SAME, duration(1500)]),
    S("JM-06", "Doctor token on an own-patient id -> 403", "/api/appointments/${ZID}", mult=20, auth="DOCTOR",
      pre=[jsr("pre", "Own first id", "vars.put('ZID', String.valueOf(props.get('fx')[vars.get('OWN')].appointments[0].id))")], asserts=[code_is(403), NOLEAK, duration(1500)]),
])

# ---------------------------------------------------------------------------------------------------------- JM-07
JM07_PRE = r"""
def n = ctx.getThreadNum()
def r = new Random()
def key = 'L' + String.format('%02d', (n % 20) + 1)
def roll = r.nextInt(100)
vars.put('PK', key)
if (roll < 10) { vars.put('KIND', 'BIG'); vars.put('PATH', '/api/appointments'); vars.put('AUTHKEY', 'BIG') }
else if (roll < 50) { vars.put('KIND', 'LIST'); vars.put('PATH', '/api/appointments'); vars.put('AUTHKEY', key) }
else { int idx = r.nextInt(12); vars.put('KIND', 'ITEM'); vars.put('IDX', String.valueOf(idx)); vars.put('AUTHKEY', key); vars.put('PATH', '/api/appointments/' + props.get('fx')[key].appointments[idx].id) }
"""
JM07_CHECK = ("def kind = vars.get('KIND')\nif (kind == 'ITEM') { " + ITEM_CHECK.replace("\n", "\n  ") + " }\n"
              "else if (!(json instanceof List)) { fails << 'response is not a JSON array' }\n"
              "else if (kind == 'BIG') { verifyList(json, 'BIG', fails, false) }\nelse { verifyList(json, vars.get('PK'), fails, true) }")
def jm07_step(tag, name, users, ramp, seconds):
    sc = "JM-07"
    reg(sc, 0)
    return gated("load", f"JM-07{tag} {name}", f"{users} users for {seconds} s, think time 200-300 ms, mix: 10% large-history list (200 appointments), 40% own list, 50% own details. Read-only.", users, ramp, 0, [
        sampler(f"JM-07{tag} {name}", "${PATH}", auth="${AUTHKEY}", pre=[jsr("pre", "Choose request", JM07_PRE)],
                asserts=[code_is(200), JSON_CT, vassert("Content matches the seeded data", JM07_CHECK), duration(5000, "No single response slower than 5000 ms (hard cap)")], timers=think(200, 100))], seconds=seconds)
JM07 = [jm07_step("a", "baseline", 5, 2, 45), jm07_step("b", "increased load", 10, 5, 60), jm07_step("c", "peak load", 20, 5, 60), jm07_step("d", "recovery", 5, 2, 45)]

# ---------------------------------------------------------------------------------------------------------- assemble
SAVE = ('<objProp><name>saveConfig</name><value class="SampleSaveConfiguration"><time>true</time><latency>true</latency><timestamp>true</timestamp><success>true</success><label>true</label><code>true</code><message>true</message>'
        '<threadName>true</threadName><dataType>true</dataType><encoding>false</encoding><assertions>true</assertions><subresults>true</subresults><responseData>false</responseData><samplerData>false</samplerData><xml>false</xml>'
        '<fieldNames>true</fieldNames><responseHeaders>false</responseHeaders><requestHeaders>false</requestHeaders><responseDataOnError>false</responseDataOnError><saveAssertionResultsFailureMessage>true</saveAssertionResultsFailureMessage>'
        '<assertionsResultsToSave>0</assertionsResultsToSave><bytes>true</bytes><sentBytes>true</sentBytes><url>true</url><threadCounts>true</threadCounts><idleTime>true</idleTime><connectTime>true</connectTime></value></objProp>')
def listener(gui, name): return (f'<ResultCollector guiclass="{gui}" testclass="ResultCollector" testname={a(name)} enabled="true"><boolProp name="ResultCollector.error_logging">false</boolProp>{SAVE}<stringProp name="filename"></stringProp></ResultCollector>') + ht()
children = headers("Accept", [("Accept", "application/json")]) + listener("SummaryReport", "Summary Report") + listener("ViewResultsFullVisualizer", "View Results Tree") + SETUP + jm01 + jm02 + jm03 + jm04 + jm05 + jm06 + "".join(JM07) + ENV
doc = ('<?xml version="1.0" encoding="UTF-8"?>\n<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3"><hashTree><TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="GCN-46 Patient Appointments API (7 scenarios JM-01..JM-07)" enabled="true">'
       '<stringProp name="TestPlan.comments">GCN-46 QA. LOCAL only: backend localhost:5246, isolated database carenova_appointment_gcn46_qa, synthetic patients. Read-only GET requests. Run per phase with -Jphase=functional (JM-01..JM-06) or -Jphase=load (JM-07). Thresholds are provisional QA targets, not product requirements. No secrets in this file.</stringProp>'
       '<boolProp name="TestPlan.functional_mode">false</boolProp><boolProp name="TestPlan.tearDown_on_shutdown">true</boolProp><boolProp name="TestPlan.serialize_threadgroups">true</boolProp>'
       '<elementProp name="TestPlan.user_defined_variables" elementType="Arguments" guiclass="ArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true"><collectionProp name="Arguments.arguments"/></elementProp>'
       '<stringProp name="TestPlan.user_define_classpath"></stringProp></TestPlan>' + ht(children) + '</hashTree></jmeterTestPlan>\n')
with open(os.path.join(OUT, "GCN46PatientAppointmentsTest.jmx"), "w") as fh: fh.write(doc)

TARGET = "provisional QA target, not an official product requirement"
SC = {
 "SETUP": {"name": "Environment check, fixtures, tokens (not scored)", "phase": "any", "expected": EXPECT["SETUP"]},
 "ENV":   {"name": "Ordering observation (not scored)", "phase": "any", "expected": EXPECT["ENV"]},
 "JM-01": {"name": "Patient appointment list under normal load", "phase": "functional", "expected": EXPECT["JM-01"], "avg_ms": 150, "p95_ms": 400},
 "JM-02": {"name": "Patient appointment details under normal load", "phase": "functional", "expected": EXPECT["JM-02"], "avg_ms": 100, "p95_ms": 300},
 "JM-03": {"name": "Concurrent patient appointment list requests", "phase": "functional", "expected": EXPECT["JM-03"], "avg_ms": 400, "p95_ms": 800},
 "JM-04": {"name": "Data integrity and categorization under load", "phase": "functional", "expected": EXPECT["JM-04"], "avg_ms": 200, "p95_ms": 500},
 "JM-05": {"name": "Missing, invalid or expired token handling", "phase": "functional", "expected": EXPECT["JM-05"], "avg_ms": 100, "p95_ms": 300, "kind": "authorization"},
 "JM-06": {"name": "Cross-patient data isolation", "phase": "functional", "expected": EXPECT["JM-06"], "avg_ms": 150, "p95_ms": 400, "kind": "isolation"},
 "JM-07": {"name": "Increased load and recovery", "phase": "load", "kind": "load", "steps": {
     "JM-07a": {"name": "baseline (5 users, 45 s)", "min_samples": 500, "avg_ms": 150, "p95_ms": 400, "max_error_pct": 0},
     "JM-07b": {"name": "increased (10 users, 60 s)", "min_samples": 1200, "p95_ms": 1500, "max_error_pct": 1},
     "JM-07c": {"name": "peak (20 users, 60 s; first run capped at 20)", "min_samples": 2400, "p95_ms": 3000, "max_error_pct": 1},
     "JM-07d": {"name": "recovery (5 users, 45 s)", "min_samples": 500, "max_error_pct": 0, "recovery_p95": "max(500 ms, 1.5 x baseline p95)"}}},
}
json.dump({"targets_label": TARGET, "note": "Thresholds are fixed before any run and are never tuned after results. Content/isolation assertion failures (HTTP 200 with wrong data) are always FAIL regardless of the error-rate allowance.",
           "per_sample_hard_cap_ms": {"functional": 1500, "load": 5000}, "scenarios": SC}, open(os.path.join(OUT, "scenarios.json"), "w"), indent=2)
print("wrote JMX and scenarios.json; expected samples:", {k: v.get("expected") for k, v in SC.items() if "expected" in v})
