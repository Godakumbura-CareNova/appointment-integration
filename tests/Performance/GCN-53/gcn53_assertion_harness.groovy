// Runs the plan's OWN assertion and pre-processor scripts against correct and deliberately corrupted responses, offline (no JMeter, no HTTP, no server).
// args: fixtures.json  scripts-dir        Exit code 1 if any script behaves differently from what is expected.
import groovy.json.*
def fxFile = args[0]; def dir = args[1]
def fx = new JsonSlurper().parseText(new File(fxFile).text)
def wrong = 0
def run = { String script, Object body, String name, boolean expectFail ->
  def text = body instanceof String ? body : JsonOutput.toJson(body)
  def props = new Properties(); props.put('fixturesFile', fxFile)
  def prev = new Expando(); prev.getResponseDataAsString = { text }; prev.getResponseCode = { '200' }
  def result = new Expando(failed: false, msg: ''); result.setFailure = { b -> delegate.failed = b }; result.setFailureMessage = { m -> delegate.msg = m }
  try { new GroovyShell(new Binding([props: props, prev: prev, AssertionResult: result])).evaluate(new File(dir + '/' + script).text) } catch (Throwable t) { result.failed = true; result.msg = 'exception: ' + t.class.simpleName }
  def ok = result.failed == expectFail; if (!ok) wrong++
  println((ok ? 'OK    ' : 'WRONG ') + name + (result.failed ? '  -> detected: ' + result.msg.take(105) : '  -> accepted'))
}
def zone = java.time.ZoneId.of('Asia/Colombo'); def inst = { String s -> java.time.Instant.parse(s) }
def now = java.time.Instant.now().truncatedTo(java.time.temporal.ChronoUnit.SECONDS); def nowIso = now.toString()
def deepCopy; deepCopy = { x -> x instanceof Map ? x.collectEntries { k, v -> [(k): deepCopy(v)] } : (x instanceof List ? x.collect { deepCopy(it) } : x) }
def mutate = { Closure make, Closure change -> def b = deepCopy(make()); change(b); b }
// ---- good bodies, built independently of the plan's scripts
def dashGood = {
  def ds = now.atZone(zone).toLocalDate().atStartOfDay(zone).toInstant(); def de = ds.plusSeconds(86400)
  [totalAppointments: fx.dashboard.totalAppointments, statusCounts: new LinkedHashMap(fx.dashboard.statusCounts),
   todayCount: fx.appointments.findAll { !inst(it.startUtc).isBefore(ds) && inst(it.startUtc).isBefore(de) }.size(),
   upcomingCount: fx.appointments.findAll { inst(it.startUtc).isAfter(now) && it.status in ['Booked', 'Confirmed'] }.size(),
   recentAppointments: fx.dashboard.recent.collect { [id: it.id, reference: it.reference, doctorName: it.doctorName, startUtc: it.startUtc, status: it.status, paymentMethod: it.paymentMethod, paymentStatus: it.paymentStatus] }, generatedAtUtc: nowIso] }
def payRow = { id -> def p = fx.payments.payments.find { it.id == id }; [id: p.id, appointmentId: p.appointmentId, reference: p.reference, amount: new BigDecimal(p.amount), method: p.method, status: p.status, confirmedAtUtc: p.confirmedAtUtc, updatedAtUtc: p.updatedAtUtc] }
def payGood = {
  def ds = now.atZone(zone).toLocalDate().atStartOfDay(zone).toInstant(); def ms = now.atZone(zone).toLocalDate().withDayOfMonth(1).atStartOfDay(zone).toInstant()
  BigDecimal today = 0, month = 0, undAmt = 0; int und = 0; def dated = []
  fx.payments.payments.each { p -> if (p.status == 'Successful') { if (p.confirmedAtUtc == null) { und++; undAmt += new BigDecimal(p.amount) } else { def t = inst(p.confirmedAtUtc)
    if (!t.isAfter(now)) { dated << p; if (!t.isBefore(ds)) today += new BigDecimal(p.amount); if (!t.isBefore(ms)) month += new BigDecimal(p.amount) } } } }
  def recent = dated.sort { a, b -> inst(b.confirmedAtUtc) <=> inst(a.confirmedAtUtc) ?: b.id <=> a.id }.take(5)
  [totalPayments: fx.payments.totalPayments, statusCounts: new LinkedHashMap(fx.payments.statusCounts), pendingTransfers: [totalCount: fx.payments.pendingTotal, items: fx.payments.pendingIds.collect { payRow(it) }],
   recentPayments: recent.collect { payRow(it.id) }, income: [todayAmount: today, monthAmount: month, undatedSuccessfulCount: und, undatedSuccessfulAmount: undAmt, currency: 'LKR', timeZone: 'Asia/Colombo', asOfUtc: nowIso], generatedAtUtc: nowIso] }
