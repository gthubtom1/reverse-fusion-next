# Keep official Evidence across conversations

REA tools return structured results. Read `normalized_result` for the observations and retain the original `evidence_id`, source, scope, limitations and unknowns. A page or summary may refer to a separate full record. Do not treat a missing result in a partial inventory as proof of absence.

A retained Evidence ID is scoped to its live connection. Use `export_evidence_bundle` to save the original bundle in the work project, then use `import_evidence_bundle` before reusing those IDs on a new connection. Keep the original bundle; a note or copied ID does not replace it. Pass absolute paths to evidence tools. For tool-specific workflows refer to the installed official REA documentation.

Reverse Fusion notes, static Field readings and byte comparisons are not official REA Evidence. State which source supports each conclusion.
