#!/usr/bin/env python3
"""Generates GCN53AdminDashboardTest.jmx and scenarios.json: EXACTLY six logical scenarios J01..J06 (24 read-only GET samplers, 66 requests per run; J06 loops three samplers 15 times; one thread).
HOW THE "NO EXTRA HTTP REQUEST" RULE IS MET: there is no setup, authentication, health-check or teardown sampler and no JSR223 *sampler* at all. Everything that is not the
requests (local JWT minting, fixture loading and the environment sanity flag) happens inside JSR223 PRE-processors attached to the 9 samplers and is never an HTTP call.
The plan contains NO secret: tokens are minted at run time from GCN53_JWT_SECRET in the JMeter process environment.
No script text contains the characters dollar-brace (JMeter would interpolate them); Groovy uses string concatenation."""
import json, os
from xml.sax.saxutils import escape, quoteattr
a = quoteattr
OUT = os.path.dirname(os.path.abspath(__file__))
PORT = "5253"
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
    """actor = None (no token) or (role, key in fixtures.actors)."""
    return LIB + r"""
def why = []
def secret = System.getenv('GCN53_JWT_SECRET')
if (!secret) { why << 'GCN53_JWT_SECRET is not in the environment of the JMeter process' }
// the target is configurable by JMeter properties but GUARDED: anything but the isolated QA backend is replaced by an address that cannot connect
String host = props.get('gcn53.host') ?: 'localhost'; String port = props.get('gcn53.port') ?: '5253'
if (!(host in ['localhost', '127.0.0.1']) || port != '5253') { why << ('refused target ' + host + ':' + port + ' (only localhost:5253 is allowed)'); host = 'target-refused.invalid'; port = '1' }
vars.put('HOST', host); vars.put('PORT', port)
def fx = null
def f = new File(props.get('fixturesFile') ?: '')
if (!f.exists()) { why << 'fixtures file missing' } else {
  fx = deep(new JsonSlurper().parseText(f.text))
  if (fx.synthetic != true) { why << 'fixtures are not marked synthetic' }
  if (java.time.Instant.now().isAfter(java.time.Instant.parse(fx.validUntilUtc))) { why << 'fixtures are older than 72 hours: re-seed a new empty database' }
  vars.put('REPORT_FROM', fx.report.from); vars.put('REPORT_TO', fx.report.to); vars.put('BAD_FROM', fx.report.badFrom); vars.put('BAD_TO', fx.report.badTo)
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
def zone = java.time.ZoneId.of('Asia/Colombo')
def inst = { String s -> java.time.Instant.parse(s) }
def colomboDayStart = { java.time.Instant now -> now.atZone(zone).toLocalDate().atStartOfDay(zone).toInstant() }
def comparePayment = { Map g, Map p, String where ->
  ['appointmentId', 'reference', 'method', 'status'].each { k -> if (g[k] != p[k]) { fails << (where + ' ' + k + ' = ' + g[k] + ', expected ' + p[k]) } }
  if (!sameNumber(g.amount, p.amount)) { fails << (where + ' amount = ' + g.amount + ', expected ' + p.amount) }
  if (!sameInstant(g.updatedAtUtc, p.updatedAtUtc)) { fails << (where + ' updatedAtUtc differs') }
  if ((g.confirmedAtUtc == null) != (p.confirmedAtUtc == null) || (p.confirmedAtUtc != null && !sameInstant(g.confirmedAtUtc, p.confirmedAtUtc))) { fails << (where + ' confirmedAtUtc = ' + g.confirmedAtUtc + ', expected ' + p.confirmedAtUtc) }
}
"""
def vassert(name, body): return jsr("assert", name, VERIFY + body + "\nfinish(fails)")

