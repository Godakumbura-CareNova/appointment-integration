#!/usr/bin/env python3
"""Generates GCN48AppointmentCancellationTest.jmx and scenarios.json: EXACTLY five scenarios JM-01..JM-05, EXACTLY five HTTP samplers (one per scenario, one thread, one iteration).
HOW THE "NO EXTRA HTTP REQUEST" RULE IS MET: there is no setup, authentication, health-check or teardown sampler and no JSR223 *sampler* at all. Everything that is not the
five requests (local JWT minting, fixture loading and the environment sanity flag) happens inside JSR223 PRE-processors attached to the five samplers and is never an HTTP call.
The plan contains NO secret: tokens are minted at run time from GCN48_JWT_SECRET in the JMeter process environment.
No script text contains the characters dollar-brace (JMeter would interpolate them); Groovy uses string concatenation."""
import json, os
from xml.sax.saxutils import escape, quoteattr
a = quoteattr
OUT = os.path.dirname(os.path.abspath(__file__))
PORT = "5248"
def ht(x=""): return f"<hashTree>{x}</hashTree>"

def resp_assert(name, field, text, test_type, ignore=False):
    f = {"code": "Assertion.response_code", "body": "Assertion.response_data", "headers": "Assertion.response_headers"}[field]
    return (f'<ResponseAssertion guiclass="AssertionGui" testclass="ResponseAssertion" testname={a(name)} enabled="true"><collectionProp name="Asserion.test_strings"><stringProp name="1">{escape(text)}</stringProp></collectionProp>'
            f'<stringProp name="Assertion.custom_message"></stringProp><stringProp name="Assertion.test_field">{f}</stringProp><boolProp name="Assertion.assume_success">{str(ignore).lower()}</boolProp>'
            f'<intProp name="Assertion.test_type">{test_type}</intProp></ResponseAssertion>') + ht()
def code_is(code): return resp_assert(f"HTTP status is exactly {code}", "code", str(code), 8, ignore=not str(code).startswith("2"))
def header_has(text, name): return resp_assert(name, "headers", text, 16)
def duration(ms): return (f'<DurationAssertion guiclass="DurationAssertionGui" testclass="DurationAssertion" testname="Sanity cap: answered within {ms} ms (NOT a performance claim)" enabled="true">'
                          f'<stringProp name="DurationAssertion.duration">{ms}</stringProp></DurationAssertion>') + ht()
def jsr(kind, name, script):
    assert "${" not in script, "script must not contain dollar-brace"
    tc = {"assert": "JSR223Assertion", "pre": "JSR223PreProcessor", "post": "JSR223PostProcessor"}[kind]      # deliberately NO JSR223 sampler: it would add a sample
    return (f'<{tc} guiclass="TestBeanGUI" testclass="{tc}" testname={a(name)} enabled="true"><stringProp name="cacheKey">true</stringProp><stringProp name="filename"></stringProp>'
            f'<stringProp name="parameters"></stringProp><stringProp name="script">{escape(script)}</stringProp><stringProp name="scriptLanguage">groovy</stringProp></{tc}>') + ht()
def headers(items):
    hs = "".join(f'<elementProp name="" elementType="Header"><stringProp name="Header.name">{escape(k)}</stringProp><stringProp name="Header.value">{escape(v)}</stringProp></elementProp>' for k, v in items)
    return f'<HeaderManager guiclass="HeaderPanel" testclass="HeaderManager" testname="Headers" enabled="true"><collectionProp name="HeaderManager.headers">{hs}</collectionProp></HeaderManager>' + ht()

