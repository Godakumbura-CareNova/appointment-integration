#!/usr/bin/env python3
"""Generates GCN47DoctorAppointmentsTest.jmx and scenarios.json: EXACTLY five scenarios JM-01..JM-05, EXACTLY five HTTP samplers (one per scenario, one thread, one iteration).
HOW THE "NO EXTRA HTTP REQUEST" RULE IS MET: there is no setup, authentication, health-check or teardown sampler and no JSR223 *sampler* at all. Everything that is not the
five requests (local JWT minting, fixture loading and the environment sanity flag) happens inside JSR223 PRE-processors attached to the five samplers and is never an HTTP call.
The plan contains NO secret: tokens are minted at run time from GCN47_JWT_SECRET in the JMeter process environment.
No script text contains the characters dollar-brace (JMeter would interpolate them); Groovy uses string concatenation."""
import json, os
from xml.sax.saxutils import escape, quoteattr
a = quoteattr
OUT = os.path.dirname(os.path.abspath(__file__))
PORT = "5247"
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
def pre_script(role_expr, path_expr, body_note=""):
    """role_expr / path_expr are Groovy expressions over fx (the fixtures) evaluated in the pre-processor."""
    return LIB + r"""
def why = []
def secret = System.getenv('GCN47_JWT_SECRET')
if (!secret) { why << 'GCN47_JWT_SECRET is not in the environment of the JMeter process' }
def fx = null
def f = new File(props.get('fixturesFile') ?: '')
if (!f.exists()) { why << 'fixtures file missing' } else {
  fx = deep(new JsonSlurper().parseText(f.text))
  if (fx.synthetic != true) { why << 'fixtures are not marked synthetic' }
  if (java.time.Instant.now().isAfter(java.time.Instant.parse(fx.validUntilUtc))) { why << 'fixtures are older than 36 hours: re-seed a new empty database' }
}
String role = 'None'; String sub = '00000000-0000-0000-0000-000000000000'; String path = '/none'
if (fx != null) { """ + role_expr + """
  """ + path_expr + r""" }
vars.put('ENV_OK', why.isEmpty() ? 'true' : 'false'); vars.put('ENV_WHY', why.join('; '))
vars.put('TOKEN', (secret && fx != null) ? mint(secret, role, sub) : 'invalid')
vars.put('TARGET', path)
"""
ENV_ASSERT = jsr("assert", "Environment sanity (secret present, synthetic fresh fixtures): otherwise the scenario FAILS",
                 "if (vars.get('ENV_OK') != 'true') { AssertionResult.setFailure(true); AssertionResult.setFailureMessage('environment not valid: ' + vars.get('ENV_WHY')) }")

VERIFY = r"""
import groovy.json.JsonSlurper
def FIELDS = ['id','appointmentReference','patientId','patientName','patientPhone','appointmentStartUtc','appointmentEndUtc','status','updatedAtUtc','paymentMethod','paymentStatus','isToday','isUpcoming','isCompleted','isHistory','allowedStatuses','contactsUnavailable'] as Set
def deep; deep = { x -> x instanceof Map ? x.collectEntries { k, v -> [(k): deep(v)] } : (x instanceof List ? x.collect { deep(it) } : x) }
def fx = deep(new JsonSlurper().parseText(new File(props.get('fixturesFile')).text))
def sameInstant = { x, y -> try { java.time.Instant.parse(String.valueOf(x)) == java.time.Instant.parse(String.valueOf(y)) } catch (Exception ex) { false } }
def verifyItem = { Map got, Map e, List fails ->
  def p = 'appointment ' + e.id + ': '
  if (got.keySet() as Set != FIELDS) { fails << (p + 'fields differ from the contract: ' + (got.keySet() as Set).minus(FIELDS) + ' extra, ' + FIELDS.minus(got.keySet() as Set) + ' missing') }
  ['id','appointmentReference','patientId','patientName','patientPhone','status','updatedAtUtc','paymentMethod','paymentStatus','isToday','isUpcoming','isCompleted','isHistory','contactsUnavailable'].each { k ->
    if (got[k] != e[k]) { fails << (p + k + ' = ' + got[k] + ', expected ' + e[k]) } }
  if (got.allowedStatuses != e.allowedStatuses) { fails << (p + 'allowedStatuses ' + got.allowedStatuses + ', expected ' + e.allowedStatuses) }
  ['appointmentStartUtc','appointmentEndUtc'].each { k -> if (!sameInstant(got[k], e[k]) || !String.valueOf(got[k]).endsWith('Z')) { fails << (p + k + ' = ' + got[k] + ', expected the UTC instant ' + e[k]) } }
}
def noForeignData = { String body, List fails ->
  fx.doctors.D2.appointments.each { x -> [String.valueOf(x.id), x.appointmentReference, x.patientId].each { s -> if (s != null && body.contains(s)) { fails << ('response contains data of the other doctor: ' + s) } } }
}
def finish = { List fails -> if (fails) { AssertionResult.setFailure(true); AssertionResult.setFailureMessage(fails.take(5).join('; ')) } }
"""
def vassert(name, body): return jsr("assert", name, VERIFY + "def fails = []\ndef raw = prev.getResponseDataAsString() ?: ''\n" + body + "\nfinish(fails)")
JSON_CT = header_has("application/json", "Content-Type is JSON")