DASH_APPTS = r"""
def j = parse()
def e = fx.dashboard
if (j instanceof Map) {
  keysAre(j, ['totalAppointments', 'statusCounts', 'todayCount', 'upcomingCount', 'recentAppointments', 'generatedAtUtc'], 'appointment summary')
  if (!fresh(j.generatedAtUtc)) { fails << ('generatedAtUtc is not fresh: ' + j.generatedAtUtc) }
  if (j.totalAppointments != e.totalAppointments) { fails << ('totalAppointments = ' + j.totalAppointments + ', expected ' + e.totalAppointments) }
  if ((j.statusCounts ?: [:]) != e.statusCounts) { fails << ('statusCounts ' + j.statusCounts + ', expected ' + e.statusCounts) }
  if ((j.statusCounts ?: [:]).values().sum() != j.totalAppointments) { fails << 'statusCounts do not add up to totalAppointments' }
  // today / upcoming depend on the CURRENT time: recomputed here from the seeded appointments at the time the server reports (Asia/Colombo calendar day)
  if (isUtc(j.generatedAtUtc)) {
    def now = inst(j.generatedAtUtc); def ds = colomboDayStart(now); def de = ds.plus(java.time.Duration.ofDays(1))
    def today = fx.appointments.count { !inst(it.startUtc).isBefore(ds) && inst(it.startUtc).isBefore(de) }
    def upcoming = fx.appointments.count { inst(it.startUtc).isAfter(now) && (it.status == 'Booked' || it.status == 'Confirmed') }
    if (j.todayCount != today) { fails << ('todayCount = ' + j.todayCount + ', expected ' + today) }
    if (j.upcomingCount != upcoming) { fails << ('upcomingCount = ' + j.upcomingCount + ', expected ' + upcoming) }
  }
  def got = j.recentAppointments ?: []
  if (got.size() > 5) { fails << 'more than five recent appointments' }
  if (got.collect { it.id } != e.recentIds) { fails << ('recent ids/order ' + got.collect { it.id } + ', expected (newest first) ' + e.recentIds) }
  else { got.eachWithIndex { g, i -> def x = e.recent[i]; keysAre(g, ['id', 'reference', 'doctorName', 'startUtc', 'status', 'paymentMethod', 'paymentStatus'], 'recent ' + x.id)
    ['reference', 'doctorName', 'status', 'paymentMethod', 'paymentStatus'].each { k -> if (g[k] != x[k]) { fails << ('recent ' + x.id + ' ' + k + ' = ' + g[k] + ', expected ' + x[k]) } }
    if (!sameInstant(g.startUtc, x.startUtc)) { fails << ('recent ' + x.id + ' startUtc differs') } } }
}
"""
DASH_PAY = r"""
def j = parse()
def e = fx.payments
def pay = { int id -> e.payments.find { it.id == id } }
if (j instanceof Map && j.pendingTransfers instanceof Map && j.income instanceof Map) {
  keysAre(j, ['totalPayments', 'statusCounts', 'pendingTransfers', 'recentPayments', 'income', 'generatedAtUtc'], 'payment summary')
  keysAre(j.pendingTransfers, ['totalCount', 'items'], 'pendingTransfers')
  keysAre(j.income, ['todayAmount', 'monthAmount', 'undatedSuccessfulCount', 'undatedSuccessfulAmount', 'currency', 'timeZone', 'asOfUtc'], 'income')
  if (j.totalPayments != e.totalPayments) { fails << ('totalPayments = ' + j.totalPayments + ', expected ' + e.totalPayments) }
  if ((j.statusCounts ?: [:]) != e.statusCounts) { fails << ('statusCounts ' + j.statusCounts + ', expected ' + e.statusCounts) }
  if (j.pendingTransfers.totalCount != e.pendingTotal) { fails << ('pendingTransfers.totalCount = ' + j.pendingTransfers.totalCount + ', expected ' + e.pendingTotal + ' (a payment whose receipt was rejected must not count)') }
  def pids = j.pendingTransfers.items.collect { it.id }
  if (pids != e.pendingIds) { fails << ('pending ids ' + pids + ', expected ' + e.pendingIds) } else { j.pendingTransfers.items.each { g -> comparePayment(g, pay(g.id), 'pending payment ' + g.id) } }
  if (j.currency != null || j.income.currency != 'LKR' || j.income.timeZone != 'Asia/Colombo') { fails << ('currency/timeZone ' + j.income.currency + '/' + j.income.timeZone) }
  if (!fresh(j.generatedAtUtc) || !fresh(j.income.asOfUtc)) { fails << 'generatedAtUtc / asOfUtc are not fresh' }
  else {
    def asOf = inst(String.valueOf(j.income.asOfUtc)); def ds = colomboDayStart(asOf); def ms = asOf.atZone(zone).toLocalDate().withDayOfMonth(1).atStartOfDay(zone).toInstant()
    def ok = e.payments.findAll { it.status == 'Successful' }
    def dated = ok.findAll { it.confirmedAtUtc != null && !inst(it.confirmedAtUtc).isAfter(asOf) }
    def sum = { List l -> l.inject(java.math.BigDecimal.ZERO) { a, p -> a + num(p.amount) } }
    def today = sum(dated.findAll { !inst(it.confirmedAtUtc).isBefore(ds) }); def month = sum(dated.findAll { !inst(it.confirmedAtUtc).isBefore(ms) }); def undated = ok.findAll { it.confirmedAtUtc == null }
    if (!sameNumber(j.income.todayAmount, today)) { fails << ('income.todayAmount = ' + j.income.todayAmount + ', expected ' + today) }
    if (!sameNumber(j.income.monthAmount, month)) { fails << ('income.monthAmount = ' + j.income.monthAmount + ', expected ' + month) }
    if (j.income.undatedSuccessfulCount != undated.size() || !sameNumber(j.income.undatedSuccessfulAmount, sum(undated))) { fails << ('undated successful ' + j.income.undatedSuccessfulCount + '/' + j.income.undatedSuccessfulAmount + ', expected ' + undated.size() + '/' + sum(undated)) }
    def recent = dated.sort { a, b -> inst(b.confirmedAtUtc) <=> inst(a.confirmedAtUtc) ?: b.id <=> a.id }.take(5).collect { it.id }
    def rids = j.recentPayments.collect { it.id }
    if (rids != recent) { fails << ('recent payment ids ' + rids + ', expected (newest confirmation first, future-dated and undated excluded) ' + recent) } else { j.recentPayments.each { g -> comparePayment(g, pay(g.id), 'recent payment ' + g.id) } }
  }
}
"""
def list_check(qn): return r"""
def qn = '""" + qn + r"""'
def j = parse()
def e = fx.queries[qn]
if (j instanceof Map) {
  keysAre(j, ['items', 'totalCount', 'page', 'pageSize', 'totalPages'], 'appointment list')
  ['totalCount', 'page', 'pageSize', 'totalPages'].each { k -> if (j[k] != e[k]) { fails << (k + ' = ' + j[k] + ', expected ' + e[k]) } }
  def got = j.items ?: []
  if (got.collect { it.id } != e.ids) { fails << ('item ids/order ' + got.collect { it.id } + ', expected (newest first) ' + e.ids) }
  else { got.eachWithIndex { g, i -> def x = e.rows[i]; keysAre(g, ['id', 'reference', 'patientId', 'doctorName', 'startUtc', 'status', 'paymentMethod', 'paymentStatus'], 'item ' + x.id)
    ['reference', 'patientId', 'doctorName', 'status', 'paymentMethod', 'paymentStatus'].each { k -> if (g[k] != x[k]) { fails << ('item ' + x.id + ' ' + k + ' = ' + g[k] + ', expected ' + x[k]) } }
    if (!sameInstant(g.startUtc, x.startUtc) || !String.valueOf(g.startUtc).endsWith('Z')) { fails << ('item ' + x.id + ' startUtc = ' + g.startUtc + ', expected ' + x.startUtc) } } }
}
"""
REPORT = r"""
def j = parse()
def e = fx.report
if (j instanceof Map) {
  keysAre(j, ['days', 'undatedSuccessfulCount', 'currency', 'timeZone', 'generatedAtUtc'], 'income report')
  if (j.currency != 'LKR' || j.timeZone != 'Asia/Colombo') { fails << ('currency/timeZone ' + j.currency + '/' + j.timeZone) }
  if (!fresh(j.generatedAtUtc)) { fails << ('generatedAtUtc is not fresh: ' + j.generatedAtUtc) }
  else {
    def now = inst(String.valueOf(j.generatedAtUtc)); def from = inst(e.from); def to = inst(e.to)
    def ok = e.payments.findAll { it.status == 'Successful' }
    def inWindow = ok.findAll { it.confirmedAtUtc != null && !inst(it.confirmedAtUtc).isBefore(from) && inst(it.confirmedAtUtc).isBefore(to) && !inst(it.confirmedAtUtc).isAfter(now) }
    def byDay = new TreeMap(); inWindow.each { p -> def d = inst(p.confirmedAtUtc).atZone(zone).toLocalDate().toString(); def cur = byDay[d] ?: [amount: java.math.BigDecimal.ZERO, count: 0]; byDay[d] = [amount: cur.amount + num(p.amount), count: cur.count + 1] }
    def got = j.days ?: []
    if (got.collect { it.date } != byDay.keySet().toList()) { fails << ('days ' + got.collect { it.date } + ', expected (ascending Sri Lanka dates) ' + byDay.keySet().toList()) }
    else { got.each { g -> keysAre(g, ['date', 'amount', 'count'], 'day ' + g.date); def x = byDay[g.date]
      if (!sameNumber(g.amount, x.amount) || g.count != x.count) { fails << ('day ' + g.date + ' = ' + g.amount + '/' + g.count + ', expected ' + x.amount + '/' + x.count) } } }
    if (got.size() < 3) { fails << 'the fixtures should produce at least three Sri Lanka dates' }
    if (j.undatedSuccessfulCount != ok.count { it.confirmedAtUtc == null }) { fails << ('undatedSuccessfulCount = ' + j.undatedSuccessfulCount) }
    // the two confirmations either side of Colombo midnight (seconds apart in UTC) must be on different dates
    def a = e.payments.find { it.id == 53001 }; def b = e.payments.find { it.id == 53002 }
    def da = inst(a.confirmedAtUtc).atZone(zone).toLocalDate().toString(); def db = inst(b.confirmedAtUtc).atZone(zone).toLocalDate().toString()
    if (da == db || !got.any { it.date == da } || !got.any { it.date == db }) { fails << 'the Sri Lanka midnight boundary is not reflected in the grouping' }
  }
}
"""
def bad400(msg): return r"""
def j = parse()
if (j instanceof Map) {
  keysAre(j, ['message'], 'error body')
  if (j.message != '""" + msg + r"""') { fails << ('message = ' + j.message) }
}
if (raw.contains('Exception') || raw.contains('   at ')) { fails << 'the error body discloses a stack trace' }
"""
EMPTY_BODY = r"""
if (raw.length() != 0) { fails << ('the body should be empty (the authentication/authorization middleware answers without a body), but has ' + raw.length() + ' bytes') }
fx.appointments.each { a -> if (raw.contains(a.appointmentReference)) { fails << 'the denied response contains appointment data' } }
"""
JSON_CT = header_has("application/json", "Content-Type is JSON")
H_JSON = ("Accept", "application/json")

