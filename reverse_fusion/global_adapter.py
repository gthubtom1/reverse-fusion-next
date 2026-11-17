"""Install the small Codex adapter that points to this checkout.

The repository owns the router and domain material.  The user-level adapter is
only a pointer and a trigger rule, so unrelated project files remain in the
workspace where the user opened them.
"""

from __future__ import annotations

from pathlib import Path
from hashlib import sha256
import json
import os
import re

from .file_updates import atomic_write, file_transaction


MARKER_START = "<!-- reverse-fusion:begin -->"
MARKER_END = "<!-- reverse-fusion:end -->"
LEGACY_HEADER = "# Global Codex guidance"
SKILL_MARKER = "# Reverse Fusion cross-project adapter"
ADAPTER_STATE = b"<!-- reverse-fusion:adapter-state "


def adapter_paths(home: Path | None = None) -> dict[str, Path]:
    root = (home or Path.home()).expanduser()
    codex_root = (Path(os.environ['CODEX_HOME']).expanduser()
                  if home is None and os.environ.get('CODEX_HOME') else root / '.codex')
    return {
        "skill": root / ".agents" / "skills" / "reverse-fusion" / "SKILL.md",
        "agents": codex_root / "AGENTS.md",
    }


def _repo_display(repo_root: Path) -> str:
    return repo_root.resolve().as_posix()


