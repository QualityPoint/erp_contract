# Printing Terms & Conditions

How ERP Contract stores, authors, and prints its Terms & Conditions.

**Core idea:** a term is a raw **Jinja template** stored verbatim in a Code field and
rendered **only at print time** by a Print Format. Nothing is rendered on save.

## Data flow

```
ERP Contract Terms Template   (raw Jinja, Code field)   ← you author here
        │  select template → rows copied RAW
        ▼
ERP Contract.contract_terms   (raw Jinja, Code field)   ← editable per contract
        │  frappe.render_template(row…, doc.as_dict())
        ▼
Print Format (Custom HTML)    → print preview & PDF      ← the only render point
```

## Documents

- [Architecture](architecture.md) — the model, where Jinja lives, key files.
- [Authoring terms](authoring-terms.md) — writing Jinja in a term: fields, helpers, gotchas.
- [Icons — `frappe_icon()`](icons.md) — the custom icon helper.
- [Print format](print-format.md) — rendering terms in a Custom HTML print format.
- [Troubleshooting](troubleshooting.md) — symptom → cause → fix.

## Deploy after changes

```bash
bench --site <site> migrate        # doctype / help / print-format changes
bench --site <site> clear-cache && bench restart   # jinja hook / methods
```
