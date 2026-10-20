#!/usr/bin/env python3
"""Generate an Insomnia V4 export (collection) from an ABAP RAP service definition.

Two steps, both optional to run separately:
  1. parse   SRVD (+ optional CDS, BDEF sources and the service's $metadata) -> spec JSON
  2. render  spec JSON -> Insomnia V4 export JSON, checked by insomnia_check.py before it is written

Typical use:
  srvd2insomnia.py --srvd zui_travel.srvd.srvdsrv --src-dir src/ --metadata metadata.xml \
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # sibling modules, also under python -I
import edmx  # noqa: E402
import insomnia_check  # noqa: E402
import payload  # noqa: E402
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


def mask_parens(s):
    """Same-length copy of s with everything inside (...) blanked, for top-level searches."""
    out, depth = [], 0
    for ch in s:
        if ch == "(":
            depth += 1
            out.append(ch)
        elif ch == ")":
            depth -= 1
            out.append(ch)
        else:
            out.append(" " if depth > 0 else ch)
    return "".join(out)


def split_top(s):
    parts, cur, depth, quoted = [], [], 0, False
    for ch in s:
        if ch == "'":
            quoted = not quoted
        if not quoted:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch in ",;" and depth == 0:
                parts.append("".join(cur))
                cur = []
                continue
        cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


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


def abap_to_edm(abap_type):
    """(edm, maxLength) for a built-in ABAP type; (None, None) for data elements we cannot resolve."""
    t = abap_type.lower().replace(" ", "")
    m = re.match(r"(?:abap\.)?(\w+)(?:\((\d+)(?:,\d+)?\))?$", t)
    if not m:
        return None, None
    base, length = m.group(1), m.group(2)
    if base in ("int1", "int2", "int4"):
        return "Edm.Int32", None
    if base == "int8":
        return "Edm.Int64", None
    if base in ("dec", "curr", "quan", "decfloat16", "decfloat34", "d16n", "d34n"):
        return "Edm.Decimal", None
    if base == "fltp":
        return "Edm.Double", None
    if base in ("dats", "datn"):
        return "Edm.Date", None
    if base in ("tims", "timn"):
        return "Edm.TimeOfDay", None
    if base in ("utclong", "timestamp", "timestampl", "tzntstmps", "tzntstmpl"):
        return "Edm.DateTimeOffset", None
    if base in ("boolean", "abap_boolean", "xsdboolean", "abap_bool"):
        return "Edm.Boolean", None
    if base in ("sysuuid_x16", "sysuuid_c32", "sysuuid_c36") or (base == "raw" and length == "16"):
        return "Edm.Guid", None
    if base in ("char", "string", "sstring", "numc", "lang", "cuky", "unit", "clnt", "accp"):
        return "Edm.String", length
    return None, None


def to_v2_edm(edm):
    return {"Edm.Date": "Edm.DateTime", "Edm.TimeOfDay": "Edm.Time"}.get(edm, edm)


def key_kind(edm):
    if edm == "Edm.Guid":
        return "guid"
    if edm in payload.INT_TYPES or edm in ("Edm.Int64", "Edm.Decimal", "Edm.Double"):
        return "number"
    return "string"


ASSOC_DEF = re.compile(r"\b(?:composition|association)\s*(?:\[[^\]]*\])?\s*(?:of|to)\s+(?:parent\s+)?"
                       r"([\w/]+)\s+as\s+(_\w+)", re.I)


def parse_element(p):
    m = re.match(r"(_\w+)\b(.*)$", p, re.S)
    if m:
        t = re.search(r"redirected\s+to\s+(?:composition\s+child\s+|parent\s+)?([\w/]+)", m.group(2), re.I)
        return {"assoc": m.group(1), "target": t.group(1) if t else None}
    key = False
    while True:
        km = re.match(r"(key|virtual|localized)\s+", p, re.I)
        if not km:
            break
        key = key or km.group(1).lower() == "key"
        p = p[km.end():]
    masked = mask_parens(p)
    edm = max_len = None
    colon = masked.find(":")
    if colon >= 0:
        edm, max_len = abap_to_edm(p[colon + 1:].strip())
        p, masked = p[:colon].strip(), masked[:colon].strip()
    am = re.search(r"\bas\s+(\w+)\s*$", masked, re.I)
    if am:
        name = am.group(1)
    elif re.fullmatch(r"[\w.$]+", p):
        name = p.split(".")[-1]
    else:
        return None  # unnamed expression
    typed = edm is not None
    if not typed:
        edm = "Edm.Guid" if re.search(r"(uuid|guid)$", name, re.I) else "Edm.String"
    f = {"name": name, "edm": edm, "key": key, "typed": typed}
    if max_len:
        f["maxLength"] = max_len
    return f


def parse_cds(src):
    """Fields, keys and associations of a CDS view / projection / abstract entity (best effort)."""
    clean = strip_annotations(strip_comments(src))
    m = re.search(r"define\s+(?:root\s+)?(?:view\s+entity|view|custom\s+entity|abstract\s+entity|"
                  r"table\s+function|transient\s+view\s+entity)\s+([\w/]+)", clean, re.I)
    name = m.group(1) if m else None
    root = bool(re.search(r"define\s+root\s+", clean, re.I))
    base = re.search(r"\bprojection\s+on\s+([\w/]+)", clean, re.I)
    body = block_after(clean, m.end())[0] if m else ""
    header = clean[:clean.find(body)] if body else clean
    fields, assocs, targets = [], [], {}
    for target, alias in ASSOC_DEF.findall(header):
        targets[alias] = target
    for part in split_top(body):
        el = parse_element(part)
        if not el:
            continue
        if "assoc" in el:
            if el["assoc"] not in assocs:
                assocs.append(el["assoc"])
            if el["target"]:
                targets[el["assoc"]] = el["target"]
        else:
            fields.append(el)
    return {"name": name, "root": root, "base": base.group(1) if base else None, "fields": fields,
            "associations": assocs, "associationTargets": targets}


DRAFT_ACTIONS = {"edit", "activate", "discard", "resume", "prepare", "draftprepare"}


def parse_field_control(flat):
    fields = {}
    for fm in re.finditer(r"(?:^|;)\s*field\s*\(([^)]*)\)\s*([^;]+);", flat, re.I | re.M):
        mods = [re.sub(r"\s+", "", x.lower()) for x in fm.group(1).split(",")]
        for n in re.split(r"\s*,\s*", fm.group(2).strip()):
            fc = fields.setdefault(n.lower(), {})
            for mod in mods:
                if mod in ("readonly", "numbering:managed"):
                    fc["readonly"] = True
                elif mod == "readonly:update":
                    fc["createOnly"] = True
                elif mod in ("mandatory", "mandatory:create"):
                    fc["mandatory"] = True
    return fields


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

        def op(name):
            return (bool(re.search(r"(^|;)\s*(use\s+)?%s\b" % name, flat, re.I | re.M))
                    and not re.search(r"(^|;)\s*internal\s+%s\b" % name, flat, re.I | re.M))

        beh = {"alias": bm.group(2), "draft": draft, "projection": projection,
               "create": op("create"), "update": op("update"), "delete": op("delete"),
               "actions": [], "createByAssociation": [], "fields": parse_field_control(flat)}
        for am in re.finditer(r"(?:^|;)\s*(use\s+)?((?:static\s+|factory\s+|internal\s+|repeatable\s+)*)"
                              r"(action|function)\s*(?:\([^)]*\))?\s+(\w+)([^;]*);", flat, re.I | re.M):
            mods = am.group(2).lower()
            if "internal" in mods or am.group(4).lower() in DRAFT_ACTIONS:
                continue
            pm = re.search(r"\bparameter\s+([\w/$]+)", am.group(5), re.I)
            beh["actions"].append({"name": am.group(4), "kind": am.group(3).lower(),
                                   "static": "static" in mods, "factory": "factory" in mods,
                                   "parameter": pm.group(1) if pm else None})
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

    alias_of = {e["cds"].lower(): e["alias"] for e in entities}
    warnings = []
    for e in entities:
        info = cds_info.get(e["cds"].lower())
        beh = behaviors.get(e["cds"].lower())
        base_beh = behaviors.get(info["base"].lower()) if info and info["base"] else None
        if not beh and base_beh:
            beh = base_beh
            warnings.append("no projection BDEF for %s: using %s" % (e["cds"], info["base"]))
        # field control lives in the interface BDEF; a projection BDEF may add to it
        fc = {}
        for b in (base_beh, behaviors.get(e["cds"].lower())):
            for k, v in (b or {}).get("fields", {}).items():
                fc.setdefault(k, {}).update(v)
        e["fields"] = [dict(f, **fc.get(f["name"].lower(), {})) for f in (info["fields"] if info else [])]
        e["keys"] = [{"name": f["name"], "type": key_kind(f["edm"])} for f in e["fields"] if f["key"]]
        e["associations"] = info["associations"] if info else []
        e["associationTargets"] = {a: alias_of.get(t.lower(), t)
                                   for a, t in (info["associationTargets"] if info else {}).items()}
        e["root"] = info["root"] if info else e is entities[0]
        if not info and not args.metadata:
            warnings.append("no CDS source for %s: keys and fields unknown (pass --metadata)" % e["cds"])
        elif info and not e["keys"]:
            warnings.append("no key fields found in %s" % e["cds"])
        if beh:
            e.update({k: beh[k] for k in ("draft", "create", "update", "delete", "actions",
                                          "createByAssociation")})
        else:
            e.update({"draft": False, "create": False, "update": False, "delete": False,
                      "actions": [], "createByAssociation": []})
            if behaviors and info:
                warnings.append("no behavior definition for %s: treated as read-only" % e["cds"])
        for a in e["actions"]:
            struct = cds_info.get((a["parameter"] or "").lower())
            if struct:
                a["params"] = [{"name": f["name"], "edm": f["edm"], "maxLength": f.get("maxLength")}
                               for f in struct["fields"]]
            elif a["parameter"]:
                warnings.append("action %s.%s: parameter %s source not found, body fields unknown "
                                "(pass --metadata or the abstract entity source)"
                                % (e["alias"], a["name"], a["parameter"]))
    by_alias = {e["alias"]: e for e in entities}
    for e in entities:
        for f in e["fields"]:
            # RAP UUID keys are almost always managed numbering; $metadata settles it when given
            if f["key"] and f["edm"] == "Edm.Guid" and not any(f.get(k) for k in ("readonly", "createOnly", "mandatory")):
                f["readonly"] = True
        for assoc in e["createByAssociation"]:
            child = by_alias.get(e["associationTargets"].get(assoc))
            # the child's copy of the parent key is filled by the framework
            for f in (child or {}).get("fields", []):
                if f["name"] in {k["name"] for k in e["keys"]} and not f["key"]:
                    f["readonly"] = True
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
        "previewUrl": args.preview_url,
        "entities": entities,
    }
    return spec, warnings


def apply_metadata(spec, md, warnings):
    """Overwrite guessed facts with the service's $metadata: types, keys, read-only fields, operations."""
    if spec.get("odataVersion") and spec["odataVersion"] != md["version"]:
        warnings.append("$metadata is OData %s but spec says %s: using %s"
                        % (md["version"], spec["odataVersion"], md["version"]))
    spec["odataVersion"] = md["version"]
    v2 = md["version"] == "v2"
    for e in spec["entities"]:
        es = md["entitySets"].get(e["alias"])
        if not es:
            warnings.append("entity set %s not in $metadata" % e["alias"])
            continue
        by_name = {f["name"]: f for f in e.get("fields", [])}
        fields = []
        for pname, p in es["props"].items():
            f = dict(by_name.get(pname, {"name": pname}))
            f.update({"edm": p["edm"], "key": pname in es["keys"], "typed": True})
            if p["maxLength"]:
                f["maxLength"] = p["maxLength"]
            if p["computed"] or not (p["creatable"] or p["updatable"]):
                f["readonly"] = True
            elif p["immutable"] or not p["updatable"]:
                f["createOnly"] = True
            if p["mandatory"]:
                f["mandatory"] = True
            fields.append(f)
        e["fields"] = fields
        e["keys"] = [{"name": k, "type": key_kind(es["props"][k]["edm"])}
                     for k in es["keys"] if k != "IsActiveEntity"]
        if "IsActiveEntity" in es["keys"]:
            e["draft"] = True
        navs = {n: t for n, t in es["navs"].items() if n not in payload.DRAFT_FIELDS}
        e["associations"] = list(navs)
        e["associationTargets"] = {n: t for n, t in navs.items() if t}
        # RAP's V2 binding exposes association _X as navigation property to_X
        e["createByAssociation"] = [a if a in navs else "to" + a if "to" + a in navs else a
                                    for a in e.get("createByAssociation", [])]

        ops = [o for o in md["operations"] if o["boundSet"] == e["alias"]]
        known = {a["name"].lower() for a in e.get("actions", [])}
        for o in ops:  # operations the BDEF sources did not show
            short = o["name"].lower()
            if v2 or short in known or short in DRAFT_ACTIONS:
                continue
            e.setdefault("actions", []).append({"name": o["name"], "kind": o["kind"], "static": o["collection"],
                                                "factory": False, "parameter": None})
        key_names = {k["name"] for k in e["keys"]} | {"IsActiveEntity"}
        for a in e.get("actions", []):
            match = [o for o in ops if o["name"] == a["name"]] or \
                    [o for o in ops if o["name"].lower().endswith(a["name"].lower())]
            if not match:
                warnings.append("action %s.%s not in $metadata" % (e["alias"], a["name"]))
                continue
            o = match[0]
            a["params"] = [{"name": p["name"], "edm": p["edm"], "maxLength": p["maxLength"]}
                           for p in o["params"] if not (v2 and p["name"] in key_names)]
            if v2:
                a["v2Name"], a["v2Method"] = o["name"], o["httpMethod"]
            else:
                a["static"] = o["collection"]
        if v2 and e.get("draft"):
            draft = {}
            for kind, stem in (("Edit", "edit"), ("Activate", "activat"), ("Prepare", "prepar")):
                hit = [o["name"] for o in ops if stem in o["name"].lower()]
                if hit:
                    draft[kind] = hit[0]
            e["v2Draft"] = draft
    return spec


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


