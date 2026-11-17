"""Repository-owned, portable Reverse router.

The upstream reverse-skill routing semantics are kept as a versioned data file
next to this module.  The router is intentionally small: it scores declarative
``must``/``mustAll``/``exclude`` rules, resolves ties with the declared
priority list, and returns a local route descriptor.  It has no provider,
credential, model, or receipt dependency.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any


ROOT = Path(__file__).resolve().parent
ROUTING_FILE = ROOT / "routing.json"
LOCAL_ROUTE_DIR = ROOT / "routes"


@dataclass(frozen=True)
class LocalRoute:
    status: str
    source: str
    hint: str
    primary_id: str
    primary: str
    label: str
    confidence: str
    matches: tuple[str, ...]
    notes: tuple[str, ...]
    routing_sha256: str
    skill: str
    skill_available: bool
    hard_target: bool
    required_reads: tuple[str, ...]
    missing_support: tuple[str, ...]
    related_routes: tuple[dict[str, Any], ...] = ()
    next_stage: dict[str, Any] | None = None
    method_reads: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source": self.source,
            "hint": self.hint,
            "primary_id": self.primary_id,
            "primary": self.primary,
            "label": self.label,
            "confidence": self.confidence,
            "matches": list(self.matches),
            "notes": list(self.notes),
            "routing_sha256": self.routing_sha256,
            "skill": self.skill,
            "skill_available": self.skill_available,
            "hard_target": self.hard_target,
            "required_reads": list(self.required_reads),
            "method_reads": list(self.method_reads),
            "missing_support": list(self.missing_support),
            "related_routes": list(self.related_routes),
            "next_stage": self.next_stage,
        }


def runtime_context(route_id: str, hint: str, skill: str, *, methods=False) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
    """Return the short contract, or on-demand technical method hints.

    This read-only route is not a stage controller or an execution recipe.
    """
    repo = ROOT.parent.parent
    runtime_file = ROOT / "runtime.json"
    if not runtime_file.is_file():
        return False, (skill,), ("components/reverse-core/runtime.json",)
    data = json.loads(runtime_file.read_text(encoding="utf-8"))
    try:
        if data["schema_version"] != 1:
            raise ValueError("local runtime context version mismatch")
        hard = data["hard_target"]
        difficult = bool(re.search(hard["pattern"], hint, flags=re.IGNORECASE))
        groups = [data["base_reads"], [skill], data["route_reads"].get(route_id, [])]
        if difficult:
            groups.extend([hard["common_reads"], hard["route_reads"].get(route_id, [])])
        if data.get('method_loading') == 'on-demand' and not methods:
            groups = [data['base_reads']]
        reads: list[str] = []
        for group in groups:
            if not isinstance(group, list) or any(not isinstance(item, str) for item in group):
                raise ValueError("local runtime reads must be lists of relative paths")
            reads.extend(group)
    except (KeyError, TypeError, re.error) as exc:
        raise ValueError(f"invalid local runtime context: {exc}") from exc
    required = tuple(dict.fromkeys(reads))
    missing = []
    for name in required:
        path = repo / name
        if (PureWindowsPath(name).is_absolute() or Path(name).is_absolute()
                or ".." in PureWindowsPath(name).parts
                or not path.resolve().is_relative_to(repo.resolve())):
            raise ValueError("local runtime resource escapes repository")
        if not path.is_file():
            missing.append(name)
    return difficult, required, tuple(missing)


def _load() -> tuple[dict[str, Any], str]:
    payload = ROUTING_FILE.read_bytes()
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("routes"), dict):
        raise ValueError("local routing manifest is malformed")
    priority = data.get("priority")
    if not isinstance(priority, list) or not priority:
        raise ValueError("local routing priority is missing")
    route_ids = set(data["routes"])
    if set(priority) != route_ids:
        raise ValueError("local routing routes and priority diverge")
    fallback = data.get("meta", {}).get("fallbackId")
    if fallback not in route_ids:
        raise ValueError("local routing fallback is missing")
    return data, hashlib.sha256(payload).hexdigest()


def _hit(text: str, rule: dict[str, Any]) -> bool:
    pattern = rule.get("must")
    if not isinstance(pattern, str) or not re.search(pattern, text, flags=re.IGNORECASE):
        return False
    must_all = rule.get("mustAll", [])
    if any(not re.search(item, text, flags=re.IGNORECASE) for item in must_all):
        return False
    exclude = rule.get("exclude")
    if isinstance(exclude, str) and re.search(exclude, text, flags=re.IGNORECASE):
        return False
    return True


def _descriptor(route_id: str, route: dict[str, Any]) -> str:
    descriptor = LOCAL_ROUTE_DIR / f"{route_id}.md"
    if descriptor.is_file():
        return str(descriptor.relative_to(ROOT.parent.parent)).replace("\\", "/")
    # A descriptor is part of the repository contract.  Returning the stable
    # path still lets callers report a missing local capability explicitly.
    return str(descriptor.relative_to(ROOT.parent.parent)).replace("\\", "/")


def _local_skill(route: dict[str, Any]) -> tuple[str, bool]:
    skill = route.get("skill")
    if not isinstance(skill, str) or not skill:
        return "", False
    path = ROOT.parent.parent / "skills" / skill
    return f"skills/{skill}", path.is_file()


def route(hint: str, *, primary: str | None = None) -> LocalRoute:
    """Resolve a hint without reading any external installation state."""
    data, digest = _load()
    text = (hint or "").lower()
    # Technical acronyms next to Chinese characters are still separate terms.
    # Python Unicode \b otherwise treats "这个APK" as one word and misses APK.
    text = re.sub(r'(?<=[\u3400-\u9fff])(?=[a-z0-9])|(?<=[a-z0-9])(?=[\u3400-\u9fff])', ' ', text)
    scores: dict[str, int] = {}
    notes: list[str] = []
    for route_id, route_data in data["routes"].items():
        for rule in route_data.get("keywords", []):
            if _hit(text, rule):
                scores[route_id] = scores.get(route_id, 0) + 1

    route_ids = set(data["routes"])
    if primary:
        if primary not in route_ids:
            raise ValueError(f"explicit primary id '{primary}' is not in local routing")
        selected = primary
        confidence = "explicit"
        notes.append("Explicit primary override; automatic keyword scoring was not used for PRIMARY.")
    else:
        selected = None
        max_score = -1
        for item in data["priority"]:
            if item in scores and scores[item] > max_score:
                selected = item
                max_score = scores[item]
        if selected is None:
            selected = data["meta"]["fallbackId"]
            confidence = "low"
            notes.append("No strong keyword hit; the generic reverse route remains the owner.")
        else:
            confidence = "high" if len(scores) == 1 else "medium"

    # A bare request to recreate an unidentified target is a delivery objective,
    # not evidence that the reconstruction implementation stage is ready.
    # Keep explicit R46 and existing-implementation verification workflows.
    if (not primary and selected == 'R46'
            and re.search(r'复刻|仿制|reconstruct|replica|re-?implement', text, re.I)
            and not re.search(r'已确认|已审查|验收|验证|追版|回归|reviewed|verification|equivalence|(?:reconstruction|replica)\s+implementation|verify.{0,12}existing|existing.{0,12}verif|upstream.{0,6}update', text, re.I)):
        domains = [item for item in data['priority'] if item != 'R46' and item in scores]
        selected = max(domains, key=lambda item: scores[item]) if domains else data['meta']['fallbackId']
        notes.append('Reconstruction intent starts with domain analysis; refine the domain from actual artifacts before R46 implementation.')

    selected_data = data["routes"][selected]
    descriptor = _descriptor(selected, selected_data)
    skill, skill_available = _local_skill(selected_data)
    if not (LOCAL_ROUTE_DIR / f"{selected}.md").is_file():
        notes.append("Local route descriptor is missing.")
    if not skill_available:
        notes.append("Local domain skill is missing.")
    difficult, required_reads, missing_support = runtime_context(selected, hint, skill)
    related: list[dict[str, Any]] = []
    for route_id in data["priority"]:
        if route_id == selected or route_id not in scores:
            continue
        candidate_data = data["routes"][route_id]
        candidate_skill, candidate_available = _local_skill(candidate_data)
        candidate_difficult, candidate_reads, candidate_missing = runtime_context(route_id, hint, candidate_skill)
        related.append({
            "id": route_id,
            "label": candidate_data.get("label"),
            "descriptor": _descriptor(route_id, candidate_data),
            "skill": candidate_skill,
            "skill_available": candidate_available,
            "hard_target": candidate_difficult,
            "required_reads": list(candidate_reads),
            "missing_support": list(candidate_missing),
            "activation": "explicit-secondary-route",
        })
    next_stage = None
    if selected != "R46" and ("R46" in scores or re.search(r"复刻|仿制|照着.{0,10}(?:做|开发)|做(?:个|一[个份套])?.{0,8}一(?:模一样|样)|reconstruct|replica|re-?implement|behavio[u]?r.?equivalence", text, flags=re.IGNORECASE)):
        recon = data["routes"]["R46"]
        recon_skill, recon_available = _local_skill(recon)
        _, recon_reads, recon_missing = runtime_context("R46", hint, recon_skill)
        next_stage = {
            "id": "R46",
            "label": recon.get("label"),
            "skill": recon_skill,
            "skill_available": recon_available,
            "required_reads": list(recon_reads),
            "missing_support": list(recon_missing),
            "activation": "explicit-second-stage",
            "hint": "reconstruction stage for the reviewed target behavior",
        }
    if missing_support:
        notes.append("Local runtime supporting resources are missing.")
    if not text:
        status = "blocked"
    else:
        status = "local-route-pass" if (LOCAL_ROUTE_DIR / f"{selected}.md").is_file() and skill_available and not missing_support else "unavailable"
    if not text:
        notes.append("Empty hint; provide task text before acting on the route.")
    return LocalRoute(
        status=status,
        source="local",
        hint=hint,
        primary_id=selected,
        primary=descriptor,
        label=selected_data["label"],
        confidence=confidence,
        matches=tuple(item for item in data["priority"] if item in scores),
        notes=tuple(notes),
        routing_sha256=digest,
        skill=skill,
        skill_available=skill_available,
        hard_target=difficult,
        required_reads=required_reads,
        missing_support=missing_support,
        related_routes=tuple(related),
        next_stage=next_stage,
        method_reads=runtime_context(selected, hint, skill, methods=True)[1],
    )

