#!/usr/bin/env python3
"""Generates GCN51RoleDashboardTest.jmx and scenarios.json: EXACTLY nine scenarios J01..J09, EXACTLY nine read-only GET samplers (one per scenario; J09 loops its sampler 30 times; one thread).
HOW THE "NO EXTRA HTTP REQUEST" RULE IS MET: there is no setup, authentication, health-check or teardown sampler and no JSR223 *sampler* at all. Everything that is not the
requests (local JWT minting, fixture loading and the environment sanity flag) happens inside JSR223 PRE-processors attached to the 9 samplers and is never an HTTP call.
The plan contains NO secret: tokens are minted at run time from GCN51_JWT_SECRET in the JMeter process environment.
No script text contains the characters dollar-brace (JMeter would interpolate them); Groovy uses string concatenation."""
import json, os
from xml.sax.saxutils import escape, quoteattr
a = quoteattr
OUT = os.path.dirname(os.path.abspath(__file__))
PORT = "5251"
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
         f'<stringProp name="HTTPSampler.domain">${{HOST}}</stringProp><stringProp name="HTTPSampler.port">${{PORT}}</stringProp><stringProp name="HTTPSampler.protocol">http</stringProp>'
         f'<stringProp name="HTTPSampler.path">{escape(path)}</stringProp><stringProp name="HTTPSampler.method">{method}</stringProp>'
         '<boolProp name="HTTPSampler.follow_redirects">false</boolProp><boolProp name="HTTPSampler.auto_redirects">false</boolProp><boolProp name="HTTPSampler.use_keepalive">true</boolProp>'
         '<boolProp name="HTTPSampler.DO_MULTIPART_POST">false</boolProp><boolProp name="HTTPSampler.image_parser">false</boolProp>'
         '<stringProp name="HTTPSampler.connect_timeout">5000</stringProp><stringProp name="HTTPSampler.response_timeout">30000</stringProp></HTTPSamplerProxy>')
    return s + ht("".join(children))

def thread_group(name, comment, children, loops=1):     # one thread, one iteration, no ramp, no scheduler
    return (f'<ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname={a(name)} enabled="true"><stringProp name="TestPlan.comments">{escape(comment)}</stringProp>'
            '<stringProp name="ThreadGroup.on_sample_error">continue</stringProp><elementProp name="ThreadGroup.main_controller" elementType="LoopController" guiclass="LoopControlPanel" testclass="LoopController" testname="Loop Controller" enabled="true">'
            f'<boolProp name="LoopController.continue_forever">false</boolProp><stringProp name="LoopController.loops">{loops}</stringProp></elementProp>'
            '<stringProp name="ThreadGroup.num_threads">1</stringProp><stringProp name="ThreadGroup.ramp_time">0</stringProp><boolProp name="ThreadGroup.scheduler">false</boolProp>'
            '<stringProp name="ThreadGroup.duration"></stringProp><stringProp name="ThreadGroup.delay"></stringProp><boolProp name="ThreadGroup.same_user_on_next_iteration">true</boolProp></ThreadGroup>') + ht("".join(children))

# ------------------------------------------------------------------------------------------------ Groovy: local JWT, guarded target, fixtures (pre-processor, never HTTP)
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
def pre_script(actor):
    """actor = None (no token) or the fixtures.actors key whose identity is signed; ROLE is passed in as the first argument."""
    return LIB + r"""
def why = []
def secret = System.getenv('GCN51_JWT_SECRET')
if (!secret) { why << 'GCN51_JWT_SECRET is not in the environment of the JMeter process' }
// the target is configurable by JMeter properties but GUARDED: anything but the isolated QA backend is replaced by an address that cannot connect
String host = props.get('gcn51.host') ?: 'localhost'; String port = props.get('gcn51.port') ?: '5251'
if (!(host in ['localhost', '127.0.0.1']) || port != '5251') { why << ('refused target ' + host + ':' + port + ' (only localhost:5251 is allowed)'); host = 'target-refused.invalid'; port = '1' }
vars.put('HOST', host); vars.put('PORT', port)
def fx = null
def f = new File(props.get('fixturesFile') ?: '')
if (!f.exists()) { why << 'fixtures file missing' } else {
  fx = deep(new JsonSlurper().parseText(f.text))
  if (fx.synthetic != true) { why << 'fixtures are not marked synthetic' }
  if (java.time.Instant.now().isAfter(java.time.Instant.parse(fx.validUntilUtc))) { why << 'fixtures are older than 72 hours: re-seed a new empty database' }
}
vars.put('ENV_OK', why.isEmpty() ? 'true' : 'false'); vars.put('ENV_WHY', why.join('; '))
""" + ("" if actor is None else r"""
def ROLE = '""" + actor[0] + r"""'; def SUB = fx != null ? fx.actors['""" + actor[1] + r"""'] : '00000000-0000-0000-0000-000000000000'
vars.put('TOKEN', (secret && fx != null) ? mint(secret, ROLE, SUB) : 'invalid')
""")
ENV_ASSERT = jsr("assert", "Environment sanity (secret present, allowed target, synthetic fresh fixtures): otherwise the scenario FAILS",
                 "if (vars.get('ENV_OK') != 'true') { AssertionResult.setFailure(true); AssertionResult.setFailureMessage('environment not valid: ' + vars.get('ENV_WHY')) }")