def listGood = { qn -> def e = fx.queries[qn]; [items: e.rows.collect { new LinkedHashMap(it) }, totalCount: e.totalCount, page: e.page, pageSize: e.pageSize, totalPages: e.totalPages] }
def reportGood = {
  def from = inst(fx.report.from), to = inst(fx.report.to); def byDay = new TreeMap()
  fx.report.payments.findAll { it.status == 'Successful' && it.confirmedAtUtc != null }.each { p -> def t = inst(p.confirmedAtUtc)
    if (!t.isBefore(from) && t.isBefore(to) && !t.isAfter(now)) { def d = t.plusSeconds(330 * 60).toString().substring(0, 10); def c = byDay[d] ?: [amount: 0G, count: 0]; byDay[d] = [amount: c.amount + new BigDecimal(p.amount), count: c.count + 1] } }
  [days: byDay.collect { d, v -> [date: d, amount: v.amount, count: v.count] }, undatedSuccessfulCount: fx.report.payments.count { it.status == 'Successful' && it.confirmedAtUtc == null }, currency: 'LKR', timeZone: 'Asia/Colombo', generatedAtUtc: nowIso] }

println '-- J01a / J06a appointment summary (J01-assert1, J06-assert1) --'
['J01-assert1.groovy', 'J06-assert1.groovy'].each { s ->
  run(s, dashGood(), s + ': correct summary', false)
  run(s, mutate(dashGood) { it.totalAppointments = 15 }, s + ': wrong total', true)
  run(s, mutate(dashGood) { it.statusCounts.Booked = 4 }, s + ': status counts differ', true)
  run(s, mutate(dashGood) { it.todayCount = it.todayCount + 1 }, s + ': wrong today count', true)
  run(s, mutate(dashGood) { it.upcomingCount = it.upcomingCount + 1 }, s + ': wrong upcoming count', true)
  run(s, mutate(dashGood) { it.recentAppointments = it.recentAppointments.reverse() }, s + ': recent appointments oldest first', true)
  run(s, mutate(dashGood) { it.recentAppointments = it.recentAppointments + [it.recentAppointments[0]] }, s + ': six recent appointments', true)
  run(s, mutate(dashGood) { it.recentAppointments[4].paymentStatus = 'Successful' }, s + ': wrong payment status on a row', true)
  run(s, mutate(dashGood) { it.recentAppointments[0].remove('doctorName') }, s + ': a row field is missing', true)
  run(s, mutate(dashGood) { it.extra = 1 }, s + ': an extra field', true)
  run(s, mutate(dashGood) { it.generatedAtUtc = '2020-01-01T00:00:00Z' }, s + ': stale generatedAtUtc', true) }
println '-- J01b / J06b payment summary (J01-assert3, J06-assert3) --'
['J01-assert3.groovy', 'J06-assert3.groovy'].each { s ->
  run(s, payGood(), s + ': correct payment summary', false)
  run(s, mutate(payGood) { it.totalPayments = 12 }, s + ': wrong total', true)
  run(s, mutate(payGood) { it.statusCounts.Successful = 6 }, s + ': status counts differ', true)
  run(s, mutate(payGood) { it.pendingTransfers.totalCount = 2 }, s + ': the rejected receipt counted as pending', true)
  run(s, mutate(payGood) { it.pendingTransfers.items[0] = payRow(53008) }, s + ': the payment with a rejected receipt listed', true)
  run(s, mutate(payGood) { it.recentPayments = it.recentPayments.reverse() }, s + ': recent payments oldest first', true)
  run(s, mutate(payGood) { it.recentPayments[0] = payRow(53006) }, s + ': a future-dated payment appears', true)
  run(s, mutate(payGood) { it.recentPayments[0] = payRow(53005) }, s + ': an undated payment appears', true)
  run(s, mutate(payGood) { it.income.todayAmount = it.income.todayAmount + 1 }, s + ': wrong income today', true)
  run(s, mutate(payGood) { it.income.monthAmount = it.income.monthAmount + new BigDecimal('0.01') }, s + ': income this month off by 0.01', true)
  run(s, mutate(payGood) { it.income.undatedSuccessfulCount = 0 }, s + ': undated payments not reported', true)
  run(s, mutate(payGood) { it.recentPayments[1].amount = 1 }, s + ': a payment amount differs', true)
  run(s, mutate(payGood) { it.recentPayments[1].confirmedAtUtc = null }, s + ': a confirmation date missing', true)
  run(s, mutate(payGood) { it.income.currency = 'USD' }, s + ': wrong currency', true) }