def sampler(label, method, path, body=None, children=()):
    args = ""
    if body is not None:
        args = ('<boolProp name="HTTPSampler.postBodyRaw">true</boolProp><elementProp name="HTTPsampler.Arguments" elementType="Arguments"><collectionProp name="Arguments.arguments">'
                f'<elementProp name="" elementType="HTTPArgument"><boolProp name="HTTPArgument.always_encode">false</boolProp><stringProp name="Argument.value">{escape(body)}</stringProp>'
                '<stringProp name="Argument.metadata">=</stringProp></elementProp></collectionProp></elementProp>')
    s = (f'<HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname={a(label)} enabled="true">{args}'
         f'<stringProp name="HTTPSampler.domain">localhost</stringProp><stringProp name="HTTPSampler.port">{PORT}</stringProp><stringProp name="HTTPSampler.protocol">http</stringProp>'
         f'<stringProp name="HTTPSampler.path">{escape(path)}</stringProp><stringProp name="HTTPSampler.method">{method}</stringProp>'
         '<boolProp name="HTTPSampler.follow_redirects">false</boolProp><boolProp name="HTTPSampler.auto_redirects">false</boolProp><boolProp name="HTTPSampler.use_keepalive">true</boolProp>'
         '<boolProp name="HTTPSampler.DO_MULTIPART_POST">false</boolProp><boolProp name="HTTPSampler.image_parser">false</boolProp>'
         '<stringProp name="HTTPSampler.connect_timeout">5000</stringProp><stringProp name="HTTPSampler.response_timeout">30000</stringProp></HTTPSamplerProxy>')
    return s + ht("".join(children))

def thread_group(name, comment, children):     # one thread, one iteration, no ramp, no scheduler
    return (f'<ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname={a(name)} enabled="true"><stringProp name="TestPlan.comments">{escape(comment)}</stringProp>'
            '<stringProp name="ThreadGroup.on_sample_error">continue</stringProp><elementProp name="ThreadGroup.main_controller" elementType="LoopController" guiclass="LoopControlPanel" testclass="LoopController" testname="Loop Controller" enabled="true">'
            '<boolProp name="LoopController.continue_forever">false</boolProp><stringProp name="LoopController.loops">1</stringProp></elementProp>'
            '<stringProp name="ThreadGroup.num_threads">1</stringProp><stringProp name="ThreadGroup.ramp_time">0</stringProp><boolProp name="ThreadGroup.scheduler">false</boolProp>'
            '<stringProp name="ThreadGroup.duration"></stringProp><stringProp name="ThreadGroup.delay"></stringProp><boolProp name="ThreadGroup.same_user_on_next_iteration">true</boolProp></ThreadGroup>') + ht("".join(children))

# ------------------------------------------------------------------------------------------------ Groovy: local JWT, fixtures, environment sanity (pre-processor, never HTTP)
LIB = r"""
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec
import groovy.json.JsonSlurper
def b64u = { byte[] b -> java.util.Base64.getUrlEncoder().withoutPadding().encodeToString(b) }
def mint = { String secret, String role, String sub ->
  def header = b64u('{"alg":"HS256","typ":"JWT"}'.getBytes('UTF-8'))
  long exp = (long) (System.currentTimeMillis() / 1000L) + 900L
  def nameId = 'http://schemas.microsoft.com/ws/2008/06/identity/claims/nameidentifier'
  def roleId = 'http://schemas.microsoft.com/ws/2008/06/identity/claims/role'
  def payload = b64u(('{"sub":"' + sub + '","' + nameId + '":"' + sub + '","' + roleId + '":"' + role + '","iss":"CareNova.UserAuth","aud":"CareNova.Client","exp":' + exp + '}').getBytes('UTF-8'))
  def mac = Mac.getInstance('HmacSHA256'); mac.init(new SecretKeySpec(secret.getBytes('UTF-8'), 'HmacSHA256'))
  header + '.' + payload + '.' + b64u(mac.doFinal((header + '.' + payload).getBytes('UTF-8')))
}
def deep; deep = { x -> x instanceof Map ? x.collectEntries { k, v -> [(k): deep(v)] } : (x instanceof List ? x.collect { deep(it) } : x) }
"""
def pre_script(jm):
    """Sets ROLE/ACTOR/target variables for scenario jm from the fixtures (JM-05 also the expected version and the reason) inside the pre-processor; never an HTTP call."""
    return LIB + r"""
def why = []
def secret = System.getenv('GCN48_JWT_SECRET')
if (!secret) { why << 'GCN48_JWT_SECRET is not in the environment of the JMeter process' }
def fx = null
def f = new File(props.get('fixturesFile') ?: '')
if (!f.exists()) { why << 'fixtures file missing' } else {
  fx = deep(new JsonSlurper().parseText(f.text))
  if (fx.synthetic != true) { why << 'fixtures are not marked synthetic' }
  if (java.time.Instant.now().isAfter(java.time.Instant.parse(fx.validUntilUtc))) { why << 'fixtures are older than 36 hours: re-seed a new empty database' }
}
String role = 'None'; String sub = '00000000-0000-0000-0000-000000000000'
if (fx != null) {
  def t = fx.targets['""" + jm + r"""']
  role = t.role ?: 'Patient'; sub = fx.actors[t.actor]
  vars.put('TARGET_ID', String.valueOf(t.appointmentId))
  if (t.expectedVersion != null) { vars.put('EXPECTED_VERSION', t.expectedVersion); vars.put('CANCEL_REASON', t.reason) }
}
vars.put('ENV_OK', why.isEmpty() ? 'true' : 'false'); vars.put('ENV_WHY', why.join('; '))
vars.put('TOKEN', (secret && fx != null) ? mint(secret, role, sub) : 'invalid')
"""
ENV_ASSERT = jsr("assert", "Environment sanity (secret present, synthetic fresh fixtures): otherwise the scenario FAILS",
                 "if (vars.get('ENV_OK') != 'true') { AssertionResult.setFailure(true); AssertionResult.setFailureMessage('environment not valid: ' + vars.get('ENV_WHY')) }")

