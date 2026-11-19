"""Edit one named MCP registration while preserving the rest of a host file."""
import json
from pathlib import Path
import re
import tomllib


def release_profile():
    marker = Path(__file__).with_name("field-release.json")
    if not marker.is_file():
        return "reverse-fusion-review"
    if json.loads(marker.read_bytes()).get("profile") != "reverse-fusion-field":
        raise ValueError("Unrecognized release profile")
    return "reverse-fusion-field"


NAME = release_profile()
_STRING = r'"(?:[^"\\]|\\.)*"'
_SPACE = re.compile(r"\s*")
_COMMENTS = re.compile(_STRING + r"|//[^\r\n]*|/\*.*?\*/", re.S)
_TRAILING = re.compile(_STRING + r"|,(?=\s*[}\]])")
_DECODER = json.JSONDecoder()


def _unique(pairs):
    values = {}
    for key, value in pairs:
        if key in values:
            raise ValueError("Duplicate configuration key; resolve it before installing.")
        values[key] = value
    return values


def _mask_comment(match):
    token = match[0]
    return token if token.startswith('"') else " " * len(token)


def _json_object(text, comments):
    """Mask JSONC extensions without moving the offsets used for surgical edits."""
    plain = text
    if comments:
        plain = _COMMENTS.sub(_mask_comment, text)
        def trailing(match):
            if match[0] != "," or plain[:match.start()].rstrip()[-1:] in ("{", "[", ",", ""):
                return match[0]
            return " "
        plain = _TRAILING.sub(trailing, plain)
    value = json.loads(plain, object_pairs_hook=_unique)
    if not isinstance(value, dict):
        raise ValueError("Host configuration must be an object.")
    return plain, value


def has_registration(host, payload, *, name=NAME):
    """Look up just the reserved server name, independent of current command or owner."""
    if payload is None:
        return False
    text = payload.decode("utf-8-sig")
    if host == "codex":
        registry = tomllib.loads(text).get("mcp_servers", {})
    else:
        _, data = _json_object(text, comments=host == "opencode")
        registry = data.get("mcp" if host == "opencode" else "mcpServers", {})
    if not isinstance(registry, dict):
        raise ValueError("The host service registry is not an object.")
    if name in registry:
        return True
    if host == "opencode":
        nested = registry.get("servers", {})
        return isinstance(nested, dict) and name in nested
    return False


def _fields(plain, opening):
    """Return key start and value bounds in an already validated JSON object."""
    result = {}
    pos = _SPACE.match(plain, opening + 1).end()
    while plain[pos] != "}":
        key, end = _DECODER.raw_decode(plain, pos)
        start = _SPACE.match(plain, _SPACE.match(plain, end).end() + 1).end()
        _, stop = _DECODER.raw_decode(plain, start)
        result[key] = (pos, start, stop)
        pos = _SPACE.match(plain, stop).end()
        if plain[pos] == ",":
            pos = _SPACE.match(plain, pos + 1).end()
    return result


def _remove_field(text, plain, fields, key):
    start, _, end = fields[key]
    after = _SPACE.match(plain, end).end()
    if plain[after] == ",":
        return text[:start] + text[end:after] + text[after + 1:]
    trailing = _COMMENTS.sub(_mask_comment, text[end:after]).find(",")
    if trailing >= 0:
        comma = end + trailing
        return text[:start] + text[end:comma] + text[comma + 1:]
    before = len(plain[:start].rstrip()) - 1
    if plain[before] == ",":
        return text[:before] + text[before + 1:start] + text[end:]
    return text[:start] + text[end:]