println '-- J02 / J06c appointment list --'
[['J02-assert1.groovy', 'default'], ['J02-assert3.groovy', 'page2'], ['J02-assert5.groovy', 'search'], ['J02-assert7.groovy', 'reference'], ['J06-assert5.groovy', 'repeat']].each { s, qn ->
  def make = { listGood(qn) }
  run(s, make(), s + ' (' + qn + '): correct list', false)
  run(s, mutate(make) { it.totalCount = it.totalCount + 1 }, s + ': wrong totalCount', true)
  run(s, mutate(make) { it.totalPages = it.totalPages + 1 }, s + ': wrong totalPages', true)
  run(s, mutate(make) { it.page = it.page + 1 }, s + ': wrong page', true)
  run(s, mutate(make) { it.items = it.items.reverse() }, s + ': wrong order', true)
  run(s, mutate(make) { it.items = it.items.drop(1) }, s + ': an item is missing', true)
  run(s, mutate(make) { it.items[0].paymentStatus = 'Failed' }, s + ': wrong payment status', true)
  run(s, mutate(make) { it.items[0].doctorName = 'Someone' }, s + ': wrong doctor name', true)
  run(s, mutate(make) { it.items[0].remove('patientId') }, s + ': an item field is missing', true)
  run(s, mutate(make) { it.items[0].startUtc = '2031-01-01 00:00:00' }, s + ': start without the UTC Z suffix', true)
  run(s, mutate(make) { it.pageSize = 7 }, s + ': wrong pageSize', true) }
println '-- J03a income report (J03-assert1) --'
run('J03-assert1.groovy', reportGood(), 'correct report', false)
run('J03-assert1.groovy', mutate(reportGood) { it.days[0].amount = it.days[0].amount + 1 }, 'a daily amount differs', true)
run('J03-assert1.groovy', mutate(reportGood) { it.days[0].count = it.days[0].count + 1 }, 'a daily count differs', true)
run('J03-assert1.groovy', mutate(reportGood) { it.days = it.days.reverse() }, 'days in descending order', true)
run('J03-assert1.groovy', mutate(reportGood) { it.days = it.days.drop(1) }, 'a day is missing', true)
run('J03-assert1.groovy', mutate(reportGood) { def d = it.days.find { it.count == 2 }; it.days.remove(d); it.days.add(0, [date: '2000-01-01', amount: d.amount, count: d.count]) }, 'the two confirmations either side of Sri Lanka midnight merged or mis-dated', true)
run('J03-assert1.groovy', mutate(reportGood) { it.undatedSuccessfulCount = 0 }, 'undated payments not counted', true)
run('J03-assert1.groovy', mutate(reportGood) { it.currency = 'USD' }, 'wrong currency', true)
run('J03-assert1.groovy', mutate(reportGood) { it.timeZone = 'UTC' }, 'wrong time zone', true)
run('J03-assert1.groovy', mutate(reportGood) { it.days[0].extra = 1 }, 'an extra day field', true)
run('J03-assert1.groovy', mutate(reportGood) { it.generatedAtUtc = '2020-01-01T00:00:00Z' }, 'stale generatedAtUtc', true)
println '-- 400 responses (J02-assert9, J03-assert3) --'
run('J02-assert9.groovy', [message: 'Check the search and page values.'], 'J02d: the documented message', false)
run('J02-assert9.groovy', [message: 'Something else'], 'J02d: a different message', true)
run('J02-assert9.groovy', [message: 'Check the search and page values.', detail: 'x'], 'J02d: an extra field', true)
run('J02-assert9.groovy', 'System.Exception: boom\n   at Foo.Bar()', 'J02d: a stack trace', true)
run('J03-assert3.groovy', [message: 'Choose a reporting period of at most 32 days.'], 'J03b: the documented message', false)
run('J03-assert3.groovy', [message: 'Check the search and page values.'], 'J03b: the message of another endpoint', true)
println '-- 401 / 403 denied requests (empty body) --'
['J04-assert1.groovy', 'J04-assert3.groovy', 'J04-assert5.groovy', 'J04-assert7.groovy'] + (0..7).collect { "J05-assert${2 * it + 1}.groovy".toString() }
.each { s -> run(s, '', s + ': empty body', false); run(s, listGood('default'), s + ': appointment data disclosed', true); run(s, '{"message":"denied"}', s + ': any body at all', true)
  run(s, 'CN-APT-ADM-53001', s + ': an appointment reference in the body', true) }
