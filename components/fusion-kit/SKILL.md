---
name: reverse-fusion
description: Use local artifact analysis, evidence comparison, and optional task continuation when the user's goal benefits from them.
---
# Reverse Fusion

Start from the user's own words. Use ordinary host tools for ordinary work. Choose a specialized tool or method only when it answers a concrete question. Do not create task memory, follow a fixed order, or change the requested deliverable merely because this skill is present.

- For local artifact inspection and official Evidence, use the native tools advertised by the service. Read [how to keep and hand off official Evidence](references/rea-evidence.md) as needed. Export official evidence when another connection will need it; reconnecting alone does not restore Evidence IDs.
- For domain guidance, use `fusion_read_method` or open [the method index](references/domain-methods.md) and only the relevant references. These methods augment the native tools; they do not control access to them.
- For a requested implementation or behavior comparison, run independently prepared sides on the same input, fix demonstrated differences, then recheck affected and preserved behaviors. For trusted local command-line programs `fusion.py replay` runs a reviewed finite plan. The `comparison` method gives the local command path; see [independent checks](references/independent-build.md). For previously produced files `fusion_compare_outputs` compares bytes only.
- For a Flutter ARM64 library question, `fusion_observe_flutter_library` returns the owned class inventory separately from the official ELF evidence. Use `same_input: true` to link the observations; missing or conflicting identity is not corroboration. Even a valid match does not confirm runtime behavior. See [Flutter static observations](references/flutter-observations.md).
- If reliable host records are insufficient for a task that must resume later, optionally save a checkpoint and its supporting paths. When continuing in a new conversation, recover the original request and inspect the current artifacts before relying on old observations.

Keep the input identity, source, observed scope and unknowns with conclusions. Use the user's requested format. Never treat missing evidence, an installation check, or a matching pair of files as a claim of global equivalence.