SANITY = 3000; REPEAT = 1500      # documented per-request caps in ms: sanity limits on a local development machine, NOT service levels
def S(label, path, actor, status, checks, ms=SANITY):
    asserts = [code_is(status)] + ([JSON_CT] if status == 200 or status == 400 else []) + [vassert(n, b) for n, b in checks] + [duration(ms)]
    hdr = headers(([("Authorization", "Bearer ${TOKEN}")] if actor else []) + [H_JSON])
    return sampler(label, "GET", path, None, [hdr, jsr("pre", "Local JWT, guarded target and fixtures (never an HTTP call)", pre_script(actor)), ENV_ASSERT] + asserts)
DA = "/api/admin/dashboard/appointments"; DP = "/api/admin/dashboard/appointment-payments"; AL = "/api/admin/appointments"; RP = "/api/admin/reports/appointment-income"
ADMIN = ("Admin", "admin"); PAT = ("Patient", "patient"); DOC = ("Doctor", "doctor"); STF = ("PharmacyStaff", "staff")
RPQ = RP + "?from=${REPORT_FROM}&to=${REPORT_TO}"
def tg(sid, name, comment, samplers, loops=1): return thread_group(f"{sid} {name}", comment, samplers, loops)
JM = [
 tg("J01", "Admin dashboard appointment summary", "GET the admin appointment summary and the admin appointment-payment summary as Admin: 200, JSON, exact contract; totals and status counts equal the fixtures and add up; today / upcoming recomputed independently for Asia/Colombo; the five newest appointments (newest first) with payment method and status; pending bank transfers exclude the rejected receipt; income today/month and undated payments equal the oracle; recent payments limited to five, newest confirmation first.",
    [S("J01a Admin appointment summary", DA, ADMIN, 200, [("Totals, status counts, today/upcoming and the five newest appointments equal the oracle", DASH_APPTS)]),
     S("J01b Admin appointment payment summary", DP, ADMIN, 200, [("Payment counts, pending transfers, recent payments and income equal the oracle", DASH_PAY)])]),
 tg("J02", "Admin appointment listing", "GET the admin appointment list as Admin: default page, page 2 with size 5 (pagination), a doctor-name search, a reference search on page 2 (4 of 9), and an invalid page size (101) rejected with 400 and the documented message.",
    [S("J02a Admin appointment list default page", AL, ADMIN, 200, [("All 14 appointments, newest first, with payment details, totals and page counts equal the fixtures", list_check("default"))]),
     S("J02b Admin appointment list page 2", AL + "?page=2&pageSize=5", ADMIN, 200, [("Page 2 of 3: items 6-10 in order, totalCount 14, totalPages 3", list_check("page2"))]),
     S("J02c Admin appointment list search by doctor", AL + "?search=Admin-B&page=1&pageSize=20", ADMIN, 200, [("Only the 7 appointments of doctor B, newest first", list_check("search"))]),
     S("J02d Admin appointment list reference search page 2", AL + "?search=CN-APT-ADM-5300&page=2&pageSize=5", ADMIN, 200, [("9 matches, page 2 holds the last 4", list_check("reference"))]),
     S("J02e Admin appointment list invalid page size", AL + "?pageSize=101", ADMIN, 400, [("400 with exactly the documented message and no stack trace", bad400("Check the search and page values."))])]),
 tg("J03", "Admin appointment income report", "GET the appointment income report for a 21-day window as Admin: 200, days grouped by Asia/Colombo date in ascending order with amount and count, the two confirmations seconds either side of Sri Lanka midnight on different dates, future-dated and undated payments excluded from the days and the undated ones counted separately, currency LKR; a 40-day window is rejected with 400 and the documented message.",
    [S("J03a Admin income report", RPQ, ADMIN, 200, [("Date grouping, daily totals and counts, undated count and currency equal the oracle", REPORT)]),
     S("J03b Admin income report period too long", RP + "?from=${BAD_FROM}&to=${BAD_TO}", ADMIN, 400, [("400 with exactly the documented message and no stack trace", bad400("Choose a reporting period of at most 32 days."))])]),
 tg("J04", "Unauthenticated access", "GET each of the four admin endpoints WITHOUT any token: 401 and an empty body, no appointment data.",
    [S("J04a Unauthenticated appointment summary", DA, None, 401, [("Empty body, no appointment data", EMPTY_BODY)]),
     S("J04b Unauthenticated payment summary", DP, None, 401, [("Empty body, no appointment data", EMPTY_BODY)]),
     S("J04c Unauthenticated appointment list", AL, None, 401, [("Empty body, no appointment data", EMPTY_BODY)]),
     S("J04d Unauthenticated income report", RPQ, None, 401, [("Empty body, no appointment data", EMPTY_BODY)])]),
 tg("J05", "Non-admin access", "GET the admin endpoints with valid tokens of NON-admin roles: Patient on all four, PharmacyStaff on the summary and the list, Doctor on the payment summary and the report: 403 and an empty body.",
    [S("J05a Patient on appointment summary", DA, PAT, 403, [("Empty body", EMPTY_BODY)]), S("J05b Patient on payment summary", DP, PAT, 403, [("Empty body", EMPTY_BODY)]),
     S("J05c Patient on appointment list", AL, PAT, 403, [("Empty body", EMPTY_BODY)]), S("J05d Patient on income report", RPQ, PAT, 403, [("Empty body", EMPTY_BODY)]),
     S("J05e PharmacyStaff on appointment summary", DA, STF, 403, [("Empty body", EMPTY_BODY)]), S("J05f PharmacyStaff on appointment list", AL, STF, 403, [("Empty body", EMPTY_BODY)]),
     S("J05g Doctor on payment summary", DP, DOC, 403, [("Empty body", EMPTY_BODY)]), S("J05h Doctor on income report", RPQ, DOC, 403, [("Empty body", EMPTY_BODY)])]),
 tg("J06", "Repeated dashboard requests", "15 sequential iterations (one thread, no think time) of GET appointment summary + GET payment summary + GET appointment list (page 1, size 5) as Admin: every response 200 with values EQUAL to the oracle (consistent), each within the per-request cap; average, median and 95th-percentile times per request type and overall are computed by the summary against documented thresholds. NOT a load or concurrency test.",
    [S("J06a Repeated appointment summary", DA, ADMIN, 200, [("Stable values (appointment summary)", DASH_APPTS)], REPEAT),
     S("J06b Repeated payment summary", DP, ADMIN, 200, [("Stable values (payment summary)", DASH_PAY)], REPEAT),
     S("J06c Repeated appointment list", AL + "?page=1&pageSize=5", ADMIN, 200, [("Stable values (list, page 1 of 3)", list_check("repeat"))], REPEAT)], loops=15),
]

