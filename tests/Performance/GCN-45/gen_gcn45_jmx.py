#!/usr/bin/env python3
"""Generates GCN45AppointmentPaymentTest.jmx (exactly eight scenarios JM-01..JM-08, plus a non-scored fixture seed 'FX', 'SETUP' and 'ENV' steps)
and scenarios.json (expected sample counts and thresholds read by summarize.py). Contains NO secret: tokens and PayHere signatures are produced at run
time from environment variables (GCN45_JWT_SECRET, GCN45_PAYHERE_SECRET, GCN45_PAYHERE_MERCHANT_ID) set only for the JMeter process.
No script text contains the characters dollar-brace (JMeter would interpolate them); Groovy uses string concatenation."""
import json, os, sys
from xml.sax.saxutils import escape, quoteattr
a = quoteattr
OUT = os.path.dirname(os.path.abspath(__file__))
def ht(x=""): return f"<hashTree>{x}</hashTree>"

# ------------------------------------------------------------------------------------------------ constants
DOCTOR = "d0c70000-0000-4000-8000-000000000045"
def patient(n): return f"ca4e0000-0000-4000-8000-00000000000{n}"
STUB, PORT_A, PORT_B = "5235", "5236", "5237"
BILLING = '{"firstName":"Test","lastName":"Patient","email":"patient@example.test","phone":"0771234567","address":"Test address","city":"Colombo"}'
UNKNOWN_ORDER = "CN-APT-UNKNOWN-QA"
NOTIFY_URL = f"http://localhost:{PORT_A}/api/appointment-payments/payhere/notify"
EXPECT = {}     # scenario -> expected number of samples in the JTL
def reg(sc, n): EXPECT[sc] = EXPECT.get(sc, 0) + n

# ------------------------------------------------------------------------------------------------ JMeter element helpers
def resp_assert(name, field, text, test_type, ignore=False):
    f = {"code": "Assertion.response_code", "body": "Assertion.response_data", "headers": "Assertion.response_headers"}[field]
    return (f'<ResponseAssertion guiclass="AssertionGui" testclass="ResponseAssertion" testname={a(name)} enabled="true">'
            f'<collectionProp name="Asserion.test_strings"><stringProp name="1">{escape(text)}</stringProp></collectionProp>'
            f'<stringProp name="Assertion.custom_message"></stringProp><stringProp name="Assertion.test_field">{f}</stringProp>'
            f'<boolProp name="Assertion.assume_success">{str(ignore).lower()}</boolProp><intProp name="Assertion.test_type">{test_type}</intProp></ResponseAssertion>') + ht()
def code_is(code, name=None):  # exact match; for non-2xx the HTTP "failure" is cleared so the assertion alone decides
    return resp_assert(name or f"Status is {code}", "code", str(code), 8, ignore=not str(code).startswith("2"))
