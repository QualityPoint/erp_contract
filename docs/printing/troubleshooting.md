# Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Print shows raw `{% %}` / `{{ }}` | Standard format can't render Jinja | Use a Custom HTML print format — see [print-format.md](print-format.md) |
| `'doc' is undefined` | template uses `doc.field` | Use bare `field` (no `doc.` prefix) |
| `'riyal' is undefined` | old `riyal()` (removed) | Replace with `{{ frappe_icon("saudi-riyal") }}` |
| `Could not load terms template …` | runtime error while rendering | usually `format(None)` on an empty number — wrap with `frappe.utils.flt(...)` |
| Icon blank in PDF | sprite `<use>`, CSS-background SVG, or transparent PNG | Use `{{ frappe_icon("…") }}` (inline SVG) — see [icons.md](icons.md) |
| Icon is a black box | transparent PNG + wkhtmltopdf alpha bug | Use `frappe_icon()` (no raster) |
| Blank lines at top of terms | standalone `{% set %}` lines wrapped in `<p>` (old editor) | Put control logic on **one line**; author in the Code field |
| A black/code block in the output | Jinja entered via the editor's source view became a `<pre>`/code block | Author in the Code field as plain text |
| Content disappears on save | old Text Editor sanitization, or old render-on-save consuming the Jinja | Fields are **Code** now; don't use a Text Editor; nothing renders on save |
| Foreign (English) text laid out RTL | block direction | wrap with `dir="ltr"` (or `dir="auto"`) |

## Mental model

- Author Jinja in the **ERP Contract Terms Template** (it's never rendered).
- The contract holds a **raw, editable copy**.
- Rendering happens **only** in the **Print Format**.

See [architecture.md](architecture.md).