LIST_CHECK = r"""
def json = new JsonSlurper().parseText(raw)
def exp = fx.doctors.D1
if (!(json instanceof Map)) { fails << 'body is not a JSON object' } else {
  if (json.keySet() as Set != ['appointments','statistics','contactsUnavailable'] as Set) { fails << 'top-level fields differ from the contract: ' + json.keySet() }
  def got = json.appointments ?: []
  if (got.collect { it.id } != exp.appointments.collect { it.id }) { fails << 'appointment ids/order ' + got.collect { it.id } + ', expected (ascending by start, then id) ' + exp.appointments.collect { it.id } }
  else { got.eachWithIndex { g, i -> verifyItem(g, exp.appointments[i], fails) } }
  ['today','upcoming','completed','patientCount'].each { k -> if (json.statistics?.get(k) != exp.statistics[k]) { fails << ('statistics.' + k + ' = ' + json.statistics?.get(k) + ', expected ' + exp.statistics[k]) } }
  if (json.contactsUnavailable != true) { fails << 'contactsUnavailable should be true: the patient-contact service is intentionally absent in this isolated environment' }
}
noForeignData(raw, fails)
"""
DETAIL_CHECK = r"""
def json = new JsonSlurper().parseText(raw)
def e = fx.doctors.D1.appointments.find { it.id == fx.targets['JM-02'].appointmentId }
if (!(json instanceof Map)) { fails << 'body is not a JSON object' } else { verifyItem(json, e, fails) }
noForeignData(raw, fails)
"""
FOREIGN_AND_OWN_DATA = r"""
noForeignData(raw, fails)
fx.doctors.D1.appointments.each { x -> if (raw.contains(x.appointmentReference) || raw.contains(x.patientId)) { fails << 'response contains appointment data' } }
"""
EMPTY_NO_DATA = r"""
if (raw.length() != 0) { fails << 'the body should be empty (the authorization middleware answers 403 without a body), but has ' + raw.length() + ' bytes' }
""" + FOREIGN_AND_OWN_DATA
NOT_FOUND_NO_DATA = r"""
// a bare NotFound() in an [ApiController] is either empty or the framework's ProblemDetails (type, title, status, traceId): nothing else is acceptable
if (raw.length() > 0) {
  def j = null
  try { j = new JsonSlurper().parseText(raw) } catch (Exception ex) { fails << 'a non-empty body that is not JSON' }
  if (j instanceof Map) {
    def extra = (j.keySet() as Set) - (['type', 'title', 'status', 'traceId'] as Set)
    if (extra) { fails << 'unexpected fields in the 404 body: ' + extra }
    if (j.status != 404 || j.title != 'Not Found') { fails << 'the 404 body is not the standard Not Found problem details: ' + j.status + ' / ' + j.title }
  } else if (j != null) { fails << 'the 404 body is not a JSON object' }
}
""" + FOREIGN_AND_OWN_DATA
UPDATE_CHECK = r"""
def json = new JsonSlurper().parseText(raw)
def t = fx.targets['JM-05']
if (!(json instanceof Map)) { fails << 'body is not a JSON object' } else {
  if (json.keySet() as Set != ['id','status','updatedAtUtc'] as Set) { fails << 'fields differ from the contract: ' + json.keySet() }
  if (json.id != t.appointmentId) { fails << 'id ' + json.id + ', expected ' + t.appointmentId }
  if (json.status != t.to) { fails << 'status ' + json.status + ', expected ' + t.to }
  def u = String.valueOf(json.updatedAtUtc)
  if (!(u ==~ /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,7})?Z$/)) { fails << 'updatedAtUtc is not a UTC timestamp: ' + u }
  else { long skew = Math.abs(java.time.Duration.between(java.time.Instant.parse(u), java.time.Instant.now()).toMinutes()); if (skew > 10) { fails << 'updatedAtUtc is ' + skew + ' minutes away from the local clock' } }
}
noForeignData(raw, fails)
"""
EVIDENCE = r"""
// non-HTTP evidence for the read-only database check after the run: only the three contract fields of the 200 response
def j = new groovy.json.JsonSlurper().parseText(prev.getResponseDataAsString())
new File(props.get('evidenceDir'), 'jm05-response.json').text = groovy.json.JsonOutput.toJson([id: j.id, status: j.status, updatedAtUtc: j.updatedAtUtc, httpStatus: prev.getResponseCode()])
"""

