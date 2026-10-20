#!/usr/bin/env python3
"""Check an Insomnia V4 export for the format mistakes that silently break requests.

  insomnia_check.py <export.json>     exit 1 when errors are found

Rules (each one has bitten a hand-written collection before):
  - envelope: _type "export", __export_format 4, resources list
  - unique _id with the prefix Insomnia expects (wrk_, fld_, req_, env_), parentId points at a resource
  - request.body is {} or {"mimeType": "application/json", "text": <string>}. A raw object such as
    {"TravelID": "1"} is dropped to text '' by mcp-insomnia's sync_to_insomnia, so it is an error
  - body.text is valid JSON once template tags are filled in; tags must sit inside JSON strings
  - GET requests carry no body; a request with a body sends Content-Type: application/json
  - headers / parameters are lists of {"id", "name": str, "value": str} with ids unique per list;
    the Insomnia UI fails with "Render Failure: Invalid array length" on missing or duplicate ids
  - template variables are written {{ _.name }} and name exists in the environment
  - every response tag points at an existing request
"""
import json
import re
import sys

TAG = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.S)
VAR = re.compile(r"\{\{\s*(.*?)\s*\}\}")
RESPONSE_TAG = re.compile(r"\{%\s*response\s+'[^']*'\s*,\s*'([^']+)'")
PREFIX = {"workspace": "wrk_", "request_group": "fld_", "request": "req_", "environment": "env_"}
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def check_json_text(text):
    """Return an error message, or None when the body is valid JSON with tags filled in."""
    try:
        json.loads(TAG.sub("X", text))
        return None
    except ValueError as exc:
        try:
            json.loads(TAG.sub('"X"', text))
            return "template tag outside a JSON string (quote it, or use a literal value)"
        except ValueError:
            return "body.text is not valid JSON: %s" % exc


def check(export):
    errors = []
    if export.get("_type") != "export" or export.get("__export_format") != 4:
        errors.append("envelope: need _type 'export' and __export_format 4")
    resources = export.get("resources")
    if not isinstance(resources, list):
        return errors + ["envelope: resources must be a list"]

    ids = {}
    for r in resources:
        rid = r.get("_id")
        if rid in ids:
            errors.append("%s: duplicate _id" % rid)
        ids[rid] = r
        want = PREFIX.get(r.get("_type"))
        if want and not str(rid).startswith(want):
            errors.append("%s: %s _id must start with %s" % (rid, r.get("_type"), want))
    env_vars = set()
    for r in resources:
        if r.get("_type") == "environment":
            env_vars |= set((r.get("data") or {}).keys())
        if r.get("_type") != "workspace" and r.get("parentId") not in ids:
            errors.append("%s: parentId %s not found" % (r.get("_id"), r.get("parentId")))

    for r in resources:
        rid, name = r.get("_id"), r.get("name")
        where = "%s (%s)" % (name, rid)
        for s in _strings(r):
            for v in VAR.findall(s):
                if not v.startswith("_."):
                    errors.append("%s: write {{ _.%s }} instead of {{ %s }}" % (where, v, v))
                elif v[2:].split(".")[0].strip() not in env_vars:
                    errors.append("%s: variable %s is not defined in the environment" % (where, v))
            for target in RESPONSE_TAG.findall(s):
                if target not in ids or ids[target].get("_type") != "request":
                    errors.append("%s: response tag points at unknown request %s" % (where, target))
        if r.get("_type") != "request":
            continue
        method = r.get("method")
        if method not in METHODS:
            errors.append("%s: invalid method %r" % (where, method))
        for field in ("headers", "parameters"):
            items = r.get(field, [])
            if not isinstance(items, list) or not all(
                    isinstance(i, dict) and isinstance(i.get("name"), str) and isinstance(i.get("value"), str)
                    for i in items):
                errors.append("%s: %s must be a list of {name, value} strings" % (where, field))
            elif items:
                pair_ids = [i.get("id") for i in items]
                if not all(pair_ids) or len(set(pair_ids)) != len(pair_ids):
                    errors.append("%s: every %s row needs a unique id (e.g. pair_<hex>)" % (where, field[:-1]))
        body = r.get("body")
        if body is None:
            body = {}
        if not isinstance(body, dict):
            errors.append("%s: body must be an object" % where)
            continue
        extra = set(body) - {"mimeType", "text"}
        if extra:
            errors.append("%s: body has %s; the payload goes into body.text as a JSON string, "
                          "e.g. {\"mimeType\": \"application/json\", \"text\": \"{\\\"Field\\\": 1}\"}"
                          % (where, ", ".join(sorted(extra))))
            continue
        has_body = bool(body.get("text"))
        if body and body.get("mimeType") != "application/json":
            errors.append("%s: body.mimeType must be application/json" % where)
        if "text" in body and not isinstance(body["text"], str):
            errors.append("%s: body.text must be a string (serialize the JSON)" % where)
            continue
        if has_body:
            msg = check_json_text(body["text"])
            if msg:
                errors.append("%s: %s" % (where, msg))
        if method == "GET" and has_body:
            errors.append("%s: GET request must not have a body" % where)
        ctype = [h.get("value", "") for h in r.get("headers", []) if str(h.get("name", "")).lower() == "content-type"]
        if has_body and not any(c.startswith("application/json") for c in ctype):
            errors.append("%s: body without Content-Type: application/json header" % where)
    return errors


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    with open(sys.argv[1], encoding="utf-8") as fh:
        errors = check(json.load(fh))
    for e in errors:
        print("error: " + e, file=sys.stderr)
    print("%s: %s" % (sys.argv[1], "%d error(s)" % len(errors) if errors else "ok"), file=sys.stderr)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