VERIFY = r"""
import groovy.json.JsonSlurper
def deep; deep = { x -> x instanceof Map ? x.collectEntries { k, v -> [(k): deep(v)] } : (x instanceof List ? x.collect { deep(it) } : x) }
def fx = deep(new JsonSlurper().parseText(new File(props.get('fixturesFile')).text))
def fails = []
def raw = prev.getResponseDataAsString() ?: ''
def finish = { List f -> if (f) { AssertionResult.setFailure(true); AssertionResult.setFailureMessage(f.take(5).join('; ')) } }
def num = { x -> new java.math.BigDecimal(String.valueOf(x)) }
def sameNumber = { x, y -> x != null && y != null && num(x).compareTo(num(y)) == 0 }
def isUtc = { v -> String.valueOf(v) ==~ /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,7})?Z$/ }
def sameInstant = { x, y -> try { java.time.Instant.parse(String.valueOf(x)) == java.time.Instant.parse(String.valueOf(y)) } catch (Exception ex) { false } }
def fresh = { v -> isUtc(v) && Math.abs(java.time.Duration.between(java.time.Instant.parse(String.valueOf(v)), java.time.Instant.now()).toMinutes()) <= 10 }
def keysAre = { Map m, List k, String where -> if ((m.keySet() as Set) != (k as Set)) { fails << (where + ' fields differ from the contract: ' + ((m.keySet() as Set) - (k as Set)) + ' extra, ' + ((k as Set) - (m.keySet() as Set)) + ' missing') } }
def parse = { try { new JsonSlurper().parseText(raw) } catch (Exception ex) { fails << 'the body is not JSON'; null } }
"""
def vassert(name, body): return jsr("assert", name, VERIFY + body + "\nfinish(fails)")

