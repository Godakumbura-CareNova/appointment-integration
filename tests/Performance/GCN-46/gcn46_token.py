#!/usr/bin/env python3
"""Mints ONE synthetic HS256 JWT for the validation script (same claims as the JMeter plan). The secret comes from GCN46_JWT_SECRET in the environment;
the token is printed to stdout for the calling script only (never logged). usage: gcn46_token.py ROLE SUB [EXP_OFFSET_SECONDS]"""
import base64, hashlib, hmac, json, os, sys, time
role, sub = sys.argv[1], sys.argv[2]; off = int(sys.argv[3]) if len(sys.argv) > 3 else 3600
secret = os.environ["GCN46_JWT_SECRET"].encode()
b = lambda x: base64.urlsafe_b64encode(x).rstrip(b"=")
head = b(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
nid, rid = "http://schemas.microsoft.com/ws/2008/06/identity/claims/nameidentifier", "http://schemas.microsoft.com/ws/2008/06/identity/claims/role"
pay = b(json.dumps({"sub": sub, nid: sub, rid: role, "iss": "CareNova.UserAuth", "aud": "CareNova.Client", "exp": int(time.time()) + off}, separators=(",", ":")).encode())
print((head + b"." + pay + b"." + b(hmac.new(secret, head + b"." + pay, hashlib.sha256).digest())).decode())
