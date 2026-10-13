#!/usr/bin/env python3
"""Generates GCN53AdminDashboardSixTest.jmx and scenarios.json: EXACTLY six test cases T01..T06, EXACTLY six HTTP GET samplers (one per test case), one thread, ONE iteration, no loops.
The Groovy assertion scripts, the local-JWT pre-processor, the guarded host/port (only localhost:5253) and the response-time assertions are NOT re-implemented: the helper part of the
66-request generator (../gen_gcn53_jmx.py, which stays unchanged) is executed to define them, so the six cases use exactly the already-validated scripts.
Nothing here is secret: tokens are minted at run time from GCN53_JWT_SECRET in the JMeter process environment."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.join(os.path.dirname(HERE), "gen_gcn53_jmx.py")
src = open(PARENT).read(); ns = {"__file__": os.path.join(HERE, "gen_gcn53_six_jmx.py"), "__name__": "gcn53_helpers"}
exec(compile(src[:src.index("JM = [")], PARENT, "exec"), ns)          # definitions only: nothing is written by this part
exec(compile(src[src.index("SAVE = ("):src.index("doc = (")], PARENT, "exec"), ns)    # the two result listeners (definitions only)
S, tg, ADMIN, PAT, DA, DP, AL, RPQ = (ns[k] for k in ("S", "tg", "ADMIN", "PAT", "DA", "DP", "AL", "RPQ"))
DASH_APPTS, DASH_PAY, REPORT, EMPTY_BODY, list_check = (ns[k] for k in ("DASH_APPTS", "DASH_PAY", "REPORT", "EMPTY_BODY", "list_check"))
listener, ht = ns["listener"], ns["ht"]
JM = [
 tg("T01", "Admin appointment summary", "ONE request: GET the admin appointment summary as Admin: 200, JSON, exact contract; total and status counts equal the fixtures and add up; today / upcoming recomputed independently for Asia/Colombo; the five newest appointments, newest first, with payment method and status.",
    [S("T01 Admin appointment summary", DA, ADMIN, 200, [("Totals, status counts, today/upcoming and the five newest appointments equal the oracle", DASH_APPTS)])]),
 tg("T02", "Admin payment summary and income", "ONE request: GET the admin appointment-payment summary as Admin: 200, JSON, exact contract; payment counts; the pending transfer included and the one with a rejected receipt excluded; recent payments newest confirmation first (future-dated and undated excluded); income today / this month and undated payments equal the oracle.",
    [S("T02 Admin payment summary and income", DP, ADMIN, 200, [("Payment counts, pending transfers, recent payments and income equal the oracle", DASH_PAY)])]),
 tg("T03", "Admin appointment listing and pagination", "ONE request: GET the admin appointment list page 2 with page size 5 as Admin: 200, JSON, items 6-10 newest first with payment details, totalCount 14, page 2, pageSize 5, totalPages 3.",
    [S("T03 Admin appointment listing page 2", AL + "?page=2&pageSize=5", ADMIN, 200, [("Page 2 of 3: items 6-10 in order, totalCount 14, totalPages 3", list_check("page2"))])]),
 tg("T04", "Admin income report and date grouping", "ONE request: GET the admin appointment-income report for a 21-day window as Admin: 200, JSON, days grouped by Asia/Colombo date in ascending order (the two confirmations seconds either side of Sri Lanka midnight on different dates), daily amounts and counts equal the oracle, future-dated and undated payments excluded from the days, undated ones counted separately, currency LKR.",
    [S("T04 Admin income report", RPQ, ADMIN, 200, [("Date grouping, daily totals and counts, undated count and currency equal the oracle", REPORT)])]),
 tg("T05", "Unauthenticated access to financial data", "ONE request: GET the admin appointment-payment summary WITHOUT any token: 401, empty body, no payment or appointment data.",
    [S("T05 Unauthenticated payment summary", DP, None, 401, [("Empty body, no appointment data", EMPTY_BODY)])]),
 tg("T06", "Non-admin access to appointment data", "ONE request: GET the admin appointment list with a valid PATIENT token: 403, empty body, no appointment data.",
    [S("T06 Patient on the admin appointment list", AL, PAT, 403, [("Empty body", EMPTY_BODY)])]),
]
doc = ('<?xml version="1.0" encoding="UTF-8"?>\n<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3"><hashTree><TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="GCN-53 Admin Dashboard API (6 test cases, 6 requests, read-only)" enabled="true">'
       '<stringProp name="TestPlan.comments">GCN-53 QA, six-request suite. LOCAL only: backend localhost:5253 (properties gcn53.host / gcn53.port, guarded: anything else is refused), isolated database carenova_appointment_gcn53_qa, synthetic data. EXACTLY 6 test cases T01..T06, 6 read-only GET samplers (one per test case), 6 requests in total: one thread, one iteration, no loops. No setup, authentication, health-check or teardown request; no writes. No secrets in this file. Run it through run-gcn53-six.sh, never from the GUI.</stringProp>'
       '<boolProp name="TestPlan.functional_mode">false</boolProp><boolProp name="TestPlan.tearDown_on_shutdown">true</boolProp><boolProp name="TestPlan.serialize_threadgroups">true</boolProp>'
       '<elementProp name="TestPlan.user_defined_variables" elementType="Arguments" guiclass="ArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true"><collectionProp name="Arguments.arguments"/></elementProp>'
       '<stringProp name="TestPlan.user_define_classpath"></stringProp></TestPlan>' + ht(listener("SummaryReport", "Summary Report") + listener("ViewResultsFullVisualizer", "View Results Tree") + "".join(JM)) + '</hashTree></jmeterTestPlan>\n')
open(os.path.join(HERE, "GCN53AdminDashboardSixTest.jmx"), "w").write(doc)
SC = {
 "T01": {"name": "Admin appointment summary", "method": "GET", "path": DA, "role": "Admin", "expected_status": 200},
 "T02": {"name": "Admin payment summary and income", "method": "GET", "path": DP, "role": "Admin", "expected_status": 200},
 "T03": {"name": "Admin appointment listing and pagination", "method": "GET", "path": AL + "?page=2&pageSize=5", "role": "Admin", "expected_status": 200},
 "T04": {"name": "Admin income report and date grouping", "method": "GET", "path": "/api/admin/reports/appointment-income?from&to (21 days)", "role": "Admin", "expected_status": 200},
 "T05": {"name": "Unauthenticated access to financial data", "method": "GET", "path": DP, "role": "none", "expected_status": 401},
 "T06": {"name": "Non-admin access to appointment data", "method": "GET", "path": AL, "role": "Patient", "expected_status": 403},
}
for v in SC.values(): v.update({"requests": 1, "threshold_ms": 3000})
json.dump({"total_requests": 6, "samplers": 6, "test_cases": 6, "threads_per_case": 1, "iterations_per_case": 1, "read_only": True,
           "note": "Six read-only requests, one per test case, one thread, one iteration. A functional smoke test of the six most important admin dashboard behaviors: not a load, concurrency, stability or response-time-statistics test. The 3000 ms limit is a sanity cap, not a service level.",
           "scenarios": SC}, open(os.path.join(HERE, "scenarios.json"), "w"), indent=2)
print("wrote JMX and scenarios.json: 6 test cases, 6 HTTP GET samplers, 6 requests")