PATIENT_CONTRACT = r"""
def j = parse()
if (j instanceof Map) {
  keysAre(j, ['upcomingCount', 'appointments', 'paymentStatusCounts', 'generatedAtUtc'], 'patient dashboard')
  if (!(j.upcomingCount instanceof Integer) || j.upcomingCount < 0) { fails << ('upcomingCount is not a non-negative integer: ' + j.upcomingCount) }
  if (!(j.appointments instanceof List) || j.appointments.size() > 5) { fails << 'appointments is not a list of at most 5 items' }
  else {
    if (j.upcomingCount < j.appointments.size()) { fails << 'upcomingCount is smaller than the number of listed appointments' }
    j.appointments.each { a -> keysAre(a, ['id', 'reference', 'doctorName', 'startUtc', 'status', 'paymentMethod', 'paymentStatus'], 'appointment ' + a.id); if (!isUtc(a.startUtc)) { fails << ('startUtc is not UTC: ' + a.startUtc) } }
  }
  if (!(j.paymentStatusCounts instanceof Map) || j.paymentStatusCounts.any { k, v -> !(v instanceof Integer) || v < 0 }) { fails << 'paymentStatusCounts is not a map of non-negative integers' }
  if (!fresh(j.generatedAtUtc)) { fails << ('generatedAtUtc is not a fresh UTC timestamp: ' + j.generatedAtUtc) }
}
"""
PATIENT_VALUES = r"""
def j = parse()
def e = fx.patient
if (j instanceof Map) {
  if (j.upcomingCount != e.upcomingCount) { fails << ('upcomingCount = ' + j.upcomingCount + ', expected ' + e.upcomingCount) }
  def got = (j.appointments ?: [])
  if (got.collect { it.id } != e.appointments.collect { it.id }) { fails << ('appointment ids/order ' + got.collect { it.id } + ', expected ' + e.appointments.collect { it.id }) }
  else { got.eachWithIndex { g, i -> def x = e.appointments[i]
    ['reference', 'doctorName', 'status', 'paymentMethod', 'paymentStatus'].each { k -> if (g[k] != x[k]) { fails << ('appointment ' + x.id + ' ' + k + ' = ' + g[k] + ', expected ' + x[k]) } }
    if (!sameInstant(g.startUtc, x.startUtc) || !String.valueOf(g.startUtc).endsWith('Z')) { fails << ('appointment ' + x.id + ' startUtc = ' + g.startUtc + ', expected ' + x.startUtc) } } }
  if ((j.paymentStatusCounts ?: [:]) != e.paymentStatusCounts) { fails << ('paymentStatusCounts ' + j.paymentStatusCounts + ', expected ' + e.paymentStatusCounts) }
}
e.foreignReferences.each { r -> if (raw.contains(r)) { fails << ('response contains an appointment of another patient: ' + r) } }
if (raw.contains('CN-APT-DSH-51201')) { fails << 'response contains an appointment of another patient' }
"""
STAFF_CONTRACT = r"""
def j = parse()
if (j instanceof Map) {
  keysAre(j, ['pendingTransfers', 'recentPayments', 'income', 'generatedAtUtc'], 'staff dashboard')
  def PK = ['id', 'appointmentId', 'reference', 'amount', 'method', 'status', 'confirmedAtUtc', 'updatedAtUtc']
  if (!(j.pendingTransfers instanceof Map)) { fails << 'pendingTransfers is not an object' } else {
    keysAre(j.pendingTransfers, ['totalCount', 'items'], 'pendingTransfers')
    if (!(j.pendingTransfers.items instanceof List) || j.pendingTransfers.items.size() > 5 || j.pendingTransfers.totalCount < j.pendingTransfers.items.size()) { fails << 'pendingTransfers items/totalCount are inconsistent or exceed 5' }
    else { j.pendingTransfers.items.each { p -> keysAre(p, PK, 'pending payment ' + p.id) } } }
  if (!(j.recentPayments instanceof List) || j.recentPayments.size() > 5) { fails << 'recentPayments is not a list of at most 5 items' } else { j.recentPayments.each { p -> keysAre(p, PK, 'recent payment ' + p.id) } }
  if (!(j.income instanceof Map)) { fails << 'income is not an object' } else {
    keysAre(j.income, ['todayAmount', 'monthAmount', 'undatedSuccessfulCount', 'undatedSuccessfulAmount', 'currency', 'timeZone', 'asOfUtc'], 'income')
    if (j.income.currency != 'LKR' || j.income.timeZone != 'Asia/Colombo') { fails << ('currency/timeZone ' + j.income.currency + '/' + j.income.timeZone) }
    if (num(j.income.monthAmount) < num(j.income.todayAmount)) { fails << 'monthAmount is smaller than todayAmount' }
    if (!fresh(j.income.asOfUtc)) { fails << ('income.asOfUtc is not fresh: ' + j.income.asOfUtc) } }
  if (!fresh(j.generatedAtUtc)) { fails << ('generatedAtUtc is not a fresh UTC timestamp: ' + j.generatedAtUtc) }
}
"""
STAFF_VALUES = r"""
def j = parse()
def e = fx.staff
def pay = { int id -> e.payments.find { it.id == id } }
def comparePayment = { Map g, Map p, String where ->
  ['appointmentId', 'reference', 'method', 'status'].each { k -> if (g[k] != p[k]) { fails << (where + ' ' + k + ' = ' + g[k] + ', expected ' + p[k]) } }
  if (!sameNumber(g.amount, p.amount)) { fails << (where + ' amount = ' + g.amount + ', expected ' + p.amount) }
  if (!sameInstant(g.updatedAtUtc, p.updatedAtUtc)) { fails << (where + ' updatedAtUtc = ' + g.updatedAtUtc + ', expected ' + p.updatedAtUtc) }
  if ((g.confirmedAtUtc == null) != (p.confirmedAtUtc == null) || (p.confirmedAtUtc != null && !sameInstant(g.confirmedAtUtc, p.confirmedAtUtc))) { fails << (where + ' confirmedAtUtc = ' + g.confirmedAtUtc + ', expected ' + p.confirmedAtUtc) }
}
if (j instanceof Map && j.pendingTransfers instanceof Map && j.income instanceof Map) {
  if (j.pendingTransfers.totalCount != e.pendingTotal) { fails << ('pendingTransfers.totalCount = ' + j.pendingTransfers.totalCount + ', expected ' + e.pendingTotal) }
  def pids = j.pendingTransfers.items.collect { it.id }
  if (pids != e.pendingIds) { fails << ('pending ids/order ' + pids + ', expected (oldest update first, rejected receipt excluded) ' + e.pendingIds) }
  else { j.pendingTransfers.items.each { g -> comparePayment(g, pay(g.id), 'pending payment ' + g.id) } }
  def rids = j.recentPayments.collect { it.id }
  if (rids != e.recentIds) { fails << ('recent ids/order ' + rids + ', expected (newest confirmation first, future-dated and undated excluded) ' + e.recentIds) }
  else { j.recentPayments.each { g -> comparePayment(g, pay(g.id), 'recent payment ' + g.id) } }
  // income: recomputed independently from the payment list at the time the SERVER reports (Asia/Colombo calendar day and month)
  def asOf = java.time.Instant.parse(String.valueOf(j.income.asOfUtc)); def zone = java.time.ZoneId.of('Asia/Colombo'); def local = asOf.atZone(zone)
  def dayStart = local.toLocalDate().atStartOfDay(zone).toInstant(); def monthStart = local.toLocalDate().withDayOfMonth(1).atStartOfDay(zone).toInstant()
  def ok = e.payments.findAll { it.status == 'Successful' }
  def datedOk = ok.findAll { it.confirmedAtUtc != null && !java.time.Instant.parse(it.confirmedAtUtc).isAfter(asOf) }
  def sum = { List l -> l.inject(java.math.BigDecimal.ZERO) { a, p -> a + num(p.amount) } }
  def today = sum(datedOk.findAll { !java.time.Instant.parse(it.confirmedAtUtc).isBefore(dayStart) }); def month = sum(datedOk.findAll { !java.time.Instant.parse(it.confirmedAtUtc).isBefore(monthStart) })
  def undated = ok.findAll { it.confirmedAtUtc == null }
  if (!sameNumber(j.income.todayAmount, today)) { fails << ('income.todayAmount = ' + j.income.todayAmount + ', expected ' + today) }
  if (!sameNumber(j.income.monthAmount, month)) { fails << ('income.monthAmount = ' + j.income.monthAmount + ', expected ' + month) }
  if (j.income.undatedSuccessfulCount != undated.size()) { fails << ('income.undatedSuccessfulCount = ' + j.income.undatedSuccessfulCount + ', expected ' + undated.size()) }
  if (!sameNumber(j.income.undatedSuccessfulAmount, sum(undated))) { fails << ('income.undatedSuccessfulAmount = ' + j.income.undatedSuccessfulAmount + ', expected ' + sum(undated)) }
}
['51109', '51110', '51112'].each { n -> if (raw.contains('CN-APT-DSH-' + n) && n != '51112' ) { fails << ('a payment that must be excluded appears: CN-APT-DSH-' + n) } }
if (raw.contains('CN-APT-DSH-51112')) { fails << 'a payment older than the five most recent appears: CN-APT-DSH-51112' }
"""
DOCTOR_CHECK = r"""
def j = parse()
def e = fx.doctor
def FIELDS = ['id', 'appointmentReference', 'patientId', 'patientName', 'patientPhone', 'appointmentStartUtc', 'appointmentEndUtc', 'status', 'updatedAtUtc', 'paymentMethod', 'paymentStatus', 'isToday', 'isUpcoming', 'isCompleted', 'isHistory', 'allowedStatuses', 'contactsUnavailable']
if (j instanceof Map) {
  keysAre(j, ['appointments', 'statistics', 'contactsUnavailable'], 'doctor appointments')
  def got = j.appointments ?: []
  if (got.collect { it.id } != e.ids) { fails << ('appointment ids/order ' + got.collect { it.id } + ', expected (start, id) ' + e.ids) }
  else { got.eachWithIndex { g, i -> def x = e.appointments[i]; keysAre(g, FIELDS, 'appointment ' + x.id)
    if (g.appointmentReference != x.appointmentReference || g.patientId != x.patientId || g.status != x.status || g.paymentMethod != x.paymentMethod || g.paymentStatus != x.paymentStatus) { fails << ('appointment ' + x.id + ' differs from the fixture') }
    ['isToday', 'isUpcoming', 'isCompleted', 'isHistory'].each { k -> if (g[k] != x.doctorExpect[k]) { fails << ('appointment ' + x.id + ' ' + k + ' = ' + g[k] + ', expected ' + x.doctorExpect[k]) } }
    if (g.allowedStatuses != x.doctorExpect.allowedStatuses) { fails << ('appointment ' + x.id + ' allowedStatuses ' + g.allowedStatuses + ', expected ' + x.doctorExpect.allowedStatuses) }
    if (g.patientName != null || g.patientPhone != null || g.contactsUnavailable != true) { fails << ('appointment ' + x.id + ': contacts should be unavailable (user-auth service is absent in this isolated environment)') }
    if (!sameInstant(g.appointmentStartUtc, x.startUtc)) { fails << ('appointment ' + x.id + ' start differs') } } }
  ['today', 'upcoming', 'completed', 'patientCount'].each { k -> if (j.statistics?.get(k) != e.statistics[k]) { fails << ('statistics.' + k + ' = ' + j.statistics?.get(k) + ', expected ' + e.statistics[k]) } }
  if (j.contactsUnavailable != true) { fails << 'contactsUnavailable should be true' }
}
e.foreignIds.each { id -> if (raw.contains('CN-APT-DSH-' + id)) { fails << ('response contains an appointment of another doctor: ' + id) } }
"""
EMPTY_BODY = r"""
if (raw.length() != 0) { fails << ('the body should be empty (the authentication/authorization middleware answers without a body), but has ' + raw.length() + ' bytes') }
fx.appointments.each { a -> if (a.appointmentReference != null && raw.contains(a.appointmentReference)) { fails << 'the denied response contains appointment data' } }
"""
JSON_CT = header_has("application/json", "Content-Type is JSON")
H_JSON = ("Accept", "application/json")