def body_has(text, name=None): return resp_assert(name or f"Body contains: {text[:50]}", "body", text, 16)
def duration(ms, name=None):
    return (f'<DurationAssertion guiclass="DurationAssertionGui" testclass="DurationAssertion" testname={a(name or f"No single response slower than {ms} ms")} enabled="true">'
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

def sampler(label, method, path, body=None, port=PORT_A, asserts=(), pre=(), post=(), auth=None, ctype="json", timers=""):
    args = ""
    if body is not None:
        args = ('<boolProp name="HTTPSampler.postBodyRaw">true</boolProp><elementProp name="HTTPsampler.Arguments" elementType="Arguments"><collectionProp name="Arguments.arguments">'
                f'<elementProp name="" elementType="HTTPArgument"><boolProp name="HTTPArgument.always_encode">false</boolProp><stringProp name="Argument.value">{escape(body)}</stringProp>'
                '<stringProp name="Argument.metadata">=</stringProp></elementProp></collectionProp></elementProp>')
    s = (f'<HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname={a(label)} enabled="true">{args}'
         f'<stringProp name="HTTPSampler.domain">localhost</stringProp><stringProp name="HTTPSampler.port">{port}</stringProp><stringProp name="HTTPSampler.protocol">http</stringProp>'
         f'<stringProp name="HTTPSampler.path">{escape(path)}</stringProp><stringProp name="HTTPSampler.method">{method}</stringProp>'
         '<boolProp name="HTTPSampler.follow_redirects">false</boolProp><boolProp name="HTTPSampler.auto_redirects">false</boolProp><boolProp name="HTTPSampler.use_keepalive">true</boolProp>'
         '<boolProp name="HTTPSampler.DO_MULTIPART_POST">false</boolProp><stringProp name="HTTPSampler.connect_timeout">5000</stringProp><stringProp name="HTTPSampler.response_timeout">30000</stringProp></HTTPSamplerProxy>')
    hdr = []
    if auth: hdr.append(("Authorization", "${__P(tok." + auth + ",MISSING)}"))
    if body is not None: hdr.append(("Content-Type", "application/json" if ctype == "json" else "application/x-www-form-urlencoded"))
    hm = headers("Headers", hdr) if hdr else ""
    return s + ht(hm + "".join(pre) + "".join(asserts) + "".join(post) + timers)

def S(sc, name, method, path, *, mult=1, ctl=False, **kw):
    """Registers the sample in the expected count and builds it. ctl=True marks stub-control calls (excluded from performance thresholds)."""
    reg(sc, mult)
    label = f"{sc} {name}" + (" [ctl]" if ctl else "")
    return sampler(label, method, path, **kw)

def tg(name, comment, threads, ramp, loops, children, kind="ThreadGroup", on_error="continue"):
    gui = {"ThreadGroup": "ThreadGroupGui", "SetupThreadGroup": "SetupThreadGroupGui", "PostThreadGroup": "PostThreadGroupGui"}[kind]
    t = (f'<{kind} guiclass="{gui}" testclass="{kind}" testname={a(name)} enabled="true"><stringProp name="TestPlan.comments">{escape(comment)}</stringProp>'
         f'<stringProp name="ThreadGroup.on_sample_error">{on_error}</stringProp><elementProp name="ThreadGroup.main_controller" elementType="LoopController" guiclass="LoopControlPanel" testclass="LoopController" testname="Loop Controller" enabled="true">'
         f'<boolProp name="LoopController.continue_forever">false</boolProp><stringProp name="LoopController.loops">{loops}</stringProp></elementProp>'
         f'<stringProp name="ThreadGroup.num_threads">{threads}</stringProp><stringProp name="ThreadGroup.ramp_time">{ramp}</stringProp><boolProp name="ThreadGroup.scheduler">false</boolProp>'
         f'<stringProp name="ThreadGroup.duration"></stringProp><stringProp name="ThreadGroup.delay"></stringProp><boolProp name="ThreadGroup.same_user_on_next_iteration">true</boolProp></{kind}>')
    return t + ht("".join(children))
def phase_gate(phase, children):
    cond = "${__groovy(props.get('phase') == '" + phase + "')}"
    return (f'<IfController guiclass="IfControllerPanel" testclass="IfController" testname="Run only in phase {phase}" enabled="true"><stringProp name="IfController.condition">{escape(cond)}</stringProp>'
            '<boolProp name="IfController.evaluateAll">false</boolProp><boolProp name="IfController.useExpression">true</boolProp></IfController>') + ht("".join(children))
def scenario_tg(phase, name, comment, threads, ramp, loops, children):
    return tg(name, comment, threads, ramp, loops, [phase_gate(phase, children)])

# ------------------------------------------------------------------------------------------------ Groovy building blocks (no dollar-brace anywhere)
LIB = r"""
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec
import java.security.MessageDigest
def b64u = { byte[] b -> java.util.Base64.getUrlEncoder().withoutPadding().encodeToString(b) }
def mint = { String secret, String role, String sub, long expOffset ->
  def header = b64u('{"alg":"HS256","typ":"JWT"}'.getBytes('UTF-8'))
  long exp = (long) (System.currentTimeMillis() / 1000L) + expOffset
  def nameId = 'http://schemas.microsoft.com/ws/2008/06/identity/claims/nameidentifier'
  def roleId = 'http://schemas.microsoft.com/ws/2008/06/identity/claims/role'
  def payload = b64u(('{"sub":"' + sub + '","' + nameId + '":"' + sub + '","' + roleId + '":"' + role + '","iss":"CareNova.UserAuth","aud":"CareNova.Client","exp":' + exp + '}').getBytes('UTF-8'))
  def mac = Mac.getInstance('HmacSHA256'); mac.init(new SecretKeySpec(secret.getBytes('UTF-8'), 'HmacSHA256'))
  header + '.' + payload + '.' + b64u(mac.doFinal((header + '.' + payload).getBytes('UTF-8')))
}
def md5 = { String s -> MessageDigest.getInstance('MD5').digest(s.getBytes('UTF-8')).collect { String.format('%02X', it) }.join('') }
def notify = { String order, String amount, String currency, String status, String mode ->
  def mid = System.getenv('GCN45_PAYHERE_MERCHANT_ID'); def sec = System.getenv('GCN45_PAYHERE_SECRET')
  def sig = md5(mid + order + amount + currency + status + md5(sec))
  if (mode == 'badsig') { sig = '0' * 32 }
  def f = [merchant_id: mid, order_id: order, payhere_amount: amount, payhere_currency: currency, status_code: status, payment_id: 'TEST-TXN-' + order]
  if (mode != 'nosig') { f['md5sig'] = sig }
  f.collect { k, v -> k + '=' + java.net.URLEncoder.encode(v, 'UTF-8') }.join('&')
}
"""
def jchk(name, body):
    return jsr("assert", name, "import groovy.json.JsonSlurper\ndef json = new JsonSlurper().parseText(prev.getResponseDataAsString())\ndef fails = []\n"
               "def check = { String what, boolean ok -> if (!ok) { fails << what } }\n" + body +
               "\nif (fails) { AssertionResult.setFailure(true); AssertionResult.setFailureMessage(fails.join('; ')) }")
NOLEAK = jsr("assert", "No stack trace, exception text or internal names in the response",
             "def b = prev.getResponseDataAsString() ?: ''\ndef bad = ['Exception', 'StackTrace', 'Stack trace', ' at AppointmentIntegration', 'Microsoft.EntityFramework', 'MySql', 'Pomelo', 'System.']\n"
             "def hit = bad.find { b.contains(it) }\nif (hit != null) { AssertionResult.setFailure(true); AssertionResult.setFailureMessage('response leaks internal detail: ' + hit) }")
def prop_save(expr_pairs):  # post-processor: save values from the JSON response into JMeter properties
    lines = "import groovy.json.JsonSlurper\ndef json = new JsonSlurper().parseText(prev.getResponseDataAsString())\n"
    for key, expr in expr_pairs: lines += f"props.put('{key}', String.valueOf({expr}))\n"
    return jsr("post", "Remember values for later steps", lines)
def status_in(name, codes_expr, extra=""):
    return jsr("assert", name, "def c = prev.getResponseCode()\nif (!(" + codes_expr + ")) { AssertionResult.setFailure(true); AssertionResult.setFailureMessage('unexpected status ' + c) }\n" + extra)
SLOT_PRE = jsr("pre", "Next unused stub slot", "vars.put('SLOT', String.valueOf(props.get('slotCounter').getAndIncrement()))")
def P(key): return "${__P(" + key + ",MISSING)}"           # for HTTP paths / bodies (JMeter interpolation)
def PG(key): return "props.get('" + key + "')"   # for Groovy code
APPT = lambda key: "/api/appointments/" + P(key) + "/payment"

def book(sc, name, who, save_key, patient_guid, slot_key=None, **kw):
    extra_post = [jsr("post", "Remember the slot used", "props.put('" + slot_key + "', vars.get('SLOT'))")] if slot_key else []
    return S(sc, name, "POST", "/api/appointments", body='{"doctorId":"' + DOCTOR + '","slotId":${SLOT}}', auth=who, pre=[SLOT_PRE],
             asserts=[code_is(201), NOLEAK, jchk("Booking is stored for this patient and slot",
                      "check('id > 0', json.id > 0)\ncheck('status Booked', json.status == 'Booked')\ncheck('patient is the caller', json.patientId == '" + patient_guid + "')\n"
                      "check('slot is the requested slot', String.valueOf(json.slotId) == vars.get('SLOT'))\ncheck('reference', json.appointmentReference.startsWith('CN-APT-'))"),
                      duration(3000)], post=[prop_save([(save_key, "json.id")])] + extra_post, **kw)
def select(sc, name, who, ap_key, method, status, checks="", **kw):
    asserts = [code_is(status), NOLEAK, duration(3000)]
    if checks: asserts.insert(1, jchk("Response content", checks))
    return S(sc, name, "POST", APPT(ap_key) + "/method", body='{"method":"' + method + '"}', auth=who, asserts=asserts, **kw)
PAY_OK = lambda method, status_text, ap_key: ("check('method " + method + "', json.method == '" + method + "')\ncheck('status " + status_text + "', json.status == '" + status_text + "')\n"
                                               "check('amount 2700', new BigDecimal(String.valueOf(json.amount)).compareTo(new BigDecimal('2700')) == 0)\ncheck('appointment id', String.valueOf(json.appointmentId) == " + PG(ap_key) + ")")
def stub(sc, name, query): return S(sc, name, "GET", "/__mode?" + query, port=STUB, ctl=True, asserts=[code_is(200)])
def stub_path(sc, name, path, checks=None):
    return S(sc, name, "GET", path, port=STUB, ctl=True, asserts=[code_is(200)] + ([jchk("Stub counters", checks)] if checks else []))
def notify_sampler(sc, name, order_expr, amount, status, mode, expect, extra_asserts=(), mult=1, timers="", pre_extra=()):
    pre = jsr("pre", "Build the notification (signed with the TEST secret)", LIB + f"vars.put('NB', notify({order_expr}, '{amount}', 'LKR', '{status}', '{mode}'))")
    return S(sc, name, "POST", "/api/appointment-payments/payhere/notify", body="${NB}", ctype="form", mult=mult, timers=timers,
             pre=[pre] + list(pre_extra), asserts=[code_is(expect), duration(3000)] + list(extra_asserts))
def payment_get(sc, name, who, ap_key, checks, mult=1):
    return S(sc, name, "GET", APPT(ap_key), auth=who, mult=mult, asserts=[code_is(200), NOLEAK, jchk("Payment content", checks), duration(3000)])
def attempt_get(sc, name, who, ap_key, attempt_key, status, checks=None, mult=1):
    a_ = [code_is(status), NOLEAK, duration(3000)] + ([jchk("Attempt content", checks)] if checks else [])
    return S(sc, name, "GET", APPT(ap_key) + "/online/" + P(attempt_key), auth=who, mult=mult, asserts=a_)

# ------------------------------------------------------------------------------------------------ SETUP / ENV
setup_script = LIB + r"""
import groovy.json.JsonSlurper
import java.util.concurrent.atomic.AtomicInteger
def phase = props.get('phase')
if (!['seed', 'readonly', 'state', 'concurrent'].contains(phase)) { throw new IllegalStateException('property phase must be seed, readonly, state or concurrent') }
def jwt = System.getenv('GCN45_JWT_SECRET')
if (!jwt || !System.getenv('GCN45_PAYHERE_SECRET') || !System.getenv('GCN45_PAYHERE_MERCHANT_ID')) { throw new IllegalStateException('GCN45_* secrets are not in the environment of the JMeter process') }
def code = { String m, String url -> try { def c = new URL(url).openConnection(); c.requestMethod = m; c.connectTimeout = 3000; c.readTimeout = 8000; c.responseCode } catch (Exception e) { -1 } }
long base = ((long) (System.currentTimeMillis() / 1000L) - 1790000000L) * 100L
if (base < 1 || base > 2000000000L) { throw new IllegalStateException('slot base out of range: ' + base) }
def r = code('GET', 'http://localhost:5235/__mode?mode=ok&slotBase=' + base + '&slotCount=300')
if (r != 200) { throw new IllegalStateException('doctor stub on 5235 is not answering (HTTP ' + r + ')') }
code('GET', 'http://localhost:5235/__reset')
if (code('GET', 'http://localhost:5236/api/appointments/1/payment') != 401) { throw new IllegalStateException('backend A on 5236 is not running with authentication on') }
if (phase == 'state' && code('GET', 'http://localhost:5237/api/appointments/1/payment') != 401) { throw new IllegalStateException('backend B on 5237 is not running') }
props.put('slotCounter', new AtomicInteger((int) base))
def sub = { int n -> 'ca4e0000-0000-4000-8000-00000000000' + n }
for (int n = 1; n <= 8; n++) { props.put('tok.P' + n, 'Bearer ' + mint(jwt, 'Patient', sub(n), 3600L)) }
props.put('tok.STAFF', 'Bearer ' + mint(jwt, 'PharmacyStaff', '5ca1f000-0000-4000-8000-000000000001', 3600L))
props.put('tok.DOCTOR', 'Bearer ' + mint(jwt, 'Doctor', 'd0c70000-0000-4000-8000-000000000045', 3600L))
props.put('tok.ADMIN', 'Bearer ' + mint(jwt, 'Admin', 'ad510000-0000-4000-8000-000000000001', 3600L))
props.put('tok.EXPIRED', 'Bearer ' + mint(jwt, 'Patient', sub(1), -3600L))
props.put('tok.WRONGSECRET', 'Bearer ' + mint('this-is-not-the-signing-secret-0123456789', 'Patient', sub(1), 3600L))
props.put('tok.BADSUB', 'Bearer ' + mint(jwt, 'Patient', 'not-a-guid', 3600L))
props.put('tok.GARBAGE', 'Bearer not-a-jwt')
if (phase != 'seed') {
  def f = new File(props.get('fixturesFile') ?: '')
  if (phase == 'readonly' && !f.exists()) { throw new IllegalStateException('fixtures file missing: run the seed phase first') }
  if (f.exists()) {
    def fx = new JsonSlurper().parseText(f.text)
    props.put('fx.F1.id', String.valueOf(fx.F1.appointmentId)); props.put('fx.F2.id', String.valueOf(fx.F2.appointmentId))
    props.put('fx.F2.attempt', String.valueOf(fx.F2.attemptId)); props.put('fx.F2.order', String.valueOf(fx.F2.gatewayOrderId)); props.put('fx.F3.id', String.valueOf(fx.F3.appointmentId))
  }
}
SampleResult.setResponseData('phase=' + phase + ' slotBase=' + base, 'UTF-8')
SampleResult.setSuccessful(true)
"""
SETUP = tg("SETUP environment and test identities", "Checks the local environment (stub 5235, backend A 5236, backend B 5237 when needed), sets the slot window, mints test tokens, loads fixtures. Stops the run if anything is wrong.",
           1, 0, 1, [jsr("sampler", "SETUP environment check and test tokens", setup_script)], kind="SetupThreadGroup", on_error="stoptest")
reg("SETUP", 1)
TEARDOWN = tg("ENV teardown: doctor stub back to normal", "Always leaves the stub in mode ok, even after a failure.", 1, 0, 1,
              [S("ENV", "teardown stub back to ok", "GET", "/__mode?mode=ok", port=STUB, ctl=True, asserts=[code_is(200)])], kind="PostThreadGroup")

# ------------------------------------------------------------------------------------------------ FX (seed)
FX = scenario_tg("seed", "FX Fixture seeding (not a scored scenario)", "Creates three fixtures through the real API against the stub doctor: F1 Cash selected (P1), F2 gateway selected with attempt 1 started (P1), F3 appointment without payment (P2).", 1, 0, 1, [
    book("FX", "01 book F1 (P1)", "P1", "fx.F1.id", patient(1)),
    select("FX", "02 F1 select Cash", "P1", "fx.F1.id", "Cash", 200, PAY_OK("Cash", "Pending", "fx.F1.id")),
    book("FX", "03 book F2 (P1)", "P1", "fx.F2.id", patient(1)),
    select("FX", "04 F2 select PaymentGateway", "P1", "fx.F2.id", "PaymentGateway", 200, PAY_OK("PaymentGateway", "AwaitingGatewayPayment", "fx.F2.id")),
    S("FX", "05 F2 start online attempt 1", "POST", APPT("fx.F2.id") + "/online/start", body=BILLING, auth="P1",
      asserts=[code_is(200), NOLEAK, jchk("Session", "check('attempt 1', json.attemptNumber == 1)\ncheck('sandbox', json.sandbox == true)"), duration(3000)],
      post=[prop_save([("fx.F2.attempt", "json.attemptId"), ("fx.F2.order", "json.gatewayOrderId")])]),
    book("FX", "06 book F3 (P2)", "P2", "fx.F3.id", patient(2)),
    S("FX", "07 save fixtures file", "GET", "/__stats", port=STUB, ctl=True, asserts=[code_is(200),
      jsr("assert", "Write fixtures.json (appointment ids only, no secrets)",
          "def f = new File(props.get('fixturesFile'))\nf.text = '{\"createdAt\":\"' + new Date().format(\"yyyy-MM-dd'T'HH:mm:ss\") + '\",\"F1\":{\"appointmentId\":' + props.get('fx.F1.id') + '},\"F2\":{\"appointmentId\":' + props.get('fx.F2.id') + ',\"attemptId\":' + props.get('fx.F2.attempt') + ',\"gatewayOrderId\":\"' + props.get('fx.F2.order') + '\"},\"F3\":{\"appointmentId\":' + props.get('fx.F3.id') + '}}'\n"
          "if (!f.exists() || f.length() < 40) { AssertionResult.setFailure(true); AssertionResult.setFailureMessage('fixtures file not written') }")]),
])

# ------------------------------------------------------------------------------------------------ JM-01
jm01 = scenario_tg("readonly", "JM-01 Payment status read under load", "5 users x 20 reads of the same seeded payment (fixture F1, Cash, Pending). Read-only.", 5, 2, 20, [
    payment_get("JM-01", "GET payment F1", "P1", "fx.F1.id",
                "check('appointmentId is F1', String.valueOf(json.appointmentId) == " + PG("fx.F1.id") + ")\ncheck('reference', json.appointmentReference != null && json.appointmentReference.startsWith('CN-APT-'))\n"
                "check('method Cash', json.method == 'Cash')\ncheck('status Pending', json.status == 'Pending')\ncheck('amount 2700', new BigDecimal(String.valueOf(json.amount)).compareTo(new BigDecimal('2700')) == 0)", mult=100)])

# ------------------------------------------------------------------------------------------------ JM-02
MSG404 = "Payment information was not found for this appointment."
def deny(name, auth, status, extra_body=None, path=None, mult=1):
    asserts = [code_is(status), NOLEAK, duration(3000)]
    if extra_body: asserts.insert(1, body_has(extra_body))
    return S("JM-02", name, "GET", path or APPT("fx.F1.id"), auth=auth, asserts=asserts)
jm02 = scenario_tg("readonly", "JM-02 Authorization and ownership on the payment status", "Same GET with every kind of bad or foreign identity. Read-only.", 1, 0, 1, [
    deny("a no token -> 401", None, 401),
    deny("b garbage token -> 401", "GARBAGE", 401),
    deny("c expired token -> 401", "EXPIRED", 401),
    deny("d token signed with another secret -> 401", "WRONGSECRET", 401),
    deny("e subject is not a GUID -> 401 with message", "BADSUB", 401, "A valid patient identity is required."),
    S("JM-02", "f other patient reads F1 -> 404, no data", "GET", APPT("fx.F1.id"), auth="P2", asserts=[code_is(404), body_has(MSG404), NOLEAK,
      jsr("assert", "No payment detail leaks to another patient", "def b = prev.getResponseDataAsString()\nif (b.contains('CN-APT') || b.contains('2700') || b.contains('Cash')) { AssertionResult.setFailure(true); AssertionResult.setFailureMessage('foreign patient got payment detail') }"),
      duration(3000)], post=[jsr("post", "Remember the foreign-patient body", "props.put('jm02.foreign', prev.getResponseDataAsString())")]),
    S("JM-02", "g owner asks for an unknown appointment -> 404 identical body", "GET", "/api/appointments/999999/payment", auth="P1", asserts=[code_is(404), body_has(MSG404), NOLEAK,
      jsr("assert", "Unknown and foreign appointment answer identically (no existence leak)", "if (prev.getResponseDataAsString() != props.get('jm02.foreign')) { AssertionResult.setFailure(true); AssertionResult.setFailureMessage('responses differ: existence of the appointment is revealed') }"),
      duration(3000)]),
    deny("h appointment id 0 -> 404", "P1", 404, path="/api/appointments/0/payment"),
    deny("i appointment id abc -> 404", "P1", 404, path="/api/appointments/abc/payment"),
    S("JM-02", "j owner of F3 (no payment yet) -> 404", "GET", APPT("fx.F3.id"), auth="P2", asserts=[code_is(404), body_has(MSG404), NOLEAK, duration(3000)]),
    S("JM-02", "k staff token on a patient payment -> 404", "GET", APPT("fx.F1.id"), auth="STAFF", asserts=[code_is(404), NOLEAK, duration(3000)]),
])

# ------------------------------------------------------------------------------------------------ JM-03
LIST = "/api/staff/appointment-payments/receipts"
VERIFY = "/api/staff/appointment-payments/appointments/999999/receipt/verify"
def staff_case(name, auth, status, method="GET", path=LIST, body=None):
    return S("JM-03", name, method, path, auth=auth, body=body, asserts=[code_is(status), NOLEAK, duration(3000)])
jm03a = scenario_tg("readonly", "JM-03 Staff authorization (functional)", "Role matrix on the staff endpoints. Read-only.", 1, 0, 1, [
    S("JM-03", "a staff lists receipts -> 200 array", "GET", LIST, auth="STAFF", asserts=[code_is(200), NOLEAK,
      jsr("assert", "Body is a JSON array", "def v = new groovy.json.JsonSlurper().parseText(prev.getResponseDataAsString())\nif (!(v instanceof List)) { AssertionResult.setFailure(true); AssertionResult.setFailureMessage('not a JSON array') }"), duration(3000)]),
    staff_case("b patient -> 403", "P1", 403), staff_case("c doctor -> 403", "DOCTOR", 403), staff_case("d admin -> 403", "ADMIN", 403), staff_case("e anonymous -> 401", None, 401),
    staff_case("f staff verifies unknown appointment -> 404", "STAFF", 404, "POST", VERIFY, '{"approved":true}'),
    staff_case("g patient verifies -> 403", "P1", 403, "POST", VERIFY, '{"approved":true}'),
])
jm03b = scenario_tg("readonly", "JM-03 Staff receipts list under load", "5 users x 20 list reads. Read-only.", 5, 2, 20, [
    S("JM-03", "p staff list receipts (load)", "GET", LIST, auth="STAFF", mult=100, asserts=[code_is(200), NOLEAK, duration(3000)])])

# ------------------------------------------------------------------------------------------------ JM-04
jm04 = scenario_tg("readonly", "JM-04 Online attempt read and webhook rejection", "Reads fixture F2 (gateway selected, attempt 1 pending) and sends only notifications that must be rejected or ignored. No state change.", 1, 0, 1, [
    attempt_get("JM-04", "a owner reads attempt -> 200 Processing", "P1", "fx.F2.id", "fx.F2.attempt", 200,
                "check('outcome Processing', json.outcome == 'Processing')\ncheck('can retry', json.canRetry == true)\ncheck('payment awaiting gateway', json.payment.status == 'AwaitingGatewayPayment')"),
    attempt_get("JM-04", "b other patient -> 404", "P2", "fx.F2.id", "fx.F2.attempt", 404),
    S("JM-04", "c unknown attempt -> 404", "GET", APPT("fx.F2.id") + "/online/999999", auth="P1", asserts=[code_is(404), NOLEAK, duration(3000)]),
    S("JM-04", "d malformed attempt id -> 404", "GET", APPT("fx.F2.id") + "/online/abc", auth="P1", asserts=[code_is(404), NOLEAK, duration(3000)]),
    notify_sampler("JM-04", "e bad md5sig -> 400", PG("fx.F2.order"), "2700.00", "2", "badsig", 400),
    notify_sampler("JM-04", "f missing md5sig -> 400", PG("fx.F2.order"), "2700.00", "2", "nosig", 400),
    S("JM-04", "g body over 64 KB -> 413", "POST", "/api/appointment-payments/payhere/notify", body="${BIGFORM}", ctype="form",
      pre=[jsr("pre", "Build a 70,000 byte form body", "vars.put('BIGFORM', 'order_id=' + ('a' * 70000))")], asserts=[code_is(413), duration(5000)]),
    notify_sampler("JM-04", "h valid signature, unknown order -> 200 ignored", "'" + UNKNOWN_ORDER + "'", "2700.00", "2", "ok", 200),
    payment_get("JM-04", "i F2 payment unchanged", "P1", "fx.F2.id", "check('still PaymentGateway', json.method == 'PaymentGateway')\ncheck('still AwaitingGatewayPayment', json.status == 'AwaitingGatewayPayment')"),
    attempt_get("JM-04", "j F2 attempt unchanged", "P1", "fx.F2.id", "fx.F2.attempt", 200, "check('still Processing', json.outcome == 'Processing')"),
])

# ------------------------------------------------------------------------------------------------ JM-05
def invalid_method(tag, value):
    return S("JM-05", f"{tag} invalid method -> 400", "POST", APPT("jm05.ap1") + "/method", body='{"method":"' + value + '"}', auth="P3",
             asserts=[code_is(400), body_has("Select a valid payment method"), NOLEAK, duration(3000)])
jm05 = scenario_tg("state", "JM-05 Booking, method selection and business rules", "Books through the real API, selects and switches methods, rejects invalid input, double booking, a foreign patient and a zero fee. Writes appointments and payments.", 1, 0, 1, [
    book("JM-05", "a book appointment 1 (P3)", "P3", "jm05.ap1", patient(3), slot_key="jm05.slot1"),
    select("JM-05", "b select Cash", "P3", "jm05.ap1", "Cash", 200, PAY_OK("Cash", "Pending", "jm05.ap1")),
    select("JM-05", "c switch to BankTransfer", "P3", "jm05.ap1", "BankTransfer", 200, PAY_OK("BankTransfer", "AwaitingBankTransferReceipt", "jm05.ap1")),
    payment_get("JM-05", "d read back: BankTransfer persisted", "P3", "jm05.ap1", PAY_OK("BankTransfer", "AwaitingBankTransferReceipt", "jm05.ap1")),
    invalid_method("e1 empty", ""), invalid_method("e2 blank", "   "), invalid_method("e3 Crypto", "Crypto"), invalid_method("e4 numeric 99", "99"),
    S("JM-05", "f other patient selects a method -> 404", "POST", APPT("jm05.ap1") + "/method", body='{"method":"Cash"}', auth="P4", asserts=[code_is(404), NOLEAK, duration(3000)]),
    S("JM-05", "g book the SAME slot again (P4) -> 409", "POST", "/api/appointments", body='{"doctorId":"' + DOCTOR + '","slotId":${__P(jm05.slot1)}}', auth="P4",
      asserts=[code_is(409), body_has("already been booked"), NOLEAK, duration(3000)]),
    stub("JM-05", "h stub: doctor without a consultation fee", "mode=nofee"),
    book("JM-05", "i book appointment 2 (P3)", "P3", "jm05.ap2", patient(3)),
    S("JM-05", "j select Cash with no fee -> 409", "POST", APPT("jm05.ap2") + "/method", body='{"method":"Cash"}', auth="P3",
      asserts=[code_is(409), body_has("consultation fee has not been configured"), NOLEAK, duration(3000)]),
    S("JM-05", "k no payment row was created -> 404", "GET", APPT("jm05.ap2"), auth="P3", asserts=[code_is(404), NOLEAK, duration(3000)]),
    stub("JM-05", "l stub back to normal", "mode=ok"),
])

# ------------------------------------------------------------------------------------------------ JM-06
SESSION_CHECK = LIB + r"""
def sec = System.getenv('GCN45_PAYHERE_SECRET')
check('attempt number', json.attemptNumber == Integer.parseInt(vars.get('EXPECT_ATTEMPT')))
check('sandbox mode', json.sandbox == true)
check('merchant is the TEST merchant', json.merchantId == 'TEST123')
check('amount 2700.00', json.amount == '2700.00')
check('currency LKR', json.currency == 'LKR')
check('order id present', json.gatewayOrderId != null && json.gatewayOrderId.length() > 5)
check('hash is 32 upper-case hex', json.hash ==~ /^[0-9A-F]{32}$/)
check('hash equals MD5(merchant+order+amount+currency+MD5(secret))', json.hash == md5(json.merchantId + json.gatewayOrderId + json.amount + json.currency + md5(sec)))
check('notify url is the local TEST endpoint', json.notifyUrl == 'NOTIFYURL')
""".replace("NOTIFYURL", NOTIFY_URL)
def start_attempt(name, n, ap_key, save_prefix, differs_from=None):
    return S("JM-06", name, "POST", APPT(ap_key) + "/online/start", body=BILLING, auth="P5",
             pre=[jsr("pre", "Expected attempt number", f"vars.put('EXPECT_ATTEMPT', '{n}')")],
             asserts=[code_is(200), NOLEAK, jchk("Checkout session is correct and correctly signed", SESSION_CHECK), duration(3000)]
             + ([jsr("assert", "A retry gets a NEW gateway reference", "def b = new groovy.json.JsonSlurper().parseText(prev.getResponseDataAsString())\nif (b.gatewayOrderId == " + PG(differs_from) + ") { AssertionResult.setFailure(true); AssertionResult.setFailureMessage('the retry reused the gateway reference') }")] if differs_from else []),
             post=[prop_save([(save_prefix + ".attempt", "json.attemptId"), (save_prefix + ".order", "json.gatewayOrderId")])])
jm06 = scenario_tg("state", "JM-06 Online payment lifecycle and duplicate handling", "Gateway payment with the TEST merchant: failure and retry, tampered amount, success, replay, late failure, pay-again and change-method after paid. Writes one appointment, one payment, three attempts.", 1, 0, 1, [
    book("JM-06", "a book appointment (P5)", "P5", "jm06.ap", patient(5)),
    select("JM-06", "b select PaymentGateway", "P5", "jm06.ap", "PaymentGateway", 200, PAY_OK("PaymentGateway", "AwaitingGatewayPayment", "jm06.ap")),
    start_attempt("c start attempt 1", 1, "jm06.ap", "jm06.a1"),
    notify_sampler("JM-06", "d signed FAILED notification for attempt 1 -> 200", PG("jm06.a1.order"), "2700.00", "-2", "ok", 200),
    attempt_get("JM-06", "e attempt 1 is Failed and can be retried", "P5", "jm06.ap", "jm06.a1.attempt", 200, "check('outcome Failed', json.outcome == 'Failed')\ncheck('can retry', json.canRetry == true)\ncheck('payment not successful', json.payment.status != 'Successful')"),
    start_attempt("f start attempt 2 (new reference)", 2, "jm06.ap", "jm06.a2", differs_from="jm06.a1.order"),
    notify_sampler("JM-06", "g signed SUCCESS with a tampered amount (1.00) -> 200", PG("jm06.a2.order"), "1.00", "2", "ok", 200),
    attempt_get("JM-06", "h tampered amount is Failed, not Succeeded", "P5", "jm06.ap", "jm06.a2.attempt", 200, "check('outcome Failed', json.outcome == 'Failed')\ncheck('payment not successful', json.payment.status != 'Successful')"),
    start_attempt("i start attempt 3", 3, "jm06.ap", "jm06.a3"),
    notify_sampler("JM-06", "j signed SUCCESS for attempt 3 -> 200", PG("jm06.a3.order"), "2700.00", "2", "ok", 200),
    attempt_get("JM-06", "k attempt 3 Succeeded and payment Successful", "P5", "jm06.ap", "jm06.a3.attempt", 200, "check('outcome Succeeded', json.outcome == 'Succeeded')\ncheck('payment Successful', json.payment.status == 'Successful')"),
    notify_sampler("JM-06", "l REPLAY of the same success notification -> 200", PG("jm06.a3.order"), "2700.00", "2", "ok", 200),
    payment_get("JM-06", "m payment still Successful after the replay", "P5", "jm06.ap", "check('Successful', json.status == 'Successful')\ncheck('still PaymentGateway', json.method == 'PaymentGateway')"),
    notify_sampler("JM-06", "n late FAILED notification of attempt 1 -> 200", PG("jm06.a1.order"), "2700.00", "-2", "ok", 200),
    payment_get("JM-06", "o a late failure cannot undo the payment", "P5", "jm06.ap", "check('Successful', json.status == 'Successful')"),
    S("JM-06", "p start another attempt after paid -> 409", "POST", APPT("jm06.ap") + "/online/start", body=BILLING, auth="P5", asserts=[code_is(409), body_has("already been paid"), NOLEAK, duration(3000)]),
    select("JM-06", "q change method after paid -> 409", "P5", "jm06.ap", "Cash", 409),
])

# ------------------------------------------------------------------------------------------------ JM-07
INIT_A = jsr("post", "Initialise concurrency counters", "import java.util.concurrent.atomic.AtomicInteger\nprops.put('jm07.a.ok', new AtomicInteger(0)); props.put('jm07.a.conflict', new AtomicInteger(0))")
METHODS = jsr("pre", "Each user asks for a different method", "def m = ['Cash', 'BankTransfer', 'PaymentGateway']\nvars.put('M', m[(ctx.getThreadNum() % 3)])")
jm07_prep_a = scenario_tg("concurrent", "JM-07A prepare", "Books the shared appointment (P6).", 1, 0, 1, [book("JM-07A", "00 book shared appointment (P6)", "P6", "jm07.a.ap", patient(6), )])
jm07_a = scenario_tg("concurrent", "JM-07A same appointment, 5 simultaneous first selections", "5 users released together choose a method on the SAME fresh appointment: never a 500, exactly a consistent single payment.", 5, 0, 1, [
    S("JM-07A", "01 concurrent first selection", "POST", APPT("jm07.a.ap") + "/method", body='{"method":"${M}"}', auth="P6", mult=5, timers=sync(5), pre=[METHODS],
      asserts=[status_in("Only 200 or 409 (never 500)", "c == '200' || c == '409'",
                         "def k = (c == '200') ? 'jm07.a.ok' : 'jm07.a.conflict'\nprops.get(k).incrementAndGet()"), NOLEAK, duration(5000)])])
jm07_a2 = scenario_tg("concurrent", "JM-07A verify", "After the race.", 1, 0, 1, [
    S("JM-07A", "02 read back: one consistent payment, at least one winner", "GET", APPT("jm07.a.ap"), auth="P6", asserts=[code_is(200), NOLEAK,
      jchk("Consistent single payment and counts", "def want = [Cash: 'Pending', BankTransfer: 'AwaitingBankTransferReceipt', PaymentGateway: 'AwaitingGatewayPayment']\ncheck('status matches method', want[json.method] == json.status)\ncheck('amount 2700', new BigDecimal(String.valueOf(json.amount)).compareTo(new BigDecimal('2700')) == 0)\n"
           "def ok = props.get('jm07.a.ok').get(); def conflict = props.get('jm07.a.conflict').get()\ncheck('at least one 200', ok >= 1)\ncheck('every request answered 200 or 409', ok + conflict == 5)"), duration(3000)])])
jm07_prep_b = scenario_tg("concurrent", "JM-07B prepare", "Appointment (P7) with a gateway payment and one started attempt.", 1, 0, 1, [
    book("JM-07B", "00 book appointment (P7)", "P7", "jm07.b.ap", patient(7)),
    S("JM-07B", "01 select PaymentGateway", "POST", APPT("jm07.b.ap") + "/method", body='{"method":"PaymentGateway"}', auth="P7", asserts=[code_is(200), NOLEAK, duration(3000)]),
    S("JM-07B", "02 start attempt", "POST", APPT("jm07.b.ap") + "/online/start", body=BILLING, auth="P7", asserts=[code_is(200), NOLEAK, duration(3000)],
      post=[prop_save([("jm07.b.attempt", "json.attemptId"), ("jm07.b.order", "json.gatewayOrderId")])])])
jm07_b = scenario_tg("concurrent", "JM-07B 5 identical success notifications at once", "The same signed success notification delivered 5 times simultaneously.", 5, 0, 1, [
    notify_sampler("JM-07B", "03 identical signed success notification", PG("jm07.b.order"), "2700.00", "2", "ok", 200, mult=5, timers=sync(5))])
jm07_b2 = scenario_tg("concurrent", "JM-07B verify", "After the burst.", 1, 0, 1, [
    attempt_get("JM-07B", "04 attempt Succeeded, payment Successful", "P7", "jm07.b.ap", "jm07.b.attempt", 200, "check('Succeeded', json.outcome == 'Succeeded')\ncheck('payment Successful', json.payment.status == 'Successful')"),
    payment_get("JM-07B", "05 one Successful payment", "P7", "jm07.b.ap", "check('Successful', json.status == 'Successful')")])
jm07_c = scenario_tg("concurrent", "JM-07C 5 different patients in parallel", "Each user books its own appointment, then all select Cash at the same moment.", 5, 0, 1, [
    S("JM-07C", "01 book own appointment", "POST", "/api/appointments", body='{"doctorId":"' + DOCTOR + '","slotId":${SLOT}}', auth="P${__threadNum}", mult=5, pre=[SLOT_PRE],
      asserts=[code_is(201), NOLEAK, duration(3000)], post=[prop_save([("jm07.c.ap.${__threadNum}".replace("${__threadNum}", "' + ctx.getThreadNum() + '"), "json.id")])]),
    S("JM-07C", "02 select Cash at the same moment", "POST", "/api/appointments/${__P(jm07.c.ap.${__threadNum},MISSING)}/payment/method", body='{"method":"Cash"}', auth="P${__threadNum}", mult=5, timers=sync(5),
      asserts=[code_is(200), NOLEAK, jchk("Cash pending", "check('Cash', json.method == 'Cash')\ncheck('Pending', json.status == 'Pending')"), duration(5000)])])

# ------------------------------------------------------------------------------------------------ JM-08
jm08 = scenario_tg("state", "JM-08 Dependency failure and recovery", "Doctor stub down: graceful error, nothing changed, reads still work, recovery; backend B (PayHere not configured): 503 retryable, backend A: 200. Writes appointments and one attempt.", 1, 0, 1, [
    book("JM-08", "a book appointment (P8)", "P8", "jm08.ap", patient(8)),
    select("JM-08", "b select Cash (baseline payment)", "P8", "jm08.ap", "Cash", 200, PAY_OK("Cash", "Pending", "jm08.ap")),
    stub_path("JM-08", "c stub: reset counters", "/__reset"),
    stub("JM-08", "d stub: doctor service DOWN", "mode=down"),
    S("JM-08", "e select BankTransfer during the outage -> 5xx, fast, no detail", "POST", APPT("jm08.ap") + "/method", body='{"method":"BankTransfer"}', auth="P8",
      asserts=[status_in("Server error class (5xx)", "c.startsWith('5')"), NOLEAK, jchk("A message is returned", "check('message present', json.message != null && json.message.toString().length() > 0)"), duration(5000, "Answer within 5 s during the outage")]),
    payment_get("JM-08", "f read still works during the outage; payment unchanged", "P8", "jm08.ap", PAY_OK("Cash", "Pending", "jm08.ap")),
    stub("JM-08", "g stub: doctor service back", "mode=ok"),
    select("JM-08", "h same request now succeeds (recovery)", "P8", "jm08.ap", "BankTransfer", 200, PAY_OK("BankTransfer", "AwaitingBankTransferReceipt", "jm08.ap")),
    stub_path("JM-08", "i stub: the caller's bearer token was forwarded to the doctor service", "/__stats", "check('lookups happened', json.requests >= 2)\ncheck('every lookup carried the bearer token', json.withoutBearer == 0)"),
    book("JM-08", "j book appointment 2 (P8)", "P8", "jm08.ap2", patient(8)),
    select("JM-08", "k select PaymentGateway", "P8", "jm08.ap2", "PaymentGateway", 200, PAY_OK("PaymentGateway", "AwaitingGatewayPayment", "jm08.ap2")),
    S("JM-08", "l start online payment on backend B (PayHere not configured) -> 503 retryable", "POST", APPT("jm08.ap2") + "/online/start", port=PORT_B, body=BILLING, auth="P8",
      asserts=[code_is(503), NOLEAK, jchk("Retryable", "check('retryable true', json.retryable == true)\ncheck('message present', json.message != null && json.message.toString().length() > 0)"), duration(5000)]),
    S("JM-08", "m same request on backend A -> 200 (recovery)", "POST", APPT("jm08.ap2") + "/online/start", body=BILLING, auth="P8",
      asserts=[code_is(200), NOLEAK, jchk("Sandbox session", "check('sandbox', json.sandbox == true)\ncheck('TEST merchant', json.merchantId == 'TEST123')"), duration(3000)]),
])

# ------------------------------------------------------------------------------------------------ assemble
SAVE = ('<objProp><name>saveConfig</name><value class="SampleSaveConfiguration"><time>true</time><latency>true</latency><timestamp>true</timestamp><success>true</success><label>true</label><code>true</code><message>true</message>'
        '<threadName>true</threadName><dataType>true</dataType><encoding>false</encoding><assertions>true</assertions><subresults>true</subresults><responseData>false</responseData><samplerData>false</samplerData><xml>false</xml>'
        '<fieldNames>true</fieldNames><responseHeaders>false</responseHeaders><requestHeaders>false</requestHeaders><responseDataOnError>false</responseDataOnError><saveAssertionResultsFailureMessage>true</saveAssertionResultsFailureMessage>'
        '<assertionsResultsToSave>0</assertionsResultsToSave><bytes>true</bytes><sentBytes>true</sentBytes><url>true</url><threadCounts>true</threadCounts><idleTime>true</idleTime><connectTime>true</connectTime></value></objProp>')
def listener(gui, name):  # view-only: NO file name, results are written by the command line (-l)
    return (f'<ResultCollector guiclass="{gui}" testclass="ResultCollector" testname={a(name)} enabled="true"><boolProp name="ResultCollector.error_logging">false</boolProp>{SAVE}'
            f'<stringProp name="filename"></stringProp></ResultCollector>') + ht()
SCEN_TGS = [FX, jm01, jm02, jm03a, jm03b, jm04, jm05, jm06, jm07_prep_a, jm07_a, jm07_a2, jm07_prep_b, jm07_b, jm07_b2, jm07_c, jm08]
children = (headers("Accept", [("Accept", "application/json")]) + listener("SummaryReport", "Summary Report") + listener("ViewResultsFullVisualizer", "View Results Tree")
            + SETUP + "".join(SCEN_TGS) + TEARDOWN)
doc = ('<?xml version="1.0" encoding="UTF-8"?>\n<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3"><hashTree><TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="GCN-45 Appointment Payment API (8 scenarios JM-01..JM-08)" enabled="true">'
       '<stringProp name="TestPlan.comments">GCN-45 QA. LOCAL only: backend A localhost:5236, backend B localhost:5237, doctor stub localhost:5235, isolated database carenova_appointment_gcn45_qa. TEST PayHere merchant only. Run per phase with -Jphase=seed|readonly|state|concurrent. No secrets in this file.</stringProp>'
       '<boolProp name="TestPlan.functional_mode">false</boolProp><boolProp name="TestPlan.tearDown_on_shutdown">true</boolProp><boolProp name="TestPlan.serialize_threadgroups">true</boolProp>'
       '<elementProp name="TestPlan.user_defined_variables" elementType="Arguments" guiclass="ArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true"><collectionProp name="Arguments.arguments"/></elementProp>'
       '<stringProp name="TestPlan.user_define_classpath"></stringProp></TestPlan>' + ht(children) + '</hashTree></jmeterTestPlan>\n')
with open(os.path.join(OUT, "GCN45AppointmentPaymentTest.jmx"), "w") as fh: fh.write(doc)

SC = {
 "SETUP": ("Environment check and test identities (not scored)", "setup", "any", EXPECT.get("SETUP", 0)),
 "ENV":   ("Stub reset (not scored)", "setup", "any", EXPECT.get("ENV", 0)),
 "FX":    ("Fixture seeding (not scored)", "write", "seed", EXPECT["FX"]),
 "JM-01": ("Payment status read under load", "read", "readonly", EXPECT["JM-01"]),
 "JM-02": ("Authorization and ownership on payment status", "read", "readonly", EXPECT["JM-02"]),
 "JM-03": ("Staff authorization and receipts list under load", "read", "readonly", EXPECT["JM-03"]),
 "JM-04": ("Online attempt read and webhook rejection", "read", "readonly", EXPECT["JM-04"]),
 "JM-05": ("Booking, method selection and business rules", "write", "state", EXPECT["JM-05"]),
 "JM-06": ("Online payment lifecycle and duplicate handling", "write", "state", EXPECT["JM-06"]),
 "JM-07": ("Concurrency (same appointment, notification burst, parallel patients)", "write", "concurrent", sum(v for k, v in EXPECT.items() if k.startswith("JM-07"))),
 "JM-08": ("Dependency failure and recovery", "write", "state", EXPECT["JM-08"]),
}
THRESH = {"read": {"avg_ms": 300, "p95_ms": 800}, "write": {"avg_ms": 600, "p95_ms": 1500}, "setup": {}}
json.dump({"scenarios": {k: {"name": n, "type": t, "phase": p, "expected_samples": e} for k, (n, t, p, e) in SC.items()}, "thresholds": THRESH,
           "per_sample_hard_cap_ms": 3000, "note": "thresholds are fixed before any run and are never tuned after results"}, open(os.path.join(OUT, "scenarios.json"), "w"), indent=2)
print("wrote JMX and scenarios.json; expected samples:", {k: v[3] for k, v in SC.items()})
