"""Request payloads for RAP OData services, typed by Edm type.

Field dicts (spec "fields"):
  {"name", "edm", "maxLength", "key", "mandatory", "readonly", "createOnly", "typed"}
readonly   -> never sent (computed, field(readonly), numbering managed)
createOnly -> sent on create, not on update (readonly : update, Core.Immutable)
"""
import json

# draft administration fields RAP adds to every draft-enabled entity
DRAFT_FIELDS = {"IsActiveEntity", "HasActiveEntity", "HasDraftEntity", "DraftEntityCreationDateTime",
                "DraftEntityLastChangeDateTime", "DraftAdministrativeData", "SiblingEntity"}

SAMPLE_DATE = "2026-01-01"
SAMPLE_EPOCH_MS = 1767225600000  # 2026-01-01T00:00:00Z
NULL_GUID = "00000000-0000-0000-0000-000000000000"

INT_TYPES = {"Edm.Byte", "Edm.SByte", "Edm.Int16", "Edm.Int32"}


def json_sample(edm, v2):
    """A value of the right JSON shape for the Edm type (V2 sends Int64/Decimal/Double as strings)."""
    edm = edm or "Edm.String"
    if edm == "Edm.Boolean":
        return False
    if edm in INT_TYPES:
        return 0
    if edm in ("Edm.Int64", "Edm.Decimal", "Edm.Double", "Edm.Single"):
        return "0" if v2 else 0
    if edm == "Edm.Guid":
        return NULL_GUID
    if edm == "Edm.Date":
        return SAMPLE_DATE
    if edm == "Edm.DateTime":  # V2 only
        return "/Date(%d)/" % SAMPLE_EPOCH_MS
    if edm == "Edm.DateTimeOffset":
        return "/Date(%d+0000)/" % SAMPLE_EPOCH_MS if v2 else SAMPLE_DATE + "T00:00:00Z"
    if edm == "Edm.TimeOfDay":
        return "00:00:00"
    if edm == "Edm.Time":  # V2 only
        return "PT00H00M00S"
    if edm == "Edm.Duration":
        return "PT0S"
    return ""


def v2_url_literal(edm, value=None):
    """OData V2 URI literal, e.g. for function import parameters."""
    edm = edm or "Edm.String"
    if edm == "Edm.Guid":
        return "guid'%s'" % (value or NULL_GUID)
    if edm == "Edm.Boolean":
        return value or "false"
    if edm in INT_TYPES:
        return value or "0"
    if edm == "Edm.Int64":
        return (value or "0") + "L"
    if edm == "Edm.Decimal":
        return (value or "0") + "M"
    if edm in ("Edm.Double", "Edm.Single"):
        return (value or "0") + "d"
    if edm == "Edm.DateTime":
        return "datetime'%s'" % (value or SAMPLE_DATE + "T00:00:00")
    if edm == "Edm.DateTimeOffset":
        return "datetimeoffset'%s'" % (value or SAMPLE_DATE + "T00:00:00Z")
    if edm == "Edm.Time":
        return "time'%s'" % (value or "PT00H00M00S")
    return "'%s'" % (value if value is not None else "")


def v4_url_literal(edm):
    """OData V4 URI literal for function parameters: strings quoted, everything else bare."""
    value = json_sample(edm, v2=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str) and edm not in ("Edm.Guid", "Edm.Date", "Edm.DateTimeOffset", "Edm.TimeOfDay",
                                               "Edm.Duration"):
        return "'%s'" % value
    return str(value)


def _sendable(f, for_update):
    if f["name"] in DRAFT_FIELDS or f.get("readonly"):
        return False
    if for_update and (f.get("key") or f.get("createOnly")):
        return False
    return True


def _ordered(fields):
    # mandatory fields first, then source order
    return sorted(fields, key=lambda f: not f.get("mandatory"))


def body_dict(entity, v2, for_update=False, exclude=(), key_value=None):
    body = {}
    for f in _ordered(entity.get("fields", [])):
        if f["name"] in exclude or not _sendable(f, for_update):
            continue
        if f.get("key") and key_value and f.get("edm", "Edm.String") == "Edm.String":
            # string keys come from the environment; the tag sits inside a JSON string, so the
            # body stays valid JSON
            body[f["name"]] = key_value(f)
        else:
            body[f["name"]] = json_sample(f.get("edm"), v2)
    return body


def dumps(body):
    return json.dumps(body, indent=2, ensure_ascii=False)


def field_guide(entity, for_update=False, exclude=()):
    lines = []
    for f in _ordered(entity.get("fields", [])):
        if f["name"] in exclude or not _sendable(f, for_update):
            continue
        info = [f.get("edm") or "Edm.String"]
        if f.get("maxLength"):
            info.append("max %s" % f["maxLength"])
        if f.get("mandatory"):
            info.append("mandatory")
        if not f.get("typed", True):
            info.append("type guessed")
        lines.append("- %s (%s)" % (f["name"], ", ".join(info)))
    skipped = [f["name"] for f in entity.get("fields", [])
               if f["name"] not in DRAFT_FIELDS and f["name"] not in exclude and not _sendable(f, for_update)]
    text = "Fields:\n" + "\n".join(lines) if lines else "No field information: add fields to the body."
    if skipped:
        text += "\nNot sent (read-only%s): %s" % (" or create-only" if for_update else "", ", ".join(skipped))
    return text