def preview_template(url):
    """Browser URL copied from ADT's preview -> host and client replaced by environment variables."""
    url = re.sub(r"^https?://[^/?#]+", "{{ _.base_url }}", url.strip())
    return re.sub(r"([?&]sap-client=)\d+", r"\g<1>{{ _.sap_client }}", url)


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


def render(spec):
    svc = spec["serviceDefinition"]
    v2 = spec["odataVersion"] == "v2"
    name = spec.get("collectionName") or spec["serviceBinding"]
    root = "{{ _.base_url }}{{ _.service_path }}"
    ns = "com.sap.gateway.srvd.%s.v%s" % (svc.lower(), spec["serviceVersion"])
    now = int(time.time() * 1000)
    by_alias = {e["alias"]: e for e in spec["entities"]}
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
        "service_path": service_path(spec),
        "sap_client": spec.get("sapClient") or "100",
        "csrf_token": "{%% response 'header', '%s', 'b64::%s::46b', 'when-expired', 600 %%}" % (
            csrf_id, base64.b64encode(b"x-csrf-token").decode()),
        "preview_url": preview_template(spec["previewUrl"]) if spec.get("previewUrl")
        else "{{ _.base_url }}/<paste the ADT service binding preview URL>",
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

    setting_fld = folder("Setting", "CSRF token, service metadata and the Fiori Elements preview. "
                                    "Run 'Fetch CSRF token' first.")
    get_fld = folder("Get", "Read requests")
    post_fld = folder("Post", "Modifying requests (POST/PATCH/DELETE), sent with {{ _.csrf_token }}")

    def request(rname, method, url, params=None, body=None, desc="", rid=None, extra_headers=None,
                parent=None, sap_client=True):
        """body: a dict/list (serialized here) or None. Never pass a JSON string built by hand."""
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
        p = [{"name": "sap-client", "value": "{{ _.sap_client }}"}] if sap_client else []
        for n, val in params or []:
            p.append({"name": n, "value": val})
        req_id = rid or stable_id("req", name, parent, rname)
        # Insomnia keys header/parameter rows by a unique id ("Render Failure: Invalid array length" without)
        for kind, rows in (("h", headers), ("p", p)):
            for i, row in enumerate(rows):
                row.update({"id": stable_id("pair", req_id, kind, str(i)), "disabled": False})
        resources.append({
            "_id": req_id, "_type": "request", "parentId": parent,
            "name": rname, "description": desc, "method": method, "url": url,
            "body": {} if body is None else {"mimeType": "application/json", "text": payload.dumps(body)},
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
    request("Fiori Elements Preview", "GET", "{{ _.preview_url }}", parent=setting_fld, sap_client=False,
            extra_headers=[{"name": "Accept", "value": "text/html"}],
            desc="The page ADT opens from the service binding (Preview). Open it in a browser; "
                 "Insomnia only shows the HTML. Set preview_url in the environment if it is still a placeholder.")

    def key_value(e):
        return lambda f: "{{ _.%s }}" % var(e, f)

    for e in spec["entities"]:
        ent = e["alias"]
        coll = root + "/" + ent
        pred = key_predicate(spec, e, active=True)
        draft_pred = key_predicate(spec, e, active=False)
        parent_keys = {k["name"] for k in e["keys"]}
        list_params = fmt + [("$top", "50")]
        list_params.append(("$inlinecount", "allpages") if v2 else ("$count", "true"))
        request("%s - List" % ent, "GET", coll, list_params, desc="CDS entity %s" % e["cds"])
        if e["keys"] or e.get("draft"):
            request("%s - Read by key" % ent, "GET", coll + pred, fmt)
            for assoc in e.get("associations", []):
                request("%s - %s" % (ent, assoc), "GET", coll + pred + "/" + assoc, fmt + [("$top", "50")])
        if e.get("create"):
            request("%s - Create" % ent, "POST", coll, fmt,
                    body=payload.body_dict(e, v2, key_value=key_value(e)),
                    desc=("Creates a draft instance.\n" if e.get("draft") else "") + payload.field_guide(e))
        for assoc in e.get("createByAssociation", []):
            child = by_alias.get(e.get("associationTargets", {}).get(assoc))
            target_pred = draft_pred if e.get("draft") else pred
            if child:
                body = payload.body_dict(child, v2, exclude=parent_keys, key_value=key_value(child))
                desc = "Creates %s under %s.\n%s" % (child["alias"], ent,
                                                    payload.field_guide(child, exclude=parent_keys))
            else:
                body, desc = {}, "Target entity of %s unknown: add the child's fields." % assoc
            request("%s - Create via %s" % (ent, assoc), "POST", coll + target_pred + "/" + assoc, fmt,
                    body=body, desc=desc)
        if e.get("create") and not v2:
            deep = {a: by_alias.get(e.get("associationTargets", {}).get(a)) for a in e.get("createByAssociation", [])}
            deep = {a: c for a, c in deep.items() if c}
            if deep:
                body = payload.body_dict(e, v2, key_value=key_value(e))
                for a, c in deep.items():
                    body[a] = [payload.body_dict(c, v2, exclude=parent_keys, key_value=key_value(c))]
                request("%s - Create (deep)" % ent, "POST", coll, fmt, body=body,
                        desc="Deep create: %s with %s in one request." % (ent, ", ".join(deep)))
        if e.get("update"):
            target_pred = draft_pred if e.get("draft") else pred
            request("%s - Update" % ent, "PATCH", coll + target_pred, fmt,
                    body=payload.body_dict(e, v2, for_update=True),
                    desc=("Draft enabled: edit the draft instance (IsActiveEntity=false), then Activate.\n"
                          if e.get("draft") else "") + payload.field_guide(e, for_update=True))
        if e.get("delete"):
            # draft children are only changed through the draft of their root
            child_draft = e.get("draft") and not e.get("root")
            request("%s - Delete" % ent, "DELETE", coll + (draft_pred if child_draft else pred), fmt)
        if e.get("draft") and e.get("root"):
            for dname, active, body in (("Edit", True, {"PreserveChanges": True}),
                                        ("Activate", False, {}),
                                        ("Prepare", False, {})):
                if v2:
                    fi = e.get("v2Draft", {}).get(dname) or ent + dname
                    request("%s - Draft %s" % (ent, dname), "POST", root + "/" + fi,
                            fmt + key_query(spec, e, active))
                else:
                    op = "draftPrepare" if dname == "Prepare" else dname
                    request("%s - Draft %s" % (ent, dname), "POST",
                            coll + (pred if active else draft_pred) + "/" + ns + "." + op, body=body)
            request("%s - Discard draft" % ent, "DELETE", coll + draft_pred, fmt)
        for a in e.get("actions", []):
            label = "Function" if a["kind"] == "function" else "Action"
            params = a.get("params")
            desc = [k for k in ("static", "factory") if a.get(k)]
            if params:
                desc.append("Parameters:\n" + "\n".join("- %s (%s)" % (p["name"], p["edm"]) for p in params))
            elif a.get("parameter"):
                desc.append("parameter structure %s: fields unknown, pass --metadata" % a["parameter"])
            if v2:
                fi = a.get("v2Name") or a["name"]
                q = fmt + ([] if a["static"] else key_query(spec, e, True))
                q += [(p["name"], payload.v2_url_literal(p["edm"])) for p in params or []]
                method = a.get("v2Method") or ("GET" if a["kind"] == "function" else "POST")
                if not a.get("v2Name"):
                    desc.append("V2 function import name not verified: pass --metadata.")
                request("%s - %s %s" % (ent, label, a["name"]), method, root + "/" + fi, q,
                        desc="\n".join(desc))
                continue
            url = (coll if a["static"] else coll + pred) + "/" + ns + "." + a["name"]
            if a["kind"] == "function":
                args = ",".join("%s=%s" % (p["name"], payload.v4_url_literal(p["edm"])) for p in params or [])
                request("%s - %s %s" % (ent, label, a["name"]), "GET", url + "(%s)" % args, desc="\n".join(desc))
            else:
                body = {p["name"]: payload.json_sample(p["edm"], v2) for p in params or []}
                request("%s - %s %s" % (ent, label, a["name"]), "POST", url, body=body, desc="\n".join(desc))

    return {
        "_type": "export", "__export_format": 4,
        "__export_date": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "__export_source": "rap-srvd-to-insomnia", "resources": resources,
    }


OVERRIDES = [("binding", "serviceBinding"), ("odata", "odataVersion"), ("binding_type", "bindingType"),
             ("service_version", "serviceVersion"), ("base_url", "baseUrl"), ("sap_client", "sapClient"),
             ("collection_name", "collectionName"), ("preview_url", "previewUrl")]
DEFAULTS = {"odataVersion": "v4", "bindingType": "ui", "serviceVersion": "0001"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--srvd", help="SRVD source file")
    ap.add_argument("--src-dir", help="directory with CDS (.ddls.asddls) / BDEF (.bdef.asbdef) sources")
    ap.add_argument("--cds", nargs="*", help="extra CDS source files")
    ap.add_argument("--bdef", nargs="*", help="extra BDEF source files")
    ap.add_argument("--metadata", help="the service's $metadata (EDMX file): exact types, keys, read-only "
                                       "fields and action parameters for the payloads")
    ap.add_argument("--collection-name", help="Insomnia collection name (default: binding name)")
    ap.add_argument("--binding", help="service binding name (default: SRVD name)")
    ap.add_argument("--odata", choices=["v2", "v4"], help="default v4")
    ap.add_argument("--binding-type", choices=["ui", "api"], help="ui (srvd) or api (srvd_a2x); default ui")
    ap.add_argument("--service-version", help="default 0001")
    ap.add_argument("--base-url", help="e.g. https://my-s4.example.com:44300")
    ap.add_argument("--sap-client", help="SAP client, e.g. 100")
    ap.add_argument("--preview-url", help="browser URL of the ADT service binding preview (copied once)")
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
    if args.metadata:
        apply_metadata(spec, edmx.parse_metadata(args.metadata), warnings)
    for field, default in DEFAULTS.items():
        if not spec.get(field):
            spec[field] = default
    if spec["odataVersion"] == "v2":
        for e in spec["entities"]:
            for f in e.get("fields", []) + [p for a in e.get("actions", []) for p in a.get("params") or []]:
                f["edm"] = to_v2_edm(f["edm"])

    for w in warnings:
        print("warning: " + w, file=sys.stderr)
    if args.dump_spec:
        with open(args.dump_spec, "w", encoding="utf-8") as fh:
            json.dump(spec, fh, indent=2, ensure_ascii=False)
        print("spec written: %s" % os.path.abspath(args.dump_spec), file=sys.stderr)
    if args.output:
        export = render(spec)
        errors = insomnia_check.check(export)
        if errors:
            for e in errors:
                print("error: " + e, file=sys.stderr)
            sys.exit("error: generated export failed the Insomnia format check, nothing written")
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(export, fh, indent=2, ensure_ascii=False)
        reqs = [r for r in export["resources"] if r["_type"] == "request"]
        folders = {r["_id"]: r["name"] for r in export["resources"] if r["_type"] == "request_group"}
        counts = ", ".join("%s %d" % (n, sum(1 for r in reqs if r["parentId"] == fid)) for fid, n in folders.items())
        print("insomnia export written: %s (%d requests: %s; format check ok)"
              % (os.path.abspath(args.output), len(reqs), counts), file=sys.stderr)
    if not args.output and not args.dump_spec:
        json.dump(spec, sys.stdout, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