VERIFY = r"""
import groovy.json.JsonSlurper
def deep; deep = { x -> x instanceof Map ? x.collectEntries { k, v -> [(k): deep(v)] } : (x instanceof List ? x.collect { deep(it) } : x) }
def fx = deep(new JsonSlurper().parseText(new File(props.get('fixturesFile')).text))
def byId = { int id -> fx.appointments.find { it.id == id } }
def finish = { List fails -> if (fails) { AssertionResult.setFailure(true); AssertionResult.setFailureMessage(fails.take(5).join('; ')) } }
def sameNumber = { x, y -> x != null && y != null && new java.math.BigDecimal(String.valueOf(x)).compareTo(new java.math.BigDecimal(String.valueOf(y))) == 0 }
def ELIG_KEYS = ['appointmentId','allowed','reasonCode','message','refundOutcome','refundAmount','requiresNoRefundAcknowledgement','version','cancellation'] as Set
def checkEligibility = { Map json, int id, List fails ->
  def e = byId(id).expected
  if (json.keySet() as Set != ELIG_KEYS) { fails << ('fields differ from the contract: ' + ((json.keySet() as Set) - ELIG_KEYS) + ' extra, ' + (ELIG_KEYS - (json.keySet() as Set)) + ' missing') }
  if (json.appointmentId != id) { fails << ('appointmentId ' + json.appointmentId + ', expected ' + id) }
  if (json.allowed != e.allowed) { fails << ('allowed = ' + json.allowed + ', expected ' + e.allowed) }
  if (json.reasonCode != e.reasonCode) { fails << ('reasonCode = ' + json.reasonCode + ', expected ' + e.reasonCode) }
  if (json.message != e.message) { fails << ('message = ' + json.message + ', expected ' + e.message) }
  if (json.refundOutcome != e.refundOutcome) { fails << ('refundOutcome = ' + json.refundOutcome + ', expected ' + e.refundOutcome) }
  if (!sameNumber(json.refundAmount, e.refundAmount)) { fails << ('refundAmount = ' + json.refundAmount + ', expected ' + e.refundAmount) }
  if (json.requiresNoRefundAcknowledgement != e.requiresNoRefundAcknowledgement) { fails << ('requiresNoRefundAcknowledgement = ' + json.requiresNoRefundAcknowledgement) }
  if (json.cancellation != null) { fails << 'a cancellation is already stored for this appointment (the database was not fresh)' }
  def v = String.valueOf(json.version)
  if (!(v ==~ /^[0-9A-F]{64}$/)) { fails << ('version is not a valid 64-character hexadecimal version: ' + v) }
  else if (v != e.version) { fails << 'version is valid but differs from the version computed offline from the seeded rows (the offline port and the server disagree)' }
}
"""
def vassert(name, body): return jsr("assert", name, VERIFY + "def fails = []\ndef raw = prev.getResponseDataAsString() ?: ''\n" + body + "\nfinish(fails)")
JSON_CT = header_has("application/json", "Content-Type is JSON")