def skill_text(repo_root: Path) -> str:
    repo = _repo_display(repo_root)
    return f"""---
name: reverse-fusion
description: Use Reverse Fusion for requests such as 分析这个软件然后复刻, 看懂APK, 照着网站做一样的, reverse engineering, protected/obfuscated binaries, protocol or behavior reconstruction, specialist security analysis/forensics, or explicit Reverse Fusion requests. Route through the shared repository and preserve the user goal across analysis and implementation.
---

# Reverse Fusion cross-project adapter

Use this skill for plain requests to analyze/recreate a supplied target, specialist security analysis/forensics, or when the current task involves reverse engineering, protected or obfuscated software, APK/DEX, PE/.NET, JavaScript/WASM, protocol reconstruction, behavior equivalence, or when the user explicitly asks to use Reverse Fusion.

The canonical checkout is `{repo}`. Keep the user's current project as the working project. Do not copy Reverse Fusion's entire `skills/` tree into the current project and do not write project output into the Reverse Fusion checkout unless the task is specifically about maintaining Reverse Fusion.

First read [the agent workflow]({repo}/docs/AGENT-WORKFLOW.md). Plain user language is sufficient: preserve the original delivery objective, start an unidentified recreation request with analysis, refine methods from actual evidence, and ask concrete product/operation questions only when needed. The user does not choose route IDs or component commands. Do not replace a whole-product goal with an unrequested demo or slice; keep unresolved dependencies and remaining work attached to that goal.

Before choosing a specialist workflow, verify the checkout and invoke its local router with the repository venv:

```text
Windows PowerShell: & "{repo}/.venv/Scripts/python.exe" -m reverse_fusion bridge --project-root "<current project absolute path>" --source local --case-root "work/current-case" --hint "<the user's original task>" --record --format json
POSIX: "{repo}/.venv/bin/python" -m reverse_fusion bridge --project-root "<current project absolute path>" --source local --case-root "work/current-case" --hint "<the user's original task>" --record --format json
```

Read `workflow.objective` and `workflow.user_request` separately from the current `workflow.stage`. A generic request to recreate a target starts with analysis; route selection is not implementation readiness. For a continuation, resume the existing case and carry forward the original objective rather than treating a short message as a new task. Read the returned `workflow`, `skill`, `required_reads`, `related_routes`, `next_stage`, `hard_target`, and `missing_support`. Read the returned local `SKILL.md` and required references before acting. If the task is ordinary software development without reverse or reconstruction intent, keep the normal host-native workflow and do not activate Reverse Fusion just because this skill exists.

Record the first original request before replacing it with a technical hint. Keep the returned case root for all refinements; its folder name can remain generic. If initial routing was read-only, supply `--user-request "<original user task>"` when first recording so the technical probe does not become the delivery objective. On continuation use the known case or let the bridge find the unique open case; do not create a fresh case by default.

Bridge returns `component_entries`: installed REA, official Spec and native Craft argument arrays, current-project cwd and recovery guides. Use those entries instead of guessing executable paths from old chats. To recover an existing case or inspect a frozen batch, run the same venv's `-m reverse_fusion workflow --project-root "<current project>"` with the known `--case-root` and optionally `--receipt`. This is read-only context resolution, not readiness or acceptance. Attach important existing project material through bridge `--ref "<project-relative file>"`; it remains in its original file.

For Codex, default deployment registers the official `reverse-fusion-rea` and original-engine `reverse-fusion-craft` MCP servers. Read `{repo}/docs/MCP-INTEGRATION.md` before choosing entry points. When using REA, read its installed official skill at `component_entries.rea.official_skill` and the relevant method/recovery reference from that same fixed package. Keep fusion as the case/deployment owner; do not run the standalone setup over it. Prefer the relevant existing MCP/provider tools; inspect actual schemas and readiness rather than writing another parser, decompiler or browser driver. Registration alone does not prove this chat loaded the tools: if missing, run mcp-check and report the required client reconnect. The returned CLI argv and bounded_argv restore the same saved provider paths as MCP. After preparing or moving a tool, run `providers --refresh` and mcp-check; path configuration alone is not successful analysis. A missing provider blocks affected operations while independent work continues.

Before Craft target analysis, invoke `component_entries.craft_mcp.case_bind`: `fusion_case_open` with the absolute current project and existing case directory. It opens the original Craft Project at `<case>/craft-analysis.cany`; rebind that case after restart, inspect restored records and any target-drift report, and use a new binding when switching cases. The shared tool checkout is not an implicit target project. Save REA's original Evidence bundle in the same outcome case before clearing/ending its investigation and import it when resuming; REA connection memory alone is not persistent progress. Craft MCP supplies original inspection/browser/device tools; formal candidate writes use the reviewed native-craft lease. Host reasoning/questions/permissions and native writer operations supply the mapped standalone orchestration roles; do not start a second AI/rebuild loop. Use absolute paths and preserve native records, actual errors and cleanup.

For requested images or 3D assets, use an available host media tool or Craft's `fusion_asset_generate` after case binding. The Craft entry invokes the original image/model producer with an explicit per-call budget and operation permission; its dedicated process-environment key is never a tool argument or saved receipt. Outputs stay in case asset staging for review, then enter the candidate through approved Spec/native commands. Read the asset section in MCP-INTEGRATION for actual dependencies; a local producer fixture is not paid-service execution, and an image tool does not provide 3D generation.

Use the returned REA bounded_argv for heavy calls when execution telemetry/cleanup is needed; read `docs/BOUNDED-REA.md`. For finite argv/stdin behavior comparison use component_entries.comparison and `docs/PROCESS-COMPARISON.md`, keeping UI/storage effects independently observed. Official Spec entry discovery supports the selected project's Codex, Pi or Claude layout. Read only current-stage documents, retain unchanged references and reuse saved operation schemas rather than repeatedly emitting entire manuals.

Read the shared `docs/RECOVERY.md` when tools fail, evidence is partial, a batch is interrupted or user input is missing. Before ending a turn with a question, continue independent useful work within the existing scope; a missing dependency blocks only the affected tasks. Ask only for the concrete human action, unavailable information or product decision that cannot be resolved autonomously. Do not treat a target's remaining unknowns as an unimplemented Reverse Fusion release or require extra user samples to install/use this edition.

For an abandoned or invalid frozen batch use the same lease's native-craft abort with a recorded reason; retain outputs and original commitments, then prepare a new reviewed batch when needed. Do not finish the observer without native cleanup. Native cleanup and finish bind actual candidate digests; changing a checked output requires replaying its frozen checks.

For analysis or reconstruction, read [the cross-project handoff guide]({repo}/docs/CROSS-PROJECT-WORKFLOW.md) before starting implementation. `required_read_paths` are absolute skill-checkout paths; cases, task files, candidate outputs and session receipts belong to `project_root`. Do not change cwd to the tool checkout to make a task command work. After identifying the real technology, refine the same case's domain route rather than staying on an initial generic route.

Reconstruction requires evidence-linked spec/tasks and review of critical dependencies, then run the installed official Spec Kit generated project workflow and `native-craft prepare --case-root "work/<case>" --handoff-manifest "<project-relative handoff>" --review-file "<project-relative semantic review>"` before candidate edits. Read `docs/NATIVE-COMPONENTS.md` in the shared checkout for the lease, native build/check/refine/summary/cleanup and additional session observer. Continue independent behavior validation. Pass the same `--project-root` on every task command and update the same recorded bridge after identifying the target. The handoff checker blocks declared critical unknowns; it cannot detect omitted licensing/state dependencies or prove semantic readiness. Do not silently remove an observed licensing dependency or redefine the delivery as a standalone local subset. Missing REA permits raw-tool analysis, but not fabricated native proof. Real REA, official Spec Kit and native Craft are required installed components. Current host reasoning supplies content to actual Craft engine tools; direct edits or the session observer do not substitute for Craft. Missing components mean incomplete deployment; maintain the repository-owned adapter/source patch when upstream has a demonstrated gap. A route pass is not execution of REA, Spec, Craft or Builder: report which parts actually ran.

Use `--mode analysis` while investigating; the bridge retains the reconstruction objective. After the readiness review, explicitly transition the same case with `--mode reconstruction` for the implementation/equivalence stage. Preserve `pass`, `fail`, `unknown`, `blocked`, and `unsupported` honestly. Do not select or download models, change host runtime configuration, start every provider, or claim target acceptance from route selection alone.

If the canonical checkout or its venv is missing, report that the shared adapter is unavailable and ask the user to restore or redeploy the checkout; do not silently clone or install a second copy in the user's project.
"""


