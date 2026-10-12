// Runs the plan's OWN assertion scripts against correct and deliberately corrupted responses, offline (no JMeter, no HTTP, no server).
// args: fixtures.json  scripts-dir  evidence-dir     Exit code 1 if any script behaves differently from what is expected.
import groovy.json.*
def fxFile = args[0]; def dir = args[1]; def ev = args[2]
def fx = new JsonSlurper().parseText(new File(fxFile).text)
def A = { int id -> fx.appointments.find { it.id == id } }
def wrong = 0
def run = { String script, String body, String name, boolean expectFail, Map extra = [:] ->
  def props = new Properties(); props.put('fixturesFile', fxFile); props.put('evidenceDir', ev)
  def vars = new Expando(map: new HashMap(extra)); vars.get = { k -> delegate.map.get(k) }; vars.put = { k, v -> delegate.map.put(k, v) }
  def prev = new Expando(); prev.getResponseDataAsString = { body }; prev.getResponseCode = { '200' }
  def result = new Expando(failed: false, msg: ''); result.setFailure = { b -> delegate.failed = b }; result.setFailureMessage = { m -> delegate.msg = m }
  try { new GroovyShell(new Binding([props: props, vars: vars, prev: prev, AssertionResult: result])).evaluate(new File(dir + '/' + script).text) } catch (Throwable t) { result.failed = true; result.msg = 'exception: ' + t.class.simpleName }
  def ok = result.failed == expectFail; if (!ok) wrong++
  println((ok ? 'OK    ' : 'WRONG ') + name + (result.failed ? '  -> detected: ' + result.msg.take(110) : '  -> accepted'))
}
def elig = { int id, Map over = [:] -> def e = A(id).expected
  [appointmentId: id, allowed: e.allowed, reasonCode: e.reasonCode, message: e.message, refundOutcome: e.refundOutcome, refundAmount: e.refundAmount, requiresNoRefundAcknowledgement: e.requiresNoRefundAcknowledgement, version: e.version, cancellation: null] + over }