OWN_CHECK = r"""
def json = new JsonSlurper().parseText(raw)
if (!(json instanceof Map)) { fails << 'body is not a JSON object' } else { checkEligibility(json, Integer.parseInt(vars.get('TARGET_ID')), fails) }
"""
NO_DATA_OF = r"""
def leak = { int id ->
  def a = byId(id)
  [a.appointmentReference, a.patientId, 'Dr Synthetic', 'Cash', 'BankTransfer', '1500', 'Booked'].each { s -> if (raw.contains(s)) { fails << ('response discloses appointment data: ' + s) } }
}
"""
NOT_FOUND_CHECK = NO_DATA_OF + r"""
leak(Integer.parseInt(vars.get('TARGET_ID')))
// the controller answers NotFound(new { message = "Appointment not found." }): exactly that, nothing else
def j = null
try { j = new JsonSlurper().parseText(raw) } catch (Exception ex) { fails << 'the 404 body is not JSON' }
if (j instanceof Map) {
  if ((j.keySet() as Set) != (['message'] as Set)) { fails << ('unexpected fields in the 404 body: ' + j.keySet()) }
  if (j.message != 'Appointment not found.') { fails << ('unexpected 404 message: ' + j.message) }
} else if (j != null) { fails << 'the 404 body is not a JSON object' }
if (raw.contains('version') || raw.contains('allowed') || raw.contains('refund')) { fails << 'the 404 body contains cancellation information' }
"""
FORBIDDEN_CHECK = NO_DATA_OF + r"""
if (raw.length() != 0) { fails << ('the body should be empty (the authorization middleware answers 403 without a body), but has ' + raw.length() + ' bytes') }
leak(Integer.parseInt(vars.get('TARGET_ID')))
"""
CANCEL_CHECK = r"""
def json = new JsonSlurper().parseText(raw)
def a = byId(Integer.parseInt(vars.get('TARGET_ID')))
def KEYS = ['appointmentId','appointmentReference','status','cancelledAtUtc','refundOutcome','refundAmount','refundStatus','reason','message'] as Set
if (!(json instanceof Map)) { fails << 'body is not a JSON object' } else {
  if (json.keySet() as Set != KEYS) { fails << ('fields differ from the contract: ' + json.keySet()) }
  if (json.appointmentId != a.id) { fails << ('appointmentId ' + json.appointmentId + ', expected ' + a.id) }
  if (json.appointmentReference != a.appointmentReference) { fails << ('appointmentReference ' + json.appointmentReference) }
  if (json.status != 'Cancelled') { fails << ('status ' + json.status + ', expected Cancelled') }
  if (json.refundOutcome != 'Eligible') { fails << ('refundOutcome ' + json.refundOutcome + ', expected Eligible') }
  if (!sameNumber(json.refundAmount, a.amount)) { fails << ('refundAmount ' + json.refundAmount + ', expected ' + a.amount) }
  if (json.refundStatus != 'PendingManualProcessing') { fails << ('refundStatus ' + json.refundStatus + ', expected PendingManualProcessing') }
  if (json.reason != vars.get('CANCEL_REASON')) { fails << ('reason ' + json.reason + ', expected the reason that was sent') }
  if (json.message != a.expected.message) { fails << ('message ' + json.message) }
  def u = String.valueOf(json.cancelledAtUtc)
  if (!(u ==~ /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,7})?Z$/)) { fails << ('cancelledAtUtc is not a UTC timestamp: ' + u) }
  else { long skew = Math.abs(java.time.Duration.between(java.time.Instant.parse(u), java.time.Instant.now()).toMinutes()); if (skew > 10) { fails << ('cancelledAtUtc is ' + skew + ' minutes away from the local clock') } }
}
"""
EVIDENCE = r"""
// non-HTTP evidence for the read-only database check after the run: only the contract fields of the 200 response
def j = new groovy.json.JsonSlurper().parseText(prev.getResponseDataAsString())
new File(props.get('evidenceDir'), 'jm05-response.json').text = groovy.json.JsonOutput.toJson([appointmentId: j.appointmentId, status: j.status, cancelledAtUtc: j.cancelledAtUtc, refundOutcome: j.refundOutcome,
  refundAmount: j.refundAmount, refundStatus: j.refundStatus, reason: j.reason, httpStatus: prev.getResponseCode()])
"""

