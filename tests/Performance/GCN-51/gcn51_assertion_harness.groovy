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
def nowIso = java.time.Instant.now().truncatedTo(java.time.temporal.ChronoUnit.SECONDS).toString()
def deepCopy; deepCopy = { x -> x instanceof Map ? x.collectEntries { k, v -> [(k): deepCopy(v)] } : (x instanceof List ? x.collect { deepCopy(it) } : x) }
// ---- good bodies, built independently of the plan's scripts
def patientGood = { [upcomingCount: fx.patient.upcomingCount, appointments: fx.patient.appointments.collect { [id: it.id, reference: it.reference, doctorName: it.doctorName, startUtc: it.startUtc, status: it.status, paymentMethod: it.paymentMethod, paymentStatus: it.paymentStatus] },
  paymentStatusCounts: new LinkedHashMap(fx.patient.paymentStatusCounts), generatedAtUtc: nowIso] }
def payRow = { id -> def p = fx.staff.payments.find { it.id == id }; [id: p.id, appointmentId: p.appointmentId, reference: p.reference, amount: new BigDecimal(p.amount), method: p.method, status: p.status, confirmedAtUtc: p.confirmedAtUtc, updatedAtUtc: p.updatedAtUtc] }
def staffGood = {
  def asOf = java.time.Instant.parse(nowIso); def zone = java.time.ZoneId.of('Asia/Colombo'); def d0 = asOf.atZone(zone).toLocalDate()
  def ds = d0.atStartOfDay(zone).toInstant(); def ms = d0.withDayOfMonth(1).atStartOfDay(zone).toInstant()
  BigDecimal today = 0, month = 0, undAmt = 0; int und = 0
  fx.staff.payments.each { p -> if (p.status == 'Successful') {
    if (p.confirmedAtUtc == null) { und++; undAmt += new BigDecimal(p.amount) }
    else { def t = java.time.Instant.parse(p.confirmedAtUtc); if (!t.isAfter(asOf)) { if (!t.isBefore(ds)) today += new BigDecimal(p.amount); if (!t.isBefore(ms)) month += new BigDecimal(p.amount) } } } }
  [pendingTransfers: [totalCount: fx.staff.pendingTotal, items: fx.staff.pendingIds.collect { payRow(it) }], recentPayments: fx.staff.recentIds.collect { payRow(it) },
   income: [todayAmount: today, monthAmount: month, undatedSuccessfulCount: und, undatedSuccessfulAmount: undAmt, currency: 'LKR', timeZone: 'Asia/Colombo', asOfUtc: nowIso], generatedAtUtc: nowIso] }
def doctorGood = { [appointments: fx.doctor.appointments.collect { a -> [id: a.id, appointmentReference: a.appointmentReference, patientId: a.patientId, patientName: null, patientPhone: null, appointmentStartUtc: a.startUtc, appointmentEndUtc: a.endUtc,
  status: a.status, updatedAtUtc: null, paymentMethod: a.paymentMethod, paymentStatus: a.paymentStatus, isToday: a.doctorExpect.isToday, isUpcoming: a.doctorExpect.isUpcoming, isCompleted: a.doctorExpect.isCompleted,
  isHistory: a.doctorExpect.isHistory, allowedStatuses: a.doctorExpect.allowedStatuses, contactsUnavailable: true] }, statistics: fx.doctor.statistics, contactsUnavailable: true] }
def mutate = { Closure make, Closure change -> def b = deepCopy(make()); change(b); b }

println '-- J01 patient contract (J01-assert1) --'
run('J01-assert1.groovy', patientGood(), 'correct patient dashboard', false)
run('J01-assert1.groovy', mutate(patientGood) { it.remove('paymentStatusCounts') }, 'a field is missing', true)
run('J01-assert1.groovy', mutate(patientGood) { it.extra = 1 }, 'an extra field', true)
run('J01-assert1.groovy', mutate(patientGood) { it.appointments = it.appointments + it.appointments[0..0].collect { x -> x + [id: 99] } + it.appointments[0..0].collect { x -> x + [id: 98] } }, 'more than five appointments', true)
run('J01-assert1.groovy', mutate(patientGood) { it.upcomingCount = 2 }, 'upcomingCount smaller than the listed appointments', true)
run('J01-assert1.groovy', mutate(patientGood) { it.upcomingCount = -1 }, 'negative upcomingCount', true)
run('J01-assert1.groovy', mutate(patientGood) { it.appointments[0].startUtc = '2031-03-12 04:00:00' }, 'start time without the UTC Z suffix', true)
run('J01-assert1.groovy', mutate(patientGood) { it.appointments[0].remove('doctorName') }, 'an appointment field is missing', true)
run('J01-assert1.groovy', mutate(patientGood) { it.generatedAtUtc = '2020-01-01T00:00:00Z' }, 'a stale generatedAtUtc', true)
run('J01-assert1.groovy', mutate(patientGood) { it.paymentStatusCounts = [Pending: -1] }, 'a negative payment-status count', true)
run('J01-assert1.groovy', 'not json', 'a non-JSON body', true)
println '-- J02 patient values (J02-assert1) --'
['J02-assert1.groovy'].each { s ->
  run(s, patientGood(), s + ': correct counts, preview and payment-status counts', false)
  run(s, mutate(patientGood) { it.upcomingCount = 6 }, s + ': wrong upcoming count', true)
  run(s, mutate(patientGood) { it.appointments = it.appointments.reverse() }, s + ': preview in the wrong order', true)
  run(s, mutate(patientGood) { it.appointments = it.appointments.take(4) }, s + ': a preview row is missing', true)
  run(s, mutate(patientGood) { it.appointments[1].paymentStatus = 'Pending' }, s + ': wrong payment status on a row', true)
  run(s, mutate(patientGood) { it.appointments[4].paymentMethod = 'Cash' }, s + ': a payment shown for an appointment without payment', true)
  run(s, mutate(patientGood) { it.paymentStatusCounts.Successful = 3 }, s + ': wrong payment-status count', true)
  run(s, mutate(patientGood) { it.appointments[0].doctorName = 'Someone' }, s + ': wrong doctor name', true)
  run(s, mutate(patientGood) { it.appointments[0].reference = fx.patient.foreignReferences[0] }, s + ': an appointment of another patient', true) }