def J = { x -> JsonOutput.toJson(x) }
println '-- JM-01 own unpaid appointment (48001): eligibility --'
def t1 = [TARGET_ID: '48001']
run('JM-01-assert1.groovy', J(elig(48001)), 'correct eligibility', false, t1)
run('JM-01-assert1.groovy', J(elig(48001, [allowed: false])), 'allowed is false', true, t1)
run('JM-01-assert1.groovy', J(elig(48001, [reasonCode: 'CashAlreadyPaid'])), 'wrong reason code', true, t1)
run('JM-01-assert1.groovy', J(elig(48001, [version: 'A' * 63])), 'version with 63 characters', true, t1)
run('JM-01-assert1.groovy', J(elig(48001, [version: 'g' * 64])), 'version that is not hexadecimal', true, t1)
run('JM-01-assert1.groovy', J(elig(48001, [version: A(48001).expected.version.toLowerCase()])), 'version in lower case', true, t1)
run('JM-01-assert1.groovy', J(elig(48001, [version: 'A' * 64])), 'a valid-looking version that differs from the offline value', true, t1)
run('JM-01-assert1.groovy', J(elig(48001, [cancellation: [appointmentId: 48001]])), 'a cancellation is already stored', true, t1)
run('JM-01-assert1.groovy', J(elig(48001, [refundAmount: 1500])), 'a refund amount for an unpaid appointment', true, t1)
run('JM-01-assert1.groovy', J(elig(48001, [message: 'Fine.'])), 'different message', true, t1)
run('JM-01-assert1.groovy', J(elig(48001, [extra: 1])), 'an extra field', true, t1)
def m = elig(48001); m.remove('version'); run('JM-01-assert1.groovy', J(m), 'the version is missing', true, t1)
println '-- JM-02 restricted cash-paid (48002) --'
def t2 = [TARGET_ID: '48002']
run('JM-02-assert1.groovy', J(elig(48002)), 'correct restriction', false, t2)
run('JM-02-assert1.groovy', J(elig(48002, [allowed: true])), 'allowed is true although cash was paid', true, t2)
run('JM-02-assert1.groovy', J(elig(48002, [reasonCode: 'Unpaid'])), 'reason Unpaid instead of CashAlreadyPaid', true, t2)
println "-- JM-03 another patient's appointment (48101): 404 --"
def t3 = [TARGET_ID: '48101']; def msg = '{"message":"Appointment not found."}'
run('JM-03-assert1.groovy', msg, 'the generic not-found message', false, t3)
run('JM-03-assert1.groovy', '', 'an empty body (the controller returns a message)', true, t3)
run('JM-03-assert1.groovy', '{"message":"Appointment not found.","appointmentReference":"' + A(48101).appointmentReference + '"}', 'the other patient\'s reference disclosed', true, t3)
run('JM-03-assert1.groovy', '{"message":"Appointment not found.","detail":"x"}', 'an extra field', true, t3)
run('JM-03-assert1.groovy', '{"message":"This belongs to another patient."}', 'a message that reveals the appointment exists', true, t3)
run('JM-03-assert1.groovy', J(elig(48101)), 'the eligibility of the other patient\'s appointment', true, t3)
run('JM-03-assert1.groovy', '{"type":"x","title":"Not Found","status":404}', 'problem details instead of the message', true, t3)
run('JM-03-assert1.groovy', '<html>oops</html>', 'a non-JSON body', true, t3)
println '-- JM-04 doctor token (48001): 403 --'
run('JM-04-assert1.groovy', '', 'empty 403 body', false, t1)
run('JM-04-assert1.groovy', J(elig(48001)), 'eligibility disclosed to a Doctor', true, t1)
run('JM-04-assert1.groovy', '{"message":"nope"}', 'any body at all', true, t1)
println '-- JM-05 cancellation (48005): 200 --'
def t5 = [TARGET_ID: '48005', CANCEL_REASON: fx.targets['JM-05'].reason]
def a5 = A(48005); def now = java.time.Instant.now().toString().replaceAll('\\.\\d+Z$', 'Z')
def ok5 = [appointmentId: 48005, appointmentReference: a5.appointmentReference, status: 'Cancelled', cancelledAtUtc: now.replaceAll('Z$', '.1234560Z'), refundOutcome: 'Eligible', refundAmount: 1500.00,
           refundStatus: 'PendingManualProcessing', reason: t5.CANCEL_REASON, message: a5.expected.message]
run('JM-05-assert1.groovy', J(ok5), 'correct cancellation response', false, t5)
run('JM-05-assert1.groovy', J(ok5 + [status: 'Booked']), 'status not Cancelled', true, t5)
run('JM-05-assert1.groovy', J(ok5 + [refundOutcome: 'NotEligible']), 'refund outcome NotEligible', true, t5)
run('JM-05-assert1.groovy', J(ok5 + [refundStatus: null]), 'refund status missing', true, t5)
run('JM-05-assert1.groovy', J(ok5 + [refundStatus: 'Refunded']), 'refund status Refunded instead of PendingManualProcessing', true, t5)
run('JM-05-assert1.groovy', J(ok5 + [refundAmount: 1000]), 'wrong refund amount', true, t5)
run('JM-05-assert1.groovy', J(ok5 + [appointmentId: 48003]), 'another appointment cancelled', true, t5)
run('JM-05-assert1.groovy', J(ok5 + [reason: 'other']), 'a different reason stored', true, t5)
run('JM-05-assert1.groovy', J(ok5 + [message: 'x']), 'a different message', true, t5)
run('JM-05-assert1.groovy', J(ok5 + [extra: 1]), 'an extra field', true, t5)
run('JM-05-assert1.groovy', J(ok5 + [cancelledAtUtc: '2026-10-12 10:00:00']), 'timestamp that is not UTC ISO', true, t5)
run('JM-05-assert1.groovy', J(ok5 + [cancelledAtUtc: '2020-01-01T00:00:00.1234560Z']), 'timestamp years away from the clock', true, t5)
m = new LinkedHashMap(ok5); m.remove('reason'); run('JM-05-assert1.groovy', J(m), 'the reason field is missing', true, t5)
run('JM-05-post0.groovy', J(ok5), 'evidence writer runs', false, t5)
println 'evidence: ' + new File(ev + '/jm05-response.json').text