def agents_block(repo_root: Path) -> str:
    repo = _repo_display(repo_root)
    return f"""{MARKER_START}
- When a task involves reverse engineering, protected or obfuscated software, APK/DEX, PE/.NET, JavaScript/WASM reverse work, protocol reconstruction, behavior equivalence, specialist security analysis or forensics, a plain request to analyze/recreate a supplied target, or an explicit request to use Reverse Fusion, use the user-level `reverse-fusion` skill before acting.
- Keep the current project directory as the work area. The Reverse Fusion checkout is a shared reference and router at `{repo}`; do not write unrelated project output there.
- Before large builds, tests, unpacking or comparison in any project, read `{repo}/docs/DISK-MANAGEMENT.md`. Classify generated output as persistent (keep), reusable (declare identity, inputs and next use) or disposable (complete to reclaim), using `rf_next_storage` with realistic byte budgets. At meaningful operation/verification ends, stage changes, resume or space pressure, use storage review; the host judges reusable keep/release with a reason. No per-command ritual or second model. Preserve original inputs, code, evidence and deliveries; complete only after all users stop. Persistent data never downgrades; active/protected/unregistered data is retained. Ordinary development remains host-native without a reverse case.
{MARKER_END}"""


def _check_markers(text: str) -> None:
    if (text.count(MARKER_START), text.count(MARKER_END)) not in {(0, 0), (1, 1)}:
        raise ValueError("Global AGENTS.md has incomplete or duplicate Reverse Fusion markers")
    if text.find(MARKER_END) >= 0 and text.find(MARKER_END) < text.find(MARKER_START):
        raise ValueError("Global AGENTS.md has reversed Reverse Fusion markers")


def _replace_agents_block(text: str, block: str) -> str:
    _check_markers(text)
    start = text.find(MARKER_START)
    end = text.find(MARKER_END)
    if start >= 0 and end >= start:
        end += len(MARKER_END)
        return text[:start] + block + text[end:]

    # Convert the adapter written by the first manual deployment into the
    # managed block without touching any unrelated user instructions.
    legacy = (
        f"{LEGACY_HEADER}\n\n"
        "- When a task involves reverse engineering, protected or obfuscated software, APK/DEX, PE/.NET, JavaScript/WASM reverse work, protocol reconstruction, behavior equivalence, or an explicit request to use Reverse Fusion, use the user-level `reverse-fusion` skill before acting.\n"
        "- Keep the current project directory as the work area. The Reverse Fusion checkout is a shared reference and router at `D:\\Project\\reverse`; do not write unrelated project output there.\n"
    )
    if legacy in text:
        text = text.replace(legacy, "")
    return (text + "\n\n" + block + "\n") if text else block + "\n"