println '-- J03 staff contract (J03-assert1) --'
run('J03-assert1.groovy', staffGood(), 'correct staff dashboard', false)
run('J03-assert1.groovy', mutate(staffGood) { it.income.currency = 'USD' }, 'wrong currency', true)
run('J03-assert1.groovy', mutate(staffGood) { it.income.todayAmount = it.income.monthAmount + 1 }, 'month smaller than today', true)
run('J03-assert1.groovy', mutate(staffGood) { it.income.remove('asOfUtc') }, 'income field missing', true)
run('J03-assert1.groovy', mutate(staffGood) { it.extra = 1 }, 'an extra field', true)
run('J03-assert1.groovy', mutate(staffGood) { it.recentPayments = it.recentPayments + [it.recentPayments[0]] }, 'more than five recent payments', true)
run('J03-assert1.groovy', mutate(staffGood) { it.pendingTransfers.totalCount = 1 }, 'totalCount smaller than the listed items', true)
run('J03-assert1.groovy', mutate(staffGood) { it.income.timeZone = 'UTC' }, 'wrong time zone', true)
println '-- J04 / J09 staff values (J04-assert1, J09-assert1) --'
['J04-assert1.groovy', 'J09-assert1.groovy'].each { s ->
  run(s, staffGood(), s + ': correct pending transfers, recent payments and income', false)
  run(s, mutate(staffGood) { it.pendingTransfers.totalCount = 5 }, s + ': wrong pending total (the rejected receipt must not count either way)', true)
  run(s, mutate(staffGood) { it.pendingTransfers.items = it.pendingTransfers.items.reverse() }, s + ': pending in the wrong order', true)
  run(s, mutate(staffGood) { it.pendingTransfers.items[0] = payRow(51109) }, s + ': the payment with a rejected receipt appears as pending', true)
  run(s, mutate(staffGood) { it.recentPayments = it.recentPayments.reverse() }, s + ': recent payments oldest first', true)
  run(s, mutate(staffGood) { it.recentPayments[0] = payRow(51110) }, s + ': a future-dated confirmation appears', true)
  run(s, mutate(staffGood) { it.recentPayments[4] = payRow(51112) }, s + ': a sixth-newest payment appears', true)
  run(s, mutate(staffGood) { it.income.todayAmount = it.income.todayAmount + 1 }, s + ': wrong income today', true)
  run(s, mutate(staffGood) { it.income.monthAmount = it.income.monthAmount + new BigDecimal('0.01') }, s + ': income this month off by 0.01', true)
  run(s, mutate(staffGood) { it.income.undatedSuccessfulCount = 0 }, s + ': undated payments not reported', true)
  run(s, mutate(staffGood) { it.income.undatedSuccessfulAmount = 0 }, s + ': undated amount not reported', true)
  run(s, mutate(staffGood) { it.recentPayments[1].amount = 1 }, s + ': a payment amount differs', true)
  run(s, mutate(staffGood) { it.recentPayments[1].confirmedAtUtc = null }, s + ': a confirmation date missing', true)
  run(s, mutate(staffGood) { it.recentPayments[0].method = 'Cash' }, s + ': a payment method differs', true) }