SAVE = ('<objProp><name>saveConfig</name><value class="SampleSaveConfiguration"><time>true</time><latency>true</latency><timestamp>true</timestamp><success>true</success><label>true</label><code>true</code><message>true</message>'
        '<threadName>true</threadName><dataType>true</dataType><encoding>false</encoding><assertions>true</assertions><subresults>true</subresults><responseData>false</responseData><samplerData>false</samplerData><xml>false</xml>'
        '<fieldNames>true</fieldNames><responseHeaders>false</responseHeaders><requestHeaders>false</requestHeaders><responseDataOnError>false</responseDataOnError><saveAssertionResultsFailureMessage>true</saveAssertionResultsFailureMessage>'
        '<assertionsResultsToSave>0</assertionsResultsToSave><bytes>true</bytes><sentBytes>true</sentBytes><url>true</url><threadCounts>true</threadCounts><idleTime>true</idleTime><connectTime>true</connectTime></value></objProp>')
def listener(gui, name): return (f'<ResultCollector guiclass="{gui}" testclass="ResultCollector" testname={a(name)} enabled="true"><boolProp name="ResultCollector.error_logging">false</boolProp>{SAVE}<stringProp name="filename"></stringProp></ResultCollector>') + ht()
doc = ('<?xml version="1.0" encoding="UTF-8"?>\n<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3"><hashTree><TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="GCN-53 Admin Dashboard API (6 scenarios, read-only)" enabled="true">'
       '<stringProp name="TestPlan.comments">GCN-53 QA. LOCAL only: backend localhost:5253 (properties gcn53.host / gcn53.port, guarded: anything else is refused), isolated database carenova_appointment_gcn53_qa, synthetic data. 6 logical scenarios J01..J06, 24 read-only GET samplers, 66 requests in a run (J06 loops three samplers 15 times), one thread. No setup, authentication, health-check or teardown request; no writes. Functional, response-time and repeated-request consistency check: NOT a load or concurrency test. No secrets in this file. Run it through run-gcn53-jmeter.sh, never from the GUI.</stringProp>'
       '<boolProp name="TestPlan.functional_mode">false</boolProp><boolProp name="TestPlan.tearDown_on_shutdown">true</boolProp><boolProp name="TestPlan.serialize_threadgroups">true</boolProp>'
       '<elementProp name="TestPlan.user_defined_variables" elementType="Arguments" guiclass="ArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true"><collectionProp name="Arguments.arguments"/></elementProp>'
       '<stringProp name="TestPlan.user_define_classpath"></stringProp></TestPlan>' + ht(listener("SummaryReport", "Summary Report") + listener("ViewResultsFullVisualizer", "View Results Tree") + "".join(JM)) + '</hashTree></jmeterTestPlan>\n')
