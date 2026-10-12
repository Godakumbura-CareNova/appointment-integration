#!/usr/bin/env python3
"""Extracts every Groovy script of the plan (pre-processors, assertions, post-processor) to files, named <scenario>-<kind><n>.groovy. Used by gcn51-check-assertions.sh. Offline."""
import os, sys, xml.etree.ElementTree as ET
jmx, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True)
sid = None; n = 0
for e in ET.parse(jmx).getroot().iter():
    if e.tag == "ThreadGroup": sid = e.get("testname").split()[0]
    if e.tag in ("JSR223PreProcessor", "JSR223Assertion", "JSR223PostProcessor"):
        kind = {"JSR223PreProcessor": "pre", "JSR223Assertion": "assert", "JSR223PostProcessor": "post"}[e.tag]; text = e.findtext("stringProp[@name='script']")
        assert "${" not in text, "script contains dollar-brace"
        k = sum(1 for f in os.listdir(out) if f.startswith(f"{sid}-{kind}")); open(os.path.join(out, f"{sid}-{kind}{k}.groovy"), "w").write(text); n += 1
print(n, "scripts extracted")
