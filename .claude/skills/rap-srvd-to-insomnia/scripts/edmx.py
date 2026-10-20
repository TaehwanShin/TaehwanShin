"""Parse an OData $metadata document (EDMX, V4 or V2) into the facts the generator needs.

Result:
  {"version": "v4" | "v2",
   "entitySets": {set: {"type": type, "keys": [..],
                        "props": {name: {"edm", "maxLength", "nullable", "computed", "immutable",
                                         "mandatory", "creatable", "updatable"}},
                        "navs": {name: target_set_or_None}}},
   "operations": [{"name", "kind": "action" | "function", "boundSet", "collection",
                   "params": [{"name", "edm", "maxLength"}], "httpMethod"}]}
"""
import xml.etree.ElementTree as ET


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _attr(el, name):
    for k, v in el.attrib.items():
        if k == name or k.endswith("}" + name):
            return v
    return None


def _children(el, name):
    return [c for c in el if _local(c.tag) == name]


def _short(qualified):
    """'Collection(SAP__self.TravelType)' -> 'TravelType'."""
    if not qualified:
        return None
    q = qualified
    if q.startswith("Collection(") and q.endswith(")"):
        q = q[len("Collection("):-1]
    return q.rsplit(".", 1)[-1]


def _truthy(el):
    b = el.get("Bool")
    return b is None or b.lower() == "true"


def parse_metadata(path):
    root = ET.parse(path).getroot()
    v2 = root.get("Version") != "4.0"
    types, sets, ops = {}, {}, []
    terms = {}  # "TypeName/Prop" -> {"computed", "immutable", "mandatory"}
    assoc_ends = {}  # V2: (association, role) -> entity type

    schemas = [el for el in root.iter() if _local(el.tag) == "Schema"]
    for schema in schemas:
        for el in schema:
            kind = _local(el.tag)
            if kind == "EntityType":
                keys = [r.get("Name") for k in _children(el, "Key") for r in _children(k, "PropertyRef")]
                props = {}
                for p in _children(el, "Property"):
                    props[p.get("Name")] = {
                        "edm": p.get("Type"),
                        "maxLength": p.get("MaxLength"),
                        "nullable": p.get("Nullable", "true").lower() != "false",
                        "creatable": (_attr(p, "creatable") or "true").lower() != "false",
                        "updatable": (_attr(p, "updatable") or "true").lower() != "false",
                    }
                navs = {}
                for n in _children(el, "NavigationProperty"):
                    navs[n.get("Name")] = {"type": _short(n.get("Type")),
                                           "rel": n.get("Relationship"), "to": n.get("ToRole")}
                types[el.get("Name")] = {"keys": keys, "props": props, "navs": navs}
            elif kind == "Association":
                for end in _children(el, "End"):
                    assoc_ends[(el.get("Name"), end.get("Role"))] = _short(end.get("Type"))
            elif kind in ("Action", "Function"):
                params = [{"name": p.get("Name"), "edm": p.get("Type"), "maxLength": p.get("MaxLength")}
                          for p in _children(el, "Parameter")]
                bound = el.get("IsBound", "false").lower() == "true"
                binding = params.pop(0) if bound and params else None
                ops.append({"name": el.get("Name"), "kind": kind.lower(),
                            "boundType": _short(binding["edm"]) if binding else None,
                            "collection": bool(binding and binding["edm"].startswith("Collection(")),
                            "params": params, "httpMethod": None})
            elif kind == "EntityContainer":
                for es in _children(el, "EntitySet"):
                    sets[es.get("Name")] = _short(es.get("EntityType"))
                for fi in _children(el, "FunctionImport"):
                    if not v2:
                        continue  # V4 imports only point at the unbound actions/functions above
                    params = [{"name": p.get("Name"), "edm": p.get("Type"), "maxLength": p.get("MaxLength")}
                              for p in _children(fi, "Parameter")]
                    method = (_attr(fi, "HttpMethod") or "POST").upper()
                    ops.append({"name": fi.get("Name"), "kind": "function" if method == "GET" else "action",
                                "boundType": _short(_attr(fi, "action-for")), "collection": False,
                                "params": params, "httpMethod": method})
            elif kind == "Annotations":
                target = el.get("Target") or ""
                if "/" not in target:
                    continue
                type_part, prop = target.split("/", 1)
                key = "%s/%s" % (_short(type_part), prop)
                t = terms.setdefault(key, {})
                for a in _children(el, "Annotation"):
                    term = (a.get("Term") or "").rsplit(".", 1)[-1]
                    if term in ("Computed", "Immutable") and _truthy(a):
                        t[term.lower()] = True
                    elif term == "FieldControl" and (a.get("EnumMember") or "").endswith("/Mandatory"):
                        t["mandatory"] = True

    for tname, t in types.items():
        for pname, p in t["props"].items():
            extra = terms.get("%s/%s" % (tname, pname), {})
            p["computed"] = extra.get("computed", False)
            p["immutable"] = extra.get("immutable", False)
            p["mandatory"] = extra.get("mandatory", False)

    type_to_set = {}
    for s, tname in sets.items():
        type_to_set.setdefault(tname, s)
    result_sets = {}
    for s, tname in sets.items():
        t = types.get(tname)
        if not t:
            continue
        navs = {}
        for n, nav in t["navs"].items():
            target_type = nav["type"] or assoc_ends.get((_short(nav["rel"]), nav["to"]))
            navs[n] = type_to_set.get(target_type)
        result_sets[s] = {"type": tname, "keys": t["keys"], "props": t["props"], "navs": navs}
    for op in ops:
        op["boundSet"] = type_to_set.get(op.pop("boundType"))
    return {"version": "v2" if v2 else "v4", "entitySets": result_sets, "operations": ops}