open(os.path.join(OUT, "GCN53AdminDashboardTest.jmx"), "w").write(doc)

def sc(name, requests, status, role, endpoints, samplers=None, **extra): return {"name": name, "samplers": samplers or len(endpoints), "requests": requests, "expected_status": status, "role": role, "endpoints": endpoints, "threshold_ms": SANITY, **extra}
SC = {
 "J01": sc("Admin dashboard appointment summary", 2, 200, "Admin", [DA, DP]),
 "J02": sc("Admin appointment listing", 5, "200 x4, 400 x1", "Admin", [AL + "?...", AL + "?page=2&pageSize=5", AL + "?search=Admin-B", AL + "?search=CN-APT-ADM-5300&page=2", AL + "?pageSize=101"]),
 "J03": sc("Admin appointment income report", 2, "200, 400", "Admin", [RP + "?from&to (21 days)", RP + "?from&to (40 days)"]),
 "J04": sc("Unauthenticated access", 4, 401, "none", [DA, DP, AL, RP]),
 "J05": sc("Non-admin access", 8, 403, "Patient / PharmacyStaff / Doctor", [DA, DP, AL, RP], samplers=8),
 "J06": sc("Repeated dashboard requests", 45, 200, "Admin", [DA, DP, AL + "?page=1&pageSize=5"], iterations=15, threshold_ms=REPEAT, mean_threshold_ms=400, p95_threshold_ms=750),
}
assert sum(x["requests"] for x in SC.values()) == 66 and sum(x["samplers"] for x in SC.values()) == 24
json.dump({"total_requests": 66, "samplers": 24, "scenarios_count": 6, "read_only": True,
           "note": "Functional, response-time and repeated-request consistency check on one thread. Not a load, concurrency or capacity test. Thresholds are sanity limits for a local development machine, not service levels.",
           "scenarios": SC}, open(os.path.join(OUT, "scenarios.json"), "w"), indent=2)
print("wrote JMX and scenarios.json: 6 scenarios, 24 HTTP samplers, 66 requests per run")