def sampler_with(label, path, auth, asserts, actor):
    hdr = headers(([("Authorization", "Bearer ${TOKEN}")] if auth else []) + [H_JSON])
    return sampler(label, "GET", path, None, [hdr, jsr("pre", "Local JWT, guarded target and fixtures (never an HTTP call)", pre_script(actor)), ENV_ASSERT] + list(asserts))
def dur(ms): return duration(ms)
SANITY = 3000; REPEAT = 1500          # documented thresholds in ms: sanity caps on a local development machine, NOT service levels
PD = "/api/patient/dashboard/appointments"; SD = "/api/staff/dashboard/appointment-payments"; DD = "/api/doctor/appointments"
PAT = ("Patient", "patient1"); STF = ("PharmacyStaff", "staff"); DOC = ("Doctor", "doctor1")
def tg(sid, name, comment, samplers, loops=1): return thread_group(f"{sid} {name}", comment, samplers, loops)
JM = [
 tg("J01", "Patient dashboard summary", "GET the patient appointment dashboard as patient 1: 200, JSON, the full documented contract (fields, types, limits, fresh UTC timestamps).",
    [sampler_with("J01 Patient dashboard summary", PD, True, [code_is(200), JSON_CT, vassert("Patient dashboard honours the documented contract", PATIENT_CONTRACT), dur(SANITY)], PAT)]),
 tg("J02", "Patient dashboard counts and preview", "GET the patient appointment dashboard as patient 1: upcoming count 7, the first five appointments in (start, id) order with payment method/status, payment-status counts of ALL the patient's payments, nothing of other patients.",
    [sampler_with("J02 Patient dashboard counts and preview", PD, True, [code_is(200), JSON_CT, vassert("Counts, preview rows and payment-status counts equal the seeded fixtures", PATIENT_VALUES), dur(SANITY)], PAT)]),
 tg("J03", "Pharmacy staff dashboard summary", "GET the staff appointment-payment dashboard as pharmacy staff: 200, JSON, the full documented contract.",
    [sampler_with("J03 Pharmacy staff dashboard summary", SD, True, [code_is(200), JSON_CT, vassert("Staff dashboard honours the documented contract", STAFF_CONTRACT), dur(SANITY)], STF)]),
 tg("J04", "Pharmacy staff payments and income", "GET the staff appointment-payment dashboard: 6 pending bank transfers (5 shown, oldest update first, the rejected receipt excluded), the 5 newest dated confirmed payments (future-dated and undated excluded), income recomputed independently for today and this month in Asia/Colombo, undated successful payments reported separately.",
    [sampler_with("J04 Pharmacy staff payments and income", SD, True, [code_is(200), JSON_CT, vassert("Pending transfers, recent payments and income equal the independent oracle", STAFF_VALUES), dur(SANITY)], STF)]),
 tg("J05", "Doctor appointments data", "No doctor DASHBOARD endpoint exists in this backend (DoctorDashboardController is an empty file); the doctor dashboard reads GET /api/doctor/appointments. As doctor 1: statistics and the complete ordered list equal the fixtures, another doctor's appointment is absent, contacts are reported unavailable.",
    [sampler_with("J05 Doctor appointments data", DD, True, [code_is(200), JSON_CT, vassert("Doctor statistics and appointment list equal the seeded fixtures", DOCTOR_CHECK), dur(SANITY)], DOC)]),
 tg("J06", "Unauthenticated dashboard request", "GET the staff payments dashboard WITHOUT any token: 401 and an empty body, no payment or appointment data. One request, one endpoint (the more sensitive one); the patient dashboard's 401 is covered by the backend xUnit tests.",
    [sampler_with("J06 Unauthenticated staff dashboard", SD, False, [code_is(401), vassert("Empty body, no payment or appointment data", EMPTY_BODY), dur(SANITY)], None)]),
 tg("J07", "Patient on the staff-only dashboard", "GET the staff dashboard with a valid PATIENT token: 403 and an empty body.",
    [sampler_with("J07 Patient on the staff dashboard", SD, True, [code_is(403), vassert("Empty body, no payment or income data", EMPTY_BODY), dur(SANITY)], PAT)]),
 tg("J08", "Staff on the patient-only dashboard", "GET the patient dashboard with a valid PHARMACY STAFF token: 403 and an empty body.",
    [sampler_with("J08 Staff on the patient dashboard", PD, True, [code_is(403), vassert("Empty body, no appointment data", EMPTY_BODY), dur(SANITY)], STF)]),
 tg("J09", "Response time and repeated-request stability", "ONE sampler looped 30 times (one thread, no think time): GET staff payments dashboard as pharmacy staff, the aggregation-heavy endpoint. Every response is 200 with values EQUAL to the fixtures (stable), each within the per-request cap; the mean and the 95th percentile over the 30 samples are checked by the summary against documented thresholds. NOT a load test.",
    [sampler_with("J09 Staff dashboard repeated", SD, True, [code_is(200), JSON_CT, vassert("Stable values: pending transfers, recent payments and income equal the oracle on every iteration", STAFF_VALUES), dur(REPEAT)], STF)], loops=30),
]