H_JSON = ("Accept", "application/json"); AUTH = ("Authorization", "Bearer ${TOKEN}")
def scenario(sid, name, comment, method, path, body, role_expr, path_expr, asserts, post=()):
    ch = [headers([AUTH, H_JSON] + ([("Content-Type", "application/json")] if body is not None else [])), jsr("pre", "Local JWT, fixtures and environment sanity (never an HTTP call)", pre_script(role_expr, path_expr)), ENV_ASSERT] + list(asserts) + list(post)
    return thread_group(f"{sid} {name}", comment, [sampler(f"{sid} {name}", method, path, body, ch)])

PATHS = "path = '/api/doctor/appointments'"
JM = [
 scenario("JM-01", "Doctor appointment list", "ONE request: GET /api/doctor/appointments as the synthetic Doctor 1. 200 and exactly Doctor 1's 8 seeded appointments, in order, every field and the statistics equal to the oracle; no data of Doctor 2.",
          "GET", "/api/doctor/appointments", None, "role = 'Doctor'; sub = fx.doctors.D1.id", PATHS,
          [code_is(200), JSON_CT, vassert("The list is exactly Doctor 1's seeded appointments (ids, order, fields, statistics) and nothing of Doctor 2", LIST_CHECK), duration(3000)]),
 scenario("JM-02", "Assigned appointment details", "ONE request: GET /api/doctor/appointments/47001 as Doctor 1 (an appointment assigned to Doctor 1). 200 and every field equal to the oracle.",
          "GET", "/api/doctor/appointments/${TARGET_ID}", None, "role = 'Doctor'; sub = fx.doctors.D1.id", "path = String.valueOf(fx.targets['JM-02'].appointmentId); vars.put('TARGET_ID', path); path = '/api/doctor/appointments/' + path",
          [code_is(200), JSON_CT, vassert("The details equal the seeded appointment (all 17 contract fields) and nothing of Doctor 2", DETAIL_CHECK), duration(3000)]),
 scenario("JM-03", "Another doctor's appointment access", "ONE request: GET /api/doctor/appointments/47101 (assigned to Doctor 2) with Doctor 1's token. Expected: 404 (the service filters by the owning doctor), with an empty or standard Not Found body and no data of the other doctor.",
          "GET", "/api/doctor/appointments/${TARGET_ID}", None, "role = 'Doctor'; sub = fx.doctors.D1.id", "path = String.valueOf(fx.targets['JM-03'].foreignAppointmentId); vars.put('TARGET_ID', path); path = '/api/doctor/appointments/' + path",
          [code_is(404), vassert("404 body is empty or the standard Not Found problem details, and discloses no appointment, patient or reference of the other doctor", NOT_FOUND_NO_DATA), duration(3000)]),
 scenario("JM-04", "Non-Doctor access (Patient role)", "ONE request: GET /api/doctor/appointments with a valid synthetic PATIENT token. Expected: 403 (authenticated, wrong role) and no data. Only this one case can be covered by one request.",
          "GET", "/api/doctor/appointments", None, "role = 'Patient'; sub = fx.targets['JM-04'].patientId", PATHS,
          [code_is(403), vassert("Empty body: nothing of any doctor's schedule is disclosed to a Patient", EMPTY_NO_DATA), duration(3000)]),
 scenario("JM-05", "Valid appointment status update", "ONE request: PATCH /api/doctor/appointments/47002/status as Doctor 1 with {status: Confirmed, expectedStatus: Booked, expectedUpdatedAtUtc: null}. 200 and {id, status, updatedAtUtc}. The audit row and all unchanged data are verified afterwards by read-only SQL, not by HTTP.",
          "PATCH", "/api/doctor/appointments/${TARGET_ID}/status", '{"status":"Confirmed","expectedStatus":"Booked","expectedUpdatedAtUtc":null}', "role = 'Doctor'; sub = fx.doctors.D1.id",
          "path = String.valueOf(fx.targets['JM-05'].appointmentId); vars.put('TARGET_ID', path); path = '/api/doctor/appointments/' + path + '/status'",
          [code_is(200), JSON_CT, vassert("The response confirms exactly the requested transition with a fresh UTC timestamp", UPDATE_CHECK), duration(3000)],
          post=[jsr("post", "Write the three response fields to a local evidence file (not HTTP)", EVIDENCE)]),
]
# the TARGET_ID variable of scenarios JM-01 / JM-04 is not used (their path is fixed); the pre-processor always sets TARGET for completeness.

