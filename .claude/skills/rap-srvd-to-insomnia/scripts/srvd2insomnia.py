#!/usr/bin/env python3
"""Generate an Insomnia V4 export (collection) from an ABAP RAP service definition.

Two steps, both optional to run separately:
  1. parse   SRVD (+ optional CDS projection views and BDEFs) -> spec JSON
  2. render  spec JSON -> Insomnia V4 export JSON

Typical use:
  srvd2insomnia.py --srvd zui_travel.srvd.srvdsrv --src-dir src/ \
      --binding ZUI_TRAVEL_O4 --collection-name "Travel O4" --dump-spec spec.json -o insomnia.json
  # review / fix spec.json, then re-render from it:
  srvd2insomnia.py --spec spec.json -o insomnia.json

Standard library only.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def strip_comments(src):
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    src = re.sub(r"//[^\n]*", " ", src)
    src = re.sub(r"--[^\n]*", " ", src)  # legacy CDS comment style
    return src


def strip_annotations(src):
    # @Foo.bar: 'x'  /  @Foo: { ... }  /  @Foo: [ ... ]
    out, i = [], 0
    while i < len(src):
        if src[i] == "@":
            m = re.match(r"@<?[\w.]+\s*(:\s*)?", src[i:])
            if not m:
                out.append(src[i])
                i += 1
                continue
            i += m.end()
            if m.group(1):
                i = skip_value(src, i)
            continue
        out.append(src[i])
        i += 1
    return "".join(out)


def skip_value(src, i):
    while i < len(src) and src[i] in " \t\r\n":
        i += 1
    if i >= len(src):
        return i
    if src[i] in "{[":
        depth, open_c = 0, src[i]
        close_c = "}" if open_c == "{" else "]"
        while i < len(src):
            if src[i] == "'":
                i = src.index("'", i + 1) + 1 if "'" in src[i + 1:] else len(src)
                continue
            if src[i] == open_c:
                depth += 1
            elif src[i] == close_c:
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
        return i
    if src[i] == "'":
        j = src.find("'", i + 1)
        return len(src) if j < 0 else j + 1
    m = re.match(r"[#\w.\-]+", src[i:])
    return i + (m.end() if m else 0)


def block_after(src, start):
    """Return (body, end) of the {...} block that begins at/after start."""
    i = src.find("{", start)
    if i < 0:
        return "", start
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i + 1:j], j + 1
    return src[i + 1:], len(src)


def remove_nested_blocks(body):
    out, depth = [], 0
    for ch in body:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def parse_srvd(src):
    clean = strip_annotations(strip_comments(src))
    m = re.search(r"define\s+service\s+(\w+)", clean, re.I)
    if not m:
        sys.exit("error: no 'define service <name>' found in SRVD source")
    name = m.group(1)
    body, _ = block_after(clean, m.end())
    entities = []
    for em in re.finditer(r"expose\s+([\w/]+)(?:\s+as\s+(\w+))?\s*;", body, re.I):
        cds = em.group(1)
        entities.append({"alias": em.group(2) or cds, "cds": cds})
    if not entities:
        sys.exit("error: SRVD '%s' exposes no entities" % name)
    return name, entities


def guess_type(field):
    f = field.lower()
    if f.endswith("uuid") or f.endswith("guid") or f in ("uuid", "guid"):
        return "guid"
    return "string"


def parse_cds(src):
    """Best effort: key fields (alias names) and exposed associations."""
    clean = strip_annotations(strip_comments(src))
    m = re.search(r"define\s+(?:root\s+)?(?:view\s+entity|view|custom\s+entity|abstract\s+entity|"
                  r"table\s+function|transient\s+view\s+entity)\s+([\w/]+)", clean, re.I)
    name = m.group(1) if m else None
    root = bool(re.search(r"define\s+root\s+", clean, re.I))
    # select list: last {...} block of the definition
    body = ""
    if m:
        body, _ = block_after(clean, m.end())
    keys = []
    for km in re.finditer(r"\bkey\s+([\w.]+)(?:\s+as\s+(\w+))?(?:\s*:\s*([\w.]+))?", body, re.I):
        field = km.group(2) or km.group(1).split(".")[-1]
        typ = guess_type(field)
        if km.group(3) and re.search(r"sysuuid|uuid|raw16", km.group(3), re.I):
            typ = "guid"
        keys.append({"name": field, "type": typ})
    assocs = []
    for am in re.finditer(r"(?:^|,)\s*(_\w+)\s*(?=[,:]|$)", body, re.M):
        if am.group(1) not in assocs:
            assocs.append(am.group(1))
    return {"name": name, "root": root, "keys": keys, "associations": assocs}


DRAFT_ACTIONS = {"edit", "activate", "discard", "resume", "prepare"}


def parse_bdef(src):
    """Return {cds_name_lower: behavior} for every 'define behavior for' block."""
    clean = strip_comments(src)
    header = clean.split("define behavior", 1)[0]
    draft = bool(re.search(r"\b(with|use)\s+draft\s*;", header, re.I))
    projection = bool(re.match(r"\s*projection\b", header, re.I))
    result = {}
    for bm in re.finditer(r"define\s+behavior\s+for\s+([\w/]+)(?:\s+alias\s+(\w+))?", clean, re.I):
        body, _ = block_after(clean, bm.end())
        flat = remove_nested_blocks(body)
        beh = {
            "alias": bm.group(2),
            "draft": draft,
            "projection": projection,
            "create": bool(re.search(r"(^|;)\s*(use\s+)?(internal\s+)?create\b(?!\s*\()", flat, re.I | re.M))
            and not re.search(r"(^|;)\s*internal\s+create\b", flat, re.I | re.M),
            "update": bool(re.search(r"(^|;)\s*(use\s+)?update\b", flat, re.I | re.M))
            and not re.search(r"(^|;)\s*internal\s+update\b", flat, re.I | re.M),
            "delete": bool(re.search(r"(^|;)\s*(use\s+)?delete\b", flat, re.I | re.M))
            and not re.search(r"(^|;)\s*internal\s+delete\b", flat, re.I | re.M),
            "actions": [],
            "createByAssociation": [],
        }
        # "create ( features : instance );" -> the negative lookahead above skips it; re-check
        if re.search(r"(^|;)\s*(use\s+)?create\s*\(", flat, re.I | re.M):
            beh["create"] = True
        for am in re.finditer(r"(?:^|;)\s*(use\s+)?((?:static\s+|factory\s+|internal\s+|repeatable\s+)*)"
                              r"(action|function)\s*(?:\([^)]*\))?\s+(\w+)([^;]*);", flat, re.I | re.M):
            mods = am.group(2).lower()
            if "internal" in mods or am.group(4).lower() in DRAFT_ACTIONS:
                continue
            rest = am.group(5)
            pm = re.search(r"\bparameter\s+([\w/$]+)", rest, re.I)
            beh["actions"].append({
                "name": am.group(4),
                "kind": am.group(3).lower(),
                "static": "static" in mods,
                "factory": "factory" in mods,
                "parameter": pm.group(1) if pm else None,
            })
        for asm in re.finditer(r"(?:^|;|})\s*(use\s+)?association\s+(_\w+)\s*\{([^}]*)\}", body, re.I | re.M):
            if re.search(r"\bcreate\b", asm.group(3), re.I):
                beh["createByAssociation"].append(asm.group(2))
        result[bm.group(1).lower()] = beh
    return result


def find_sources(src_dir):
    """Index abapGit-style files: <name>.ddls.asddls, <name>.bdef.asbdef (and plain .cds/.bdef)."""
    cds, bdef = {}, {}
    for root, _, files in os.walk(src_dir):
        for f in files:
            p = os.path.join(root, f)
            lf = f.lower()
            base = lf.split(".")[0].replace("#", "/")
            if lf.endswith(".ddls.asddls") or lf.endswith(".asddls") or lf.endswith(".cds"):
                cds[base] = p
            elif lf.endswith(".bdef.asbdef") or lf.endswith(".asbdef") or lf.endswith(".bdef"):
                bdef[base] = p
    return cds, bdef


def read(p):
    with open(p, encoding="utf-8-sig") as fh:
        return fh.read()


def build_spec(args):
    srvd_name, entities = parse_srvd(read(args.srvd))
    cds_files, bdef_files = ({}, {})
    if args.src_dir:
        cds_files, bdef_files = find_sources(args.src_dir)
    cds_info = {}
    for p in list(cds_files.values()) + (args.cds or []):
        info = parse_cds(read(p))
        if info["name"]:
            cds_info[info["name"].lower()] = info
    behaviors, action_params = {}, {}
    for p in list(bdef_files.values()) + (args.bdef or []):
        for k, v in parse_bdef(read(p)).items():
            # a projection BDEF wins over an interface BDEF for the same entity name
            if k not in behaviors or (v["projection"] and not behaviors[k]["projection"]):
                behaviors[k] = v
            for a in v["actions"]:
                if a["parameter"]:
                    action_params[a["name"].lower()] = a["parameter"]
    # projections only say "use action x": take parameter structures from the base BDEF
    for v in behaviors.values():
        for a in v["actions"]:
            a["parameter"] = a["parameter"] or action_params.get(a["name"].lower())
    warnings = []
    for e in entities:
        info = cds_info.get(e["cds"].lower())
        beh = behaviors.get(e["cds"].lower())
        e["keys"] = info["keys"] if info else []
        e["associations"] = info["associations"] if info else []
        e["root"] = info["root"] if info else e is entities[0]
        if not info:
            warnings.append("no CDS source for %s: keys unknown, fill 'keys' in the spec" % e["cds"])
        elif not e["keys"]:
            warnings.append("no key fields found in %s" % e["cds"])
        if beh:
            e.update({k: beh[k] for k in ("draft", "create", "update", "delete", "actions",
                                          "createByAssociation")})
        else:
            e.update({"draft": False, "create": False, "update": False, "delete": False,
                      "actions": [], "createByAssociation": []})
            if behaviors:
                warnings.append("no behavior definition for %s: treated as read-only" % e["cds"])
    if not behaviors:
        warnings.append("no BDEF given: all entities treated as read-only (GET only)")
    binding = args.binding or srvd_name
    spec = {
        "serviceDefinition": srvd_name,
        "collectionName": args.collection_name or binding,
        "serviceBinding": binding,
        "odataVersion": args.odata,
        "bindingType": args.binding_type,
        "serviceVersion": args.service_version,
        "baseUrl": args.base_url,
        "sapClient": args.sap_client,
        "entities": entities,
    }
    return spec, warnings


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def stable_id(prefix, *parts):
    return prefix + "_" + hashlib.sha1("|".join(parts).encode()).hexdigest()[:24]


def service_path(spec):
    b = spec["serviceBinding"].lower()
    if spec["odataVersion"] == "v2":
        return "/sap/opu/odata/sap/%s" % spec["serviceBinding"].upper()
    seg = "srvd_a2x" if spec["bindingType"] == "api" else "srvd"
    return "/sap/opu/odata4/sap/%s/%s/sap/%s/%s" % (b, seg, spec["serviceDefinition"].lower(),
                                                    spec["serviceVersion"])


def var(entity, key):
    return "%s_%s" % (entity["alias"], key["name"])


def key_literal(spec, entity, key):
    v = "{{ _.%s }}" % var(entity, key)
    t = key.get("type", "string")
    if spec["odataVersion"] == "v2":
        if t == "guid":
            return "guid'%s'" % v
        return v if t == "number" else "'%s'" % v
    return v if t in ("guid", "number") else "'%s'" % v


def key_predicate(spec, entity, active=True):
    parts = ["%s=%s" % (k["name"], key_literal(spec, entity, k)) for k in entity["keys"]]
    if entity.get("draft"):
        parts.append("IsActiveEntity=%s" % ("true" if active else "false"))
    if not parts:
        return "(<key>)"
    return "(%s)" % ",".join(parts)


def key_query(spec, entity, active=True):
    q = [(k["name"], key_literal(spec, entity, k)) for k in entity["keys"]]
    if entity.get("draft"):
        q.append(("IsActiveEntity", "true" if active else "false"))
    return q


def sample_body(entity):
    body = {}
    for k in entity["keys"]:
        if k.get("type") != "guid":  # managed UUID keys are usually early-numbered by the framework
            body[k["name"]] = "{{ _.%s }}" % var(entity, k)
    body["<Field>"] = "<value>"
    return json.dumps(body, indent=2)


def render(spec):
    svc = spec["serviceDefinition"]
    v2 = spec["odataVersion"] == "v2"
    name = spec.get("collectionName") or spec["serviceBinding"]
    root = "{{ _.base_url }}" + service_path(spec)
    ns = "com.sap.gateway.srvd.%s.v%s" % (svc.lower(), spec["serviceVersion"])
    now = int(time.time() * 1000)
    wrk = stable_id("wrk", name)
    resources = [{
        "_id": wrk, "_type": "workspace", "parentId": None, "name": name,
        "description": "Generated from RAP service definition %s (binding %s, OData %s)"
                       % (svc, spec["serviceBinding"], spec["odataVersion"].upper()),
        "scope": "collection", "created": now, "modified": now,
    }]

    csrf_id = stable_id("req", name, "csrf")
    # the token lives in an environment variable that reads the Fetch request's response header,
    # so every modifying request just sends {{ _.csrf_token }}
    env_data = {
        "base_url": spec.get("baseUrl") or "https://<host>:<port>",
        "sap_client": spec.get("sapClient") or "100",
        "csrf_token": "{%% response 'header', '%s', 'b64::%s::46b', 'when-expired', 600 %%}" % (
            csrf_id, base64.b64encode(b"x-csrf-token").decode()),
        "username": "",
        "password": "",
    }
    for e in spec["entities"]:
        for k in e["keys"]:
            env_data[var(e, k)] = ""
    resources.append({
        "_id": stable_id("env", name, "base"), "_type": "environment", "parentId": wrk,
        "name": "Base Environment", "data": env_data, "dataPropertyOrder": {"&": list(env_data)},
        "color": None, "isPrivate": False, "metaSortKey": now, "created": now, "modified": now,
    })

    auth = {"type": "basic", "useISO88591": False, "disabled": False,
            "username": "{{ _.username }}", "password": "{{ _.password }}"}
    sort = [0]

    def folder(fname, desc=""):
        fid = stable_id("fld", name, fname)
        sort[0] += 1
        resources.append({"_id": fid, "_type": "request_group", "parentId": wrk, "name": fname,
                          "description": desc, "environment": {}, "environmentPropertyOrder": None,
                          "metaSortKey": sort[0], "created": now, "modified": now})
        return fid

    setting_fld = folder("Setting", "CSRF token and service metadata. Run 'Fetch CSRF token' first.")
    get_fld = folder("Get", "Read requests")
    post_fld = folder("Post", "Modifying requests (POST/PATCH/DELETE), sent with {{ _.csrf_token }}")

    def request(rname, method, url, params=None, body=None, desc="", rid=None, extra_headers=None,
                parent=None):
        if parent is None:
            parent = get_fld if method == "GET" else post_fld
        sort[0] += 1
        extra_headers = extra_headers or []
        headers = []
        if not any(h["name"] == "Accept" for h in extra_headers):
            headers.append({"name": "Accept", "value": "application/json"})
        if method not in ("GET", "HEAD"):
            headers.append({"name": "X-CSRF-Token", "value": "{{ _.csrf_token }}"})
        if body is not None:
            headers.append({"name": "Content-Type", "value": "application/json"})
        headers += extra_headers
        if method in ("PATCH", "PUT", "DELETE"):
            headers.append({"name": "If-Match", "value": "*"})
        p = [{"name": "sap-client", "value": "{{ _.sap_client }}"}]
        for n, val in params or []:
            p.append({"name": n, "value": val})
        resources.append({
            "_id": rid or stable_id("req", name, parent, rname), "_type": "request", "parentId": parent,
            "name": rname, "description": desc, "method": method, "url": url,
            "body": {} if body is None else {"mimeType": "application/json", "text": body},
            "parameters": p, "headers": headers, "authentication": auth,
            "metaSortKey": sort[0], "isPrivate": False, "settingStoreCookies": True,
            "settingSendCookies": True, "settingDisableRenderRequestBody": False,
            "settingEncodeUrl": True, "settingRebuildPath": True, "settingFollowRedirects": "global",
            "created": now, "modified": now,
        })

    fmt = [("$format", "json")] if v2 else []
    request("Fetch CSRF token", "GET", root + "/", fmt, rid=csrf_id, parent=setting_fld,
            desc="Run once per session. The csrf_token environment variable reads the token from this "
                 "response (re-fetched after 10 min). Session cookies are kept in the workspace cookie jar.",
            extra_headers=[{"name": "X-CSRF-Token", "value": "Fetch"}])
    request("$metadata", "GET", root + "/$metadata", parent=setting_fld,
            extra_headers=[{"name": "Accept", "value": "application/xml"}])

    for e in spec["entities"]:
        ent = e["alias"]
        coll = root + "/" + ent
        pred = key_predicate(spec, e, active=True)
        draft_pred = key_predicate(spec, e, active=False)
        list_params = fmt + [("$top", "50")]
        list_params.append(("$inlinecount", "allpages") if v2 else ("$count", "true"))
        request("%s - List" % ent, "GET", coll, list_params, desc="CDS entity %s" % e["cds"])
        if e["keys"] or e.get("draft"):
            request("%s - Read by key" % ent, "GET", coll + pred, fmt)
            for assoc in e.get("associations", []):
                request("%s - %s" % (ent, assoc), "GET", coll + pred + "/" + assoc, fmt + [("$top", "50")])
        if e.get("create"):
            request("%s - Create" % ent, "POST", coll, fmt, body=sample_body(e),
                    desc="Creates a draft instance." if e.get("draft") else "")
        for assoc in e.get("createByAssociation", []):
            target_pred = draft_pred if e.get("draft") else pred
            request("%s - Create via %s" % (ent, assoc), "POST", coll + target_pred + "/" + assoc, fmt,
                    body=json.dumps({"<Field>": "<value>"}, indent=2))
        if e.get("update"):
            target_pred = draft_pred if e.get("draft") else pred
            request("%s - Update" % ent, "PATCH", coll + target_pred, fmt,
                    body=json.dumps({"<Field>": "<value>"}, indent=2),
                    desc="Draft enabled: edit the draft instance (IsActiveEntity=false), then Activate."
                    if e.get("draft") else "")
        if e.get("delete"):
            # draft children are only changed through the draft of their root
            child_draft = e.get("draft") and not e.get("root")
            request("%s - Delete" % ent, "DELETE", coll + (draft_pred if child_draft else pred), fmt)
        if e.get("draft") and e.get("root"):
            for dname, active, body in (("Edit", True, '{\n  "PreserveChanges": true\n}'),
                                        ("Activate", False, "{}"),
                                        ("Prepare", False, "{}")):
                p = pred if active else draft_pred
                if v2:
                    request("%s - Draft %s" % (ent, dname), "POST", root + "/" + ent + dname,
                            fmt + key_query(spec, e, active))
                else:
                    op = "draftPrepare" if dname == "Prepare" else dname
                    request("%s - Draft %s" % (ent, dname), "POST", coll + p + "/" + ns + "." + op, body=body)
            request("%s - Discard draft" % ent, "DELETE", coll + draft_pred, fmt)
        for a in e.get("actions", []):
            label = "Function" if a["kind"] == "function" else "Action"
            if v2:
                params = fmt + ([] if a["static"] else key_query(spec, e, True))
                method = "GET" if a["kind"] == "function" else "POST"
                request("%s - %s %s" % (ent, label, a["name"]), method, root + "/" + a["name"], params,
                        desc="V2 function import name may be prefixed; verify in $metadata.")
                continue
            url = (coll if a["static"] else coll + pred) + "/" + ns + "." + a["name"]
            desc = []
            if a["static"]:
                desc.append("static")
            if a["factory"]:
                desc.append("factory")
            if a["parameter"]:
                desc.append("parameter structure %s: fill the body with its fields" % a["parameter"])
            if a["kind"] == "function":
                request("%s - %s %s" % (ent, label, a["name"]), "GET", url + "()", desc=", ".join(desc))
            else:
                request("%s - %s %s" % (ent, label, a["name"]), "POST", url,
                        body='{\n  "<param>": "<value>"\n}' if a["parameter"] else "{}", desc=", ".join(desc))

    return {
        "_type": "export", "__export_format": 4,
        "__export_date": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "__export_source": "rap-srvd-to-insomnia", "resources": resources,
    }


OVERRIDES = [("binding", "serviceBinding"), ("odata", "odataVersion"), ("binding_type", "bindingType"),
             ("service_version", "serviceVersion"), ("base_url", "baseUrl"), ("sap_client", "sapClient"),
             ("collection_name", "collectionName")]
DEFAULTS = {"odataVersion": "v4", "bindingType": "ui", "serviceVersion": "0001"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--srvd", help="SRVD source file")
    ap.add_argument("--src-dir", help="directory with CDS (.ddls.asddls) / BDEF (.bdef.asbdef) sources")
    ap.add_argument("--cds", nargs="*", help="extra CDS source files")
    ap.add_argument("--bdef", nargs="*", help="extra BDEF source files")
    ap.add_argument("--collection-name", help="Insomnia collection name (default: binding name)")
    ap.add_argument("--binding", help="service binding name (default: SRVD name)")
    ap.add_argument("--odata", choices=["v2", "v4"], help="default v4")
    ap.add_argument("--binding-type", choices=["ui", "api"], help="ui (srvd) or api (srvd_a2x); default ui")
    ap.add_argument("--service-version", help="default 0001")
    ap.add_argument("--base-url", help="e.g. https://my-s4.example.com:44300")
    ap.add_argument("--sap-client", help="SAP client, e.g. 100")
    ap.add_argument("--spec", help="render from an existing spec JSON instead of parsing sources")
    ap.add_argument("--dump-spec", help="write the parsed spec JSON here")
    ap.add_argument("-o", "--output", help="Insomnia V4 export JSON output path")
    args = ap.parse_args()

    if args.spec:
        spec, warnings = json.loads(read(args.spec)), []
    elif args.srvd:
        spec, warnings = build_spec(args)
    else:
        ap.error("--srvd or --spec is required")
    # explicit options override what the spec says
    for opt, field in OVERRIDES:
        if getattr(args, opt) is not None:
            spec[field] = getattr(args, opt)
    for field, default in DEFAULTS.items():
        if not spec.get(field):
            spec[field] = default

    for w in warnings:
        print("warning: " + w, file=sys.stderr)
    if args.dump_spec:
        with open(args.dump_spec, "w", encoding="utf-8") as fh:
            json.dump(spec, fh, indent=2)
        print("spec written: %s" % os.path.abspath(args.dump_spec), file=sys.stderr)
    if args.output:
        export = render(spec)
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(export, fh, indent=2)
        n = sum(1 for r in export["resources"] if r["_type"] == "request")
        print("insomnia export written: %s (%d requests)" % (os.path.abspath(args.output), n),
              file=sys.stderr)
    if not args.output and not args.dump_spec:
        json.dump(spec, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