println '-- J05 doctor appointments (J05-assert1) --'
run('J05-assert1.groovy', doctorGood(), 'correct doctor appointments', false)
run('J05-assert1.groovy', mutate(doctorGood) { it.appointments = it.appointments + [it.appointments[0] + [id: 51201, appointmentReference: 'CN-APT-DSH-51201']] }, "another doctor's appointment included", true)
run('J05-assert1.groovy', mutate(doctorGood) { it.statistics.upcoming = it.statistics.upcoming + 1 }, 'wrong statistics', true)
run('J05-assert1.groovy', mutate(doctorGood) { it.appointments = it.appointments.reverse() }, 'wrong order', true)
run('J05-assert1.groovy', mutate(doctorGood) { it.appointments[0].allowedStatuses = ['Confirmed'] }, 'wrong allowedStatuses', true)
run('J05-assert1.groovy', mutate(doctorGood) { it.appointments[2].patientName = 'Someone Real' }, 'a patient name although contacts are unavailable', true)
run('J05-assert1.groovy', mutate(doctorGood) { it.contactsUnavailable = false }, 'contactsUnavailable false', true)
run('J05-assert1.groovy', mutate(doctorGood) { it.appointments[1].remove('isHistory') }, 'a contract field is missing', true)
run('J05-assert1.groovy', mutate(doctorGood) { it.appointments[1].status = 'Cancelled' }, 'a status differs from the database', true)
run('J05-assert1.groovy', mutate(doctorGood) { it.appointments = it.appointments.take(5) }, 'appointments are missing', true)
println '-- J06 / J07 / J08 denied requests --'
['J06-assert1.groovy', 'J07-assert1.groovy', 'J08-assert1.groovy'].each { s ->
  run(s, '', s + ': empty body', false)
  run(s, patientGood(), s + ': patient data disclosed', true)
  run(s, '{"message":"denied"}', s + ': any body at all', true)
  run(s, 'CN-APT-DSH-51001', s + ': an appointment reference in the body', true) }
println '-- pre-processors: token role and identity, guarded target (uses a throw-away dummy secret, never a real one) --'
def pre = { String script, Map extra = [:] ->
  def props = new Properties(); props.put('fixturesFile', fxFile); extra.each { k, v -> props.put(k, v) }
  def vars = new Expando(map: new HashMap()); vars.get = { k -> delegate.map.get(k) }; vars.put = { k, v -> delegate.map.put(k, v) }
  new GroovyShell(new Binding([props: props, vars: vars])).evaluate(new File(dir + '/' + script).text); vars.map }
def claims = { String tok -> new JsonSlurper().parseText(new String(java.util.Base64.getUrlDecoder().decode(tok.split('\\.')[1]), 'UTF-8')) }
def roleUri = 'http://schemas.microsoft.com/ws/2008/06/identity/claims/role'; def idUri = 'http://schemas.microsoft.com/ws/2008/06/identity/claims/nameidentifier'
def expectPre = { String name, boolean cond -> if (!cond) wrong++; println((cond ? 'OK    ' : 'WRONG ') + name) }
if (System.getenv('GCN51_JWT_SECRET')) {
  [['J01-pre0', 'Patient', fx.actors.patient1], ['J02-pre0', 'Patient', fx.actors.patient1], ['J03-pre0', 'PharmacyStaff', fx.actors.staff], ['J04-pre0', 'PharmacyStaff', fx.actors.staff], ['J05-pre0', 'Doctor', fx.actors.doctor1],
   ['J07-pre0', 'Patient', fx.actors.patient1], ['J08-pre0', 'PharmacyStaff', fx.actors.staff], ['J09-pre0', 'PharmacyStaff', fx.actors.staff]].each { s, role, sub ->
    def v = pre(s + '.groovy'); def c = claims(v.TOKEN)
    expectPre(s + ': token for role ' + role + ' and the right identity, target localhost:5251, environment valid',
      v.ENV_OK == 'true' && c[roleUri] == role && c[idUri] == sub && c.sub == sub && c.iss == 'CareNova.UserAuth' && c.aud == 'CareNova.Client' && v.HOST == 'localhost' && v.PORT == '5251' && c.exp - (System.currentTimeMillis() / 1000) < 1000) }
  ['J06-pre0'].each { s -> def v = pre(s + '.groovy'); expectPre(s + ': no token is created for the unauthenticated scenario', v.TOKEN == null && v.ENV_OK == 'true') }
  def r = pre('J01-pre0.groovy', ['gcn51.host': 'prod.example.com'])
  expectPre('a configured host other than localhost is REFUSED (the sampler gets an unreachable address, the scenario fails)', r.ENV_OK == 'false' && r.HOST == 'target-refused.invalid' && r.PORT == '1' && r.ENV_WHY.contains('refused target'))
  r = pre('J01-pre0.groovy', ['gcn51.port': '5248'])
  expectPre('a configured port other than 5251 (for example the GCN-48 backend 5248) is REFUSED', r.ENV_OK == 'false' && r.HOST == 'target-refused.invalid' && r.PORT == '1')
  r = pre('J01-pre0.groovy', ['gcn51.host': '127.0.0.1'])
  expectPre('127.0.0.1:5251 is accepted', r.ENV_OK == 'true' && r.HOST == '127.0.0.1' && r.PORT == '5251')
  expectPre('the token does not contain the secret', !pre('J01-pre0.groovy').TOKEN.contains(System.getenv('GCN51_JWT_SECRET')))
} else { println 'SKIPPED pre-processor checks: run through gcn51-check-assertions.sh' }
println wrong == 0 ? 'ALL ASSERTION CHECKS BEHAVE AS EXPECTED' : (wrong + ' CHECK(S) BEHAVED UNEXPECTEDLY')
System.exit(wrong == 0 ? 0 : 1)