def _agents_region(payload: bytes) -> dict | None:
    """Locate only our block; retain exact bytes outside its recorded appendage."""
    text = payload.decode('utf-8')
    _check_markers(text)
    start = payload.find(MARKER_START.encode('ascii'))
    count = payload.count(ADAPTER_STATE)
    if start < 0:
        if count:
            raise ValueError('Global AGENTS.md has adapter metadata without its block')
        return None
    end = payload.index(MARKER_END.encode('ascii'), start) + len(MARKER_END)
    block = payload[start:end]
    if not count:
        return {'start': start, 'end': end, 'block': block, 'metadata': None}
    if count != 1:
        raise ValueError('Global AGENTS.md has duplicate adapter metadata')
    metadata_start = payload.index(ADAPTER_STATE)
    match = re.match(rb'<!-- reverse-fusion:adapter-state ([^\r\n]*) -->\r?\n', payload[metadata_start:])
    if match is None or metadata_start + match.end() != start:
        raise ValueError('Global AGENTS.md adapter metadata is not adjacent to its block')
    try:
        metadata = json.loads(match[1].decode('ascii'))
        if (set(metadata) != {'schema_version', 'repository', 'separator', 'trailing',
                              'original_existed', 'block_sha256'}
                or metadata['schema_version'] != 1
                or not isinstance(metadata['repository'], str)
                or not Path(metadata['repository']).is_absolute()
                or type(metadata['original_existed']) is not bool
                or not re.fullmatch('[a-f0-9]{64}', metadata['block_sha256'])):
            raise ValueError('Invalid global adapter metadata')
        separator = bytes.fromhex(metadata['separator'])
        trailing = bytes.fromhex(metadata['trailing'])
        if separator not in (b'', b'\n', b'\n\n', b'\r\n', b'\r\n\r\n') or trailing not in (b'', b'\n', b'\r\n'):
            raise ValueError('Invalid global adapter separators')
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise ValueError('Global AGENTS.md adapter metadata is malformed; preserve it for review') from exc
    # A user's editor may convert the whole file's newline convention. Match
    # only the recorded newline count in either spelling; keep all other bytes.
    variants = lambda value: tuple(dict.fromkeys((value, value.replace(b'\r\n', b'\n'),
                                                 value.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))))
    actual_separator = next((value for value in variants(separator)
                             if metadata_start >= len(value) and payload[metadata_start-len(value):metadata_start] == value), None)
    actual_trailing = next((value for value in variants(trailing) if payload[end:end+len(value)] == value), None)
    if actual_separator is None or actual_trailing is None:
        raise ValueError('Global AGENTS.md adapter separators changed; preserve it for review')
    return {'start': metadata_start-len(actual_separator), 'end': end+len(actual_trailing),
            'block': block, 'metadata': metadata, 'separator': actual_separator, 'trailing': actual_trailing}


def _agents_digest(block: bytes) -> str:
    return sha256(block.replace(b'\r\n', b'\n')).hexdigest()


def _updated_agents(payload: bytes, block: str, repo: Path, *, original_existed: bool) -> bytes:
    region = _agents_region(payload)
    newline = b'\r\n' if b'\r\n' in payload else b'\n'
    encoded = block.replace('\n', newline.decode('ascii')).encode('utf-8')
    if region and region['metadata']:
        previous = region['metadata']
        if _agents_digest(region['block']) != previous['block_sha256']:
            raise ValueError('Global AGENTS.md managed instructions changed; preserve them for review')
        separator, trailing = region['separator'], region['trailing']
        original_existed = previous['original_existed']
    else:
        # Old markers have no appendage identity: only replace their exact
        # region, never infer or strip adjacent whitespace owned by the user.
        separator = b'' if region or not payload else newline * 2
        trailing = b'' if region else newline
    metadata = {'schema_version': 1, 'repository': str(repo.resolve()),
                'separator': separator.hex(), 'trailing': trailing.hex(),
                'original_existed': original_existed, 'block_sha256': _agents_digest(encoded)}
    header = ADAPTER_STATE + json.dumps(metadata, ensure_ascii=True, separators=(',', ':')).encode('ascii') + b' -->' + newline
    replacement = separator + header + encoded + trailing
    return payload[:region['start']] + replacement + payload[region['end']:] if region else payload + replacement