SAVE = ('<objProp><name>saveConfig</name><value class="SampleSaveConfiguration"><time>true</time><latency>true</latency><timestamp>true</timestamp><success>true</success><label>true</label><code>true</code><message>true</message>'
        '<threadName>true</threadName><dataType>true</dataType><encoding>false</encoding><assertions>true</assertions><subresults>true</subresults><responseData>false</responseData><samplerData>false</samplerData><xml>false</xml>'
        '<fieldNames>true</fieldNames><responseHeaders>false</responseHeaders><requestHeaders>false</requestHeaders><responseDataOnError>false</responseDataOnError><saveAssertionResultsFailureMessage>true</saveAssertionResultsFailureMessage>'
        '<assertionsResultsToSave>0</assertionsResultsToSave><bytes>true</bytes><sentBytes>true</sentBytes><url>true</url><threadCounts>true</threadCounts><idleTime>true</idleTime><connectTime>true</connectTime></value></objProp>')
def listener(gui, name): return (f'<ResultCollector guiclass="{gui}" testclass="ResultCollector" testname={a(name)} enabled="true"><boolProp name="ResultCollector.error_logging">false</boolProp>{SAVE}<stringProp name="filename"></stringProp></ResultCollector>') + ht()
doc = ('<?xml version="1.0" encoding="UTF-8"?>\n<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3"><hashTree><TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="GCN-51 Role Dashboards API (9 scenarios, read-only)" enabled="true">'
       '<stringProp name="TestPlan.comments">GCN-51 QA. LOCAL only: backend localhost:5251 (properties gcn51.host / gcn51.port, guarded: anything else is refused), isolated database carenova_appointment_gcn51_qa, synthetic data. 9 scenarios J01..J09, exactly 9 read-only GET samplers (one per scenario), 38 requests in a run (J09 loops its sampler 30 times), one thread. No setup, authentication, health-check or teardown request; no writes. Functional, response-time and repeated-request stability check: NOT a load or concurrency test. No secrets in this file. Run it through run-gcn51-jmeter.sh, never from the GUI.</stringProp>'
       '<boolProp name="TestPlan.functional_mode">false</boolProp><boolProp name="TestPlan.tearDown_on_shutdown">true</boolProp><boolProp name="TestPlan.serialize_threadgroups">true</boolProp>'
       '<elementProp name="TestPlan.user_defined_variables" elementType="Arguments" guiclass="ArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true"><collectionProp name="Arguments.arguments"/></elementProp>'
       '<stringProp name="TestPlan.user_define_classpath"></stringProp></TestPlan>' + ht(listener("SummaryReport", "Summary Report") + listener("ViewResultsFullVisualizer", "View Results Tree") + "".join(JM)) + '</hashTree></jmeterTestPlan>\n')