SAVE = ('<objProp><name>saveConfig</name><value class="SampleSaveConfiguration"><time>true</time><latency>true</latency><timestamp>true</timestamp><success>true</success><label>true</label><code>true</code><message>true</message>'
        '<threadName>true</threadName><dataType>true</dataType><encoding>false</encoding><assertions>true</assertions><subresults>true</subresults><responseData>false</responseData><samplerData>false</samplerData><xml>false</xml>'
        '<fieldNames>true</fieldNames><responseHeaders>false</responseHeaders><requestHeaders>false</requestHeaders><responseDataOnError>false</responseDataOnError><saveAssertionResultsFailureMessage>true</saveAssertionResultsFailureMessage>'
        '<assertionsResultsToSave>0</assertionsResultsToSave><bytes>true</bytes><sentBytes>true</sentBytes><url>true</url><threadCounts>true</threadCounts><idleTime>true</idleTime><connectTime>true</connectTime></value></objProp>')
def listener(gui, name): return (f'<ResultCollector guiclass="{gui}" testclass="ResultCollector" testname={a(name)} enabled="true"><boolProp name="ResultCollector.error_logging">false</boolProp>{SAVE}<stringProp name="filename"></stringProp></ResultCollector>') + ht()
doc = ('<?xml version="1.0" encoding="UTF-8"?>\n<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3"><hashTree><TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="GCN-47 Doctor Appointments API (5 scenarios, 5 HTTP requests)" enabled="true">'
       '<stringProp name="TestPlan.comments">GCN-47 QA. LOCAL only: backend localhost:5247, isolated database carenova_appointment_gcn47_qa, synthetic doctors and appointments. EXACTLY five HTTP requests, one per scenario (4 GET + 1 PATCH), one thread and one iteration each. No setup, authentication, health-check or teardown request. This plan is NOT a load or concurrency test. No secrets in this file.</stringProp>'
       '<boolProp name="TestPlan.functional_mode">false</boolProp><boolProp name="TestPlan.tearDown_on_shutdown">true</boolProp><boolProp name="TestPlan.serialize_threadgroups">true</boolProp>'
       '<elementProp name="TestPlan.user_defined_variables" elementType="Arguments" guiclass="ArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true"><collectionProp name="Arguments.arguments"/></elementProp>'
       '<stringProp name="TestPlan.user_define_classpath"></stringProp></TestPlan>' + ht(listener("SummaryReport", "Summary Report") + listener("ViewResultsFullVisualizer", "View Results Tree") + "".join(JM)) + '</hashTree></jmeterTestPlan>\n')
open(os.path.join(OUT, "GCN47DoctorAppointmentsTest.jmx"), "w").write(doc)

SC = {
 "JM-01": {"name": "Doctor appointment list", "method": "GET", "path": "/api/doctor/appointments", "role": "Doctor (doctor 1)", "expected_status": 200, "expected_requests": 1},
 "JM-02": {"name": "Assigned appointment details", "method": "GET", "path": "/api/doctor/appointments/47001", "role": "Doctor (doctor 1)", "expected_status": 200, "expected_requests": 1},
 "JM-03": {"name": "Another doctor's appointment access", "method": "GET", "path": "/api/doctor/appointments/47101", "role": "Doctor (doctor 1; appointment belongs to doctor 2)", "expected_status": 404, "expected_requests": 1},
 "JM-04": {"name": "Non-Doctor access (Patient role)", "method": "GET", "path": "/api/doctor/appointments", "role": "Patient", "expected_status": 403, "expected_requests": 1},
 "JM-05": {"name": "Valid appointment status update", "method": "PATCH", "path": "/api/doctor/appointments/47002/status", "role": "Doctor (doctor 1)", "expected_status": 200, "expected_requests": 1,
           "database_verification": "read-only SQL after the run: exactly one audit row (Booked -> Confirmed, doctor 1, ChangedAtUtc = Appointments.UpdatedAtUtc = response updatedAtUtc), nothing else changed"},
}
json.dump({"total_http_requests": 5, "iterations_per_scenario": 1, "threads_per_scenario": 1,
           "note": "A single request per scenario proves behaviour for ONE input each. It is not a load, concurrency or performance test; the 3000 ms limit is a sanity cap only.",
           "scenarios": SC}, open(os.path.join(OUT, "scenarios.json"), "w"), indent=2)
print("wrote JMX and scenarios.json: 5 scenarios, 5 HTTP samplers")