println '-- pre-processors: token role and identity, guarded target, report window (a throw-away dummy secret, never a real one) --'
def pre = { String script, Map extra = [:] ->
  def props = new Properties(); props.put('fixturesFile', fxFile); extra.each { k, v -> props.put(k, v) }
  def vars = new Expando(map: new HashMap()); vars.get = { k -> delegate.map.get(k) }; vars.put = { k, v -> delegate.map.put(k, v) }
  new GroovyShell(new Binding([props: props, vars: vars])).evaluate(new File(dir + '/' + script).text); vars.map }
def claims = { String tok -> new JsonSlurper().parseText(new String(java.util.Base64.getUrlDecoder().decode(tok.split('\\.')[1]), 'UTF-8')) }
def roleUri = 'http://schemas.microsoft.com/ws/2008/06/identity/claims/role'; def idUri = 'http://schemas.microsoft.com/ws/2008/06/identity/claims/nameidentifier'
def expectPre = { String name, boolean cond -> if (!cond) wrong++; println((cond ? 'OK    ' : 'WRONG ') + name) }
if (System.getenv('GCN53_JWT_SECRET')) {
  def roles = [['J01-pre0', 'Admin'], ['J01-pre1', 'Admin'], ['J02-pre0', 'Admin'], ['J02-pre4', 'Admin'], ['J03-pre0', 'Admin'], ['J03-pre1', 'Admin'], ['J05-pre0', 'Patient'], ['J05-pre3', 'Patient'], ['J05-pre4', 'PharmacyStaff'],
               ['J05-pre5', 'PharmacyStaff'], ['J05-pre6', 'Doctor'], ['J05-pre7', 'Doctor'], ['J06-pre0', 'Admin'], ['J06-pre2', 'Admin']]
  def subOf = ['Admin': fx.actors.admin, 'Patient': fx.actors.patient, 'PharmacyStaff': fx.actors.staff, 'Doctor': fx.actors.doctor]
  roles.each { s, role -> def v = pre(s + '.groovy'); def c = claims(v.TOKEN)
    expectPre(s + ': token for role ' + role + ' and the right identity, target localhost:5253, environment valid',
      v.ENV_OK == 'true' && c[roleUri] == role && c[idUri] == subOf[role] && c.sub == subOf[role] && c.iss == 'CareNova.UserAuth' && c.aud == 'CareNova.Client' && v.HOST == 'localhost' && v.PORT == '5253' && c.exp - (System.currentTimeMillis() / 1000) < 1000) }
  (0..3).each { k -> def v = pre("J04-pre${k}.groovy".toString()); expectPre("J04-pre${k}: no token is created for the unauthenticated scenario".toString(), v.TOKEN == null && v.ENV_OK == 'true') }
  def v = pre('J03-pre0.groovy'); expectPre('the report window comes from the fixtures (21 days) and the invalid window (40 days) too', v.REPORT_FROM == fx.report.from && v.REPORT_TO == fx.report.to && v.BAD_FROM == fx.report.badFrom && v.BAD_TO == fx.report.badTo)
  def r = pre('J01-pre0.groovy', ['gcn53.host': 'prod.example.com'])
  expectPre('a configured host other than localhost is REFUSED (the sampler gets an unreachable address, the scenario fails)', r.ENV_OK == 'false' && r.HOST == 'target-refused.invalid' && r.PORT == '1' && r.ENV_WHY.contains('refused target'))
  r = pre('J01-pre0.groovy', ['gcn53.port': '5251'])
  expectPre('a configured port other than 5253 (for example the GCN-51 backend 5251) is REFUSED', r.ENV_OK == 'false' && r.HOST == 'target-refused.invalid' && r.PORT == '1')
  r = pre('J01-pre0.groovy', ['gcn53.host': '127.0.0.1']); expectPre('127.0.0.1:5253 is accepted', r.ENV_OK == 'true' && r.HOST == '127.0.0.1' && r.PORT == '5253')
  expectPre('the token does not contain the secret', !pre('J01-pre0.groovy').TOKEN.contains(System.getenv('GCN53_JWT_SECRET')))
} else { println 'SKIPPED pre-processor checks: run through gcn53-check-assertions.sh' }
println wrong == 0 ? 'ALL ASSERTION CHECKS BEHAVE AS EXPECTED' : (wrong + ' CHECK(S) BEHAVED UNEXPECTEDLY')
System.exit(wrong == 0 ? 0 : 1)