H_JSON = ("Accept", "application/json"); AUTH = ("Authorization", "Bearer ${TOKEN}")
def scenario(sid, name, comment, method, path, body, asserts, post=()):
    ch = [headers([AUTH, H_JSON] + ([("Content-Type", "application/json")] if body is not None else [])), jsr("pre", "Local JWT, fixtures and environment sanity (never an HTTP call)", pre_script(sid)), ENV_ASSERT] + list(asserts) + list(post)
    return thread_group(f"{sid} {name}", comment, [sampler(f"{sid} {name}", method, path, body, ch)])

CPATH = "/api/patient/appointments/${TARGET_ID}/cancellation"
JM = [
 scenario("JM-01", "Own unpaid appointment eligibility", "ONE request: GET eligibility of patient 1's own unpaid (cash, pending) appointment 48001 with patient 1's token. 200, allowed true, reason Unpaid, no refund, a valid 64-character version (equal to the version computed offline).",
          "GET", CPATH, None, [code_is(200), JSON_CT, vassert("Eligibility equals the seeded appointment: allowed true, Unpaid, NotRequired, valid 64-hex version equal to the offline value", OWN_CHECK), duration(3000)]),
 scenario("JM-02", "Restricted cash-paid appointment eligibility", "ONE request: GET eligibility of patient 1's cash-paid appointment 48002. 200, allowed false, reason CashAlreadyPaid.",
          "GET", CPATH, None, [code_is(200), JSON_CT, vassert("Eligibility is the restriction: allowed false, CashAlreadyPaid, no refund, version equal to the offline value", OWN_CHECK), duration(3000)]),
 scenario("JM-03", "Another patient's appointment access", "ONE request: GET eligibility of appointment 48101 (patient 2's) with patient 1's token. 404 with only the generic message; nothing about the appointment is disclosed.",
          "GET", CPATH, None, [code_is(404), vassert("404 body is exactly the generic message and discloses no appointment, patient, payment or cancellation data", NOT_FOUND_CHECK), duration(3000)]),
 scenario("JM-04", "Doctor-role token on a patient endpoint", "ONE request: GET eligibility of appointment 48001 with a valid synthetic DOCTOR token. 403 (authenticated, wrong role) with an empty body. Only this one non-patient case can be covered by one request.",
          "GET", CPATH, None, [code_is(403), vassert("Empty body: nothing about the appointment is disclosed to a Doctor", FORBIDDEN_CHECK), duration(3000)]),
 scenario("JM-05", "Valid bank-transfer cancellation", "ONE request: POST the cancellation of patient 1's verified bank-transfer appointment 48005 (72 hours before its start) with the expectedVersion computed offline and verified against the real backend code. 200, Cancelled, refund Eligible, PendingManualProcessing. The cancellation row, the manual-refund row and all unchanged data are verified afterwards by read-only SQL, not by HTTP.",
          "POST", CPATH, '{"expectedVersion":"${EXPECTED_VERSION}","acknowledgeNoRefund":false,"reason":"${CANCEL_REASON}"}',
          [code_is(200), JSON_CT, vassert("The response confirms the cancellation: Cancelled, Eligible refund of the paid amount, PendingManualProcessing, the reason that was sent, a fresh UTC timestamp", CANCEL_CHECK), duration(3000)],
          post=[jsr("post", "Write the response fields to a local evidence file (not HTTP)", EVIDENCE)]),
]