def _block_repository(block: bytes) -> Path | None:
    match = re.search(r'shared reference and router at `([^`]+)`', block.decode('utf-8'))
    if match is None or not Path(match[1]).is_absolute():
        return None
    return Path(match[1]).resolve()


def install_global_adapter(repo_root: Path, home: Path | None = None) -> dict[str, object]:
    repo = repo_root.resolve()
    paths = adapter_paths(home)
    if paths["skill"].is_file():
        existing_skill = paths["skill"].read_text(encoding="utf-8")
        if SKILL_MARKER not in existing_skill:
            raise ValueError(f"Existing user skill is not managed by Reverse Fusion: {paths['skill']}")
    existing = paths["agents"].read_bytes() if paths["agents"].is_file() else b''
    updated = _updated_agents(existing, agents_block(repo), repo, original_existed=paths['agents'].is_file())
    paths["skill"].parent.mkdir(parents=True, exist_ok=True)
    paths["agents"].parent.mkdir(parents=True, exist_ok=True)
    with file_transaction(paths.values()):
        atomic_write(paths['skill'], skill_text(repo).encode('utf-8'))
        atomic_write(paths['agents'], updated)
    return {
        "enabled": True,
        "skill": str(paths["skill"]),
        "agents": str(paths["agents"]),
        "repository": str(repo),
    }


def remove_global_adapter(home: Path | None = None, *, repo_root: Path | None = None) -> dict[str, object]:
    paths = adapter_paths(home)
    payload = paths['agents'].read_bytes() if paths['agents'].is_file() else b''
    region = _agents_region(payload)
    selected = repo_root.resolve() if repo_root is not None else None
    removed: list[str] = []
    retained: list[str] = []
    remove_agents = False
    if region is None and selected is not None:
        spelling = payload.decode('utf-8').replace('\\', '/')
        reference = _repo_display(selected)
        if os.name == 'nt':
            spelling, reference = spelling.casefold(), reference.casefold()
        if reference in spelling:
            raise ValueError('Unmanaged global instructions still refer to this checkout; retain runtime for review')
    if region:
        owner = _block_repository(region['block'])
        metadata = region['metadata']
        if metadata and owner != Path(metadata['repository']).resolve():
            raise ValueError('Global AGENTS.md owner and instructions disagree; retain the runtime for review')
        if owner is None:
            raise ValueError('Global AGENTS.md ownership is unknown; retain the runtime for review')
        if selected is not None and owner != selected:
            retained.append('another checkout owns the global instructions')
        else:
            unchanged = (_agents_digest(region['block']) == metadata['block_sha256'] if metadata else
                         region['block'].decode('utf-8').replace('\r\n', '\n') == agents_block(owner))
            if not unchanged:
                raise ValueError('Global AGENTS.md managed instructions changed; retain the runtime for review')
            remove_agents = True
    remove_skill = False
    if paths["skill"].is_file():
        text = paths["skill"].read_text(encoding="utf-8")
        match = re.search(r'The canonical checkout is `([^`]+)`\.', text)
        if SKILL_MARKER in text:
            if match is None or not Path(match[1]).is_absolute():
                raise ValueError('Global skill ownership is unknown; retain the runtime for review')
            if selected is None or Path(match[1]).resolve() == selected:
                remove_skill = True
            else:
                retained.append('another checkout owns the global skill')
        elif selected is not None:
            raise ValueError('Global skill ownership is unmanaged; retain runtime for review')
    with file_transaction(paths.values()):
        if remove_skill:
            paths['skill'].unlink()
            removed.append(str(paths['skill']))
        if remove_agents:
            updated = payload[:region['start']] + payload[region['end']:]
            original_existed = region['metadata']['original_existed'] if region['metadata'] else True
            if not updated and not original_existed:
                paths['agents'].unlink()
            else:
                atomic_write(paths['agents'], updated)
            removed.append(str(paths['agents']))
    return {"enabled": False, "removed": removed, **({'retained': retained} if retained else {})}
