# Icons — `frappe_icon()`

Inline **any** Frappe Lucide icon in a term. Renders in the Desk form preview **and**
the PDF.

## Usage

```jinja
{{ frappe_icon("saudi-riyal") }}
{{ frappe_icon("calendar", size="1.2em", color="#444") }}
```

| Arg | Default | Notes |
|---|---|---|
| `name` | — | Lucide icon name, e.g. `saudi-riyal`, `calendar`, `user`, `check` |
| `size` | `"1em"` | any CSS length |
| `color` | `"currentColor"` | follows surrounding text colour |
| `stroke_width` | `2` | |

Unknown name → returns `""` (no error).

## Why not the obvious options

| Approach | Desk | PDF | Verdict |
|---|---|---|---|
| `frappe.utils.icon()` → `<use href="#icon-…">` | ✅ | ❌ blank (sprite absent in PDF) | JS-only anyway |
| CSS `background-image` data-URI | ✅ | ❌ blank (old WebKit) | no |
| `<img src="data:…">` | — | — | Text Editor sanitizer strips `src` |
| transparent PNG `<img>` | ✅ | ❌ black box (wkhtmltopdf alpha bug) | no |
| **inline `<svg>` from the sprite** | ✅ | ✅ | **used** |

## How it works

`frappe_icon` parses Frappe's Lucide sprite once (cached with `lru_cache`), extracts the
named icon's `viewBox` + paths, and returns a self-contained inline `<svg>` with
`stroke="currentColor"`. Defined in `erp_contract/utils/jinja_methods.py`, exposed to
Jinja via the `jinja` hook in `hooks.py`.

## Caveat

Inline SVG survives because **Code fields and print output are not sanitized**. Do **not**
use `frappe_icon()` inside a *Text Editor* field — the sanitizer strips the `<path d>` and
the icon comes out empty.