println '-- pre-processors: local token, target, version (uses a throw-away dummy secret from the environment, never a real one) --'
def pre = { String script, Map extra = [:], String secret ->
  def props = new Properties(); props.put('fixturesFile', fxFile); props.put('evidenceDir', ev)
  def vars = new Expando(map: new HashMap(extra)); vars.get = { k -> delegate.map.get(k) }; vars.put = { k, v -> delegate.map.put(k, v) }
  new GroovyShell(new Binding([props: props, vars: vars])).evaluate(new File(dir + '/' + script).text); vars.map }
def claims = { String tok -> new JsonSlurper().parseText(new String(java.util.Base64.getUrlDecoder().decode(tok.split('\\.')[1]), 'UTF-8')) }
def roleUri = 'http://schemas.microsoft.com/ws/2008/06/identity/claims/role'; def idUri = 'http://schemas.microsoft.com/ws/2008/06/identity/claims/nameidentifier'
def expectPre = { String name, boolean cond -> if (!cond) wrong++; println((cond ? 'OK    ' : 'WRONG ') + name) }
if (System.getenv('GCN48_JWT_SECRET')) {
  [['JM-01', 'Patient', fx.actors.patient1, '48001'], ['JM-02', 'Patient', fx.actors.patient1, '48002'], ['JM-03', 'Patient', fx.actors.patient1, '48101'],
   ['JM-04', 'Doctor', fx.actors.doctor, '48001'], ['JM-05', 'Patient', fx.actors.patient1, '48005']].each { sid, role, sub, target ->
    def v = pre(sid + '-pre0.groovy', [:], 'x'); def c = claims(v.TOKEN)
    expectPre(sid + ': token for role ' + role + ' and the right identity, target ' + target + ', environment valid',
      v.ENV_OK == 'true' && c[roleUri] == role && c[idUri] == sub && c.sub == sub && c.iss == 'CareNova.UserAuth' && c.aud == 'CareNova.Client' && v.TARGET_ID == target && c.exp - (System.currentTimeMillis() / 1000) < 1000) }
  def v5 = pre('JM-05-pre0.groovy', [:], 'x')
  expectPre('JM-05: the expected version and the reason come from the fixtures (version not printed)', v5.EXPECTED_VERSION == fx.targets['JM-05'].expectedVersion && v5.EXPECTED_VERSION ==~ /^[0-9A-F]{64}$/ && v5.CANCEL_REASON == fx.targets['JM-05'].reason)
  expectPre('JM-05: the version is the one of the target appointment (not of another seeded row)', fx.appointments.findAll { it.expected.version == v5.EXPECTED_VERSION }.collect { it.id } == [48005])
  expectPre('the token is signed (HS256, three parts) and does not contain the secret', pre('JM-01-pre0.groovy', [:], 'x').TOKEN.split('\\.').size() == 3 && !pre('JM-01-pre0.groovy', [:], 'x').TOKEN.contains(System.getenv('GCN48_JWT_SECRET')))
} else { println 'SKIPPED pre-processor checks: run through gcn48-check-assertions.sh' }

println wrong == 0 ? 'ALL ASSERTION CHECKS BEHAVE AS EXPECTED' : (wrong + ' CHECK(S) BEHAVED UNEXPECTEDLY')
System.exit(wrong == 0 ? 0 : 1)