SAVE = ('<objProp><name>saveConfig</name><value class="SampleSaveConfiguration"><time>true</time><latency>true</latency><timestamp>true</timestamp><success>true</success><label>true</label><code>true</code><message>true</message>'
        '<threadName>true</threadName><dataType>true</dataType><encoding>false</encoding><assertions>true</assertions><subresults>true</subresults><responseData>false</responseData><samplerData>false</samplerData><xml>false</xml>'
        '<fieldNames>true</fieldNames><responseHeaders>false</responseHeaders><requestHeaders>false</requestHeaders><responseDataOnError>false</responseDataOnError><saveAssertionResultsFailureMessage>true</saveAssertionResultsFailureMessage>'
        '<assertionsResultsToSave>0</assertionsResultsToSave><bytes>true</bytes><sentBytes>true</sentBytes><url>true</url><threadCounts>true</threadCounts><idleTime>true</idleTime><connectTime>true</connectTime></value></objProp>')
def listener(gui, name): return (f'<ResultCollector guiclass="{gui}" testclass="ResultCollector" testname={a(name)} enabled="true"><boolProp name="ResultCollector.error_logging">false</boolProp>{SAVE}<stringProp name="filename"></stringProp></ResultCollector>') + ht()
doc = ('<?xml version="1.0" encoding="UTF-8"?>\n<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3"><hashTree><TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="GCN-48 Appointment Cancellation API (5 scenarios, 5 HTTP requests)" enabled="true">'
       '<stringProp name="TestPlan.comments">GCN-48 QA. LOCAL only: backend localhost:5248, isolated database carenova_appointment_gcn48_qa, synthetic patients and appointments. EXACTLY five HTTP requests, one per scenario (4 GET + 1 POST), one thread and one iteration each. No setup, authentication, health-check or teardown request. Functional and latency SMOKE test only: NOT a load or concurrency test. No secrets in this file. Run it through run-gcn48-jmeter.sh, never from the GUI.</stringProp>'
       '<boolProp name="TestPlan.functional_mode">false</boolProp><boolProp name="TestPlan.tearDown_on_shutdown">true</boolProp><boolProp name="TestPlan.serialize_threadgroups">true</boolProp>'
       '<elementProp name="TestPlan.user_defined_variables" elementType="Arguments" guiclass="ArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true"><collectionProp name="Arguments.arguments"/></elementProp>'
       '<stringProp name="TestPlan.user_define_classpath"></stringProp></TestPlan>' + ht(listener("SummaryReport", "Summary Report") + listener("ViewResultsFullVisualizer", "View Results Tree") + "".join(JM)) + '</hashTree></jmeterTestPlan>\n')
open(os.path.join(OUT, "GCN48AppointmentCancellationTest.jmx"), "w").write(doc)

SC = {
 "JM-01": {"name": "Own unpaid appointment eligibility", "method": "GET", "path": "/api/patient/appointments/48001/cancellation", "role": "Patient (patient 1)", "expected_status": 200, "expected_requests": 1},
 "JM-02": {"name": "Restricted cash-paid appointment eligibility", "method": "GET", "path": "/api/patient/appointments/48002/cancellation", "role": "Patient (patient 1)", "expected_status": 200, "expected_requests": 1},
 "JM-03": {"name": "Another patient's appointment access", "method": "GET", "path": "/api/patient/appointments/48101/cancellation", "role": "Patient (patient 1; appointment belongs to patient 2)", "expected_status": 404, "expected_requests": 1},
 "JM-04": {"name": "Doctor-role token on a patient endpoint", "method": "GET", "path": "/api/patient/appointments/48001/cancellation", "role": "Doctor", "expected_status": 403, "expected_requests": 1},
 "JM-05": {"name": "Valid bank-transfer cancellation", "method": "POST", "path": "/api/patient/appointments/48005/cancellation", "role": "Patient (patient 1)", "expected_status": 200, "expected_requests": 1,
           "database_verification": "read-only SQL after the run: appointment Cancelled, exactly one cancellation row and one manual-refund row (PendingManualProcessing), timestamps equal, nothing else changed"},
}
json.dump({"total_http_requests": 5, "iterations_per_scenario": 1, "threads_per_scenario": 1,
           "note": "Functional and latency smoke test. A single request per scenario proves behaviour for ONE input each. It is not a load, concurrency or performance test; the 3000 ms limit is a sanity cap only.",
           "scenarios": SC}, open(os.path.join(OUT, "scenarios.json"), "w"), indent=2)
print("wrote JMX and scenarios.json: 5 scenarios, 5 HTTP samplers")