open(os.path.join(OUT, "GCN51RoleDashboardTest.jmx"), "w").write(doc)

SC = {
 "J01": {"name": "Patient dashboard summary", "method": "GET", "path": PD, "role": "Patient", "expected_status": 200, "requests": 1, "threshold_ms": SANITY},
 "J02": {"name": "Patient dashboard counts and preview", "method": "GET", "path": PD, "role": "Patient", "expected_status": 200, "requests": 1, "threshold_ms": SANITY},
 "J03": {"name": "Pharmacy staff dashboard summary", "method": "GET", "path": SD, "role": "PharmacyStaff", "expected_status": 200, "requests": 1, "threshold_ms": SANITY},
 "J04": {"name": "Pharmacy staff payments and income", "method": "GET", "path": SD, "role": "PharmacyStaff", "expected_status": 200, "requests": 1, "threshold_ms": SANITY},
 "J05": {"name": "Doctor appointments data", "method": "GET", "path": DD, "role": "Doctor", "expected_status": 200, "requests": 1, "threshold_ms": SANITY,
         "note": "REPLACEMENT: this backend has no doctor dashboard endpoint (DoctorDashboardController is empty); the doctor dashboard reads this GCN-47 endpoint."},
 "J06": {"name": "Unauthenticated dashboard request", "method": "GET", "path": SD, "role": "none", "expected_status": 401, "requests": 1, "threshold_ms": SANITY},
 "J07": {"name": "Patient on the staff-only dashboard", "method": "GET", "path": SD, "role": "Patient", "expected_status": 403, "requests": 1, "threshold_ms": SANITY},
 "J08": {"name": "Staff on the patient-only dashboard", "method": "GET", "path": PD, "role": "PharmacyStaff", "expected_status": 403, "requests": 1, "threshold_ms": SANITY},
 "J09": {"name": "Response time and repeated-request stability", "method": "GET", "path": SD, "role": "PharmacyStaff", "expected_status": 200, "requests": 30, "threshold_ms": REPEAT,
         "mean_threshold_ms": 400, "p95_threshold_ms": 750, "iterations": 30},
}
json.dump({"total_requests": 38, "samplers": 9, "threads_per_scenario": 1, "read_only": True,
           "note": "Functional, response-time and repeated-request stability check on one thread. Not a load, concurrency or capacity test. Thresholds are sanity limits for a local development machine, not service levels.",
           "scenarios": SC}, open(os.path.join(OUT, "scenarios.json"), "w"), indent=2)
print("wrote JMX and scenarios.json: 9 scenarios, 9 HTTP samplers, 38 requests per run")