def _json_update(text, group, entry, receipt, remove, comments, *, parent=None, name=NAME):
    plain, data = _json_object(text, comments)
    opening = _SPACE.match(plain).end()
    groups = (parent, group) if parent else (group,)
    scopes = [(opening, data)]
    for key in groups:
        at, members = scopes[-1]
        if key not in members:
            break
        if not isinstance(members[key], dict):
            raise ValueError(f"Host configuration member {key} must be an object.")
        if parent and key == parent and name in members[key]:
            raise ValueError(f"An unrelated OpenCode 1.x {name} registration already exists.")
        scopes.append((_fields(plain, at)[key][1], members[key]))
    depth = len(scopes) - 1
    at, members = scopes[-1]
    if depth == len(groups) and name in members:
        if receipt is None or members[name] != entry:
            raise ValueError(f"An unrelated or edited {name} registration already exists.")
        if not remove:
            return text, receipt
        key = name
        owned_depth = 0 if receipt.get("created_parent") else len(groups) - int(receipt["created_group"])
        while depth > owned_depth and len(members) == 1:
            depth -= 1
            key = groups[depth]
            at, members = scopes[depth]
        fragment = receipt["inserted"]
        del members[key]
        if text.startswith(fragment, at + 1):
            updated = text[:at + 1] + text[at + 1 + len(fragment):]
            try:
                if _json_object(updated, comments)[1] == data:
                    return updated, receipt
            except ValueError:
                pass
        updated = _remove_field(text, plain, _fields(plain, at), key)
        if _json_object(updated, comments)[1] == data:
            return updated, receipt
        raise ValueError("The current configuration cannot be edited at its original location.")
    if remove:
        return text, receipt
    key, value = name, entry
    for container in reversed(groups[depth:]):
        key, value = container, {key: value}
    newline = "\r\n" if "\r\n" in text else "\n"
    fragment = newline + "  " + json.dumps(key) + ": " + json.dumps(value, ensure_ascii=True)
    if members:
        fragment += ","
    updated = text[:at + 1] + fragment + text[at + 1:]
    _json_object(updated, comments)
    record = {"created_group": depth < len(groups), "inserted": fragment}
    if parent and depth == 0:
        record["created_parent"] = True
    return updated, record


def _toml_update(text, entry, receipt, remove, *, name=NAME):
    registry = tomllib.loads(text).get("mcp_servers", {})
    if not isinstance(registry, dict):
        raise ValueError("Codex mcp_servers must be a table.")
    if name in registry:
        if receipt is None or registry[name] != entry:
            raise ValueError(f"An unrelated or edited {name} registration already exists.")
        if not remove:
            return text, receipt
        fragment = receipt["inserted"]
        if text.count(fragment) != 1:
            raise ValueError(f"Codex reformatted this registration. Run `codex mcp remove {name}`, then retry removal.")
        updated = text.replace(fragment, "", 1)
        after = tomllib.loads(updated).get("mcp_servers", {})
        if name in after or after != {k: v for k, v in registry.items() if k != name}:
            raise ValueError("Codex configuration changed near the installed registration.")
        return updated, receipt
    if remove:
        return text, receipt
    newline = "\r\n" if "\r\n" in text else "\n"
    block = [f"[mcp_servers.{name}]", "command = " + json.dumps(entry["command"], ensure_ascii=False),
             "args = " + json.dumps(entry["args"], ensure_ascii=False)]
    fragment = (newline if text and not text.endswith("\n") else "") + newline.join(block) + newline
    updated = text + fragment
    if tomllib.loads(updated)["mcp_servers"][name] != entry:
        raise ValueError("Codex did not round-trip the requested paths.")
    return updated, {"inserted": fragment}


def update(host, payload, command, receipt=None, *, remove=False, opencode_version=1, name=NAME):
    """Return proposed bytes and metadata containing only our own insertion."""
    has_bom = payload is not None and payload.startswith(b"\xef\xbb\xbf")
    text = payload.decode("utf-8-sig") if payload is not None else ("" if host == "codex" else "{}\n")
    if host == "opencode":
        entry = {"type": "local", "command": command}
        if opencode_version == 2:
            text, record = _json_update(text, "servers", entry, receipt, remove, True, parent="mcp", name=name)
        else:
            entry["enabled"] = True
            text, record = _json_update(text, "mcp", entry, receipt, remove, True, name=name)
    else:
        entry = {"command": command[0], "args": command[1:]}
        if host == "pi":
            text, record = _json_update(text, "mcpServers", entry, receipt, remove, False, name=name)
        else:
            text, record = _toml_update(text, entry, receipt, remove, name=name)
    if remove and (payload is None or (receipt["created_file"] and text in ("", "{}\n"))):
        return None, record
    record = dict(record, created_file=receipt["created_file"] if receipt else payload is None)
    return text.encode("utf-8-sig" if has_bom else "utf-8"), record
