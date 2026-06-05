# Contract Renewal — Overview

Applies to: **Duration-Based** contracts only.

## Sections

| File | Topic |
|---|---|
| [grace_period.md](grace_period.md) | When the Renew button is shown |
| [dialog.md](dialog.md) | Renewal dialog fields and duration calculation |
| [archive.md](archive.md) | What gets written to Contract Records |
| [field_resets.md](field_resets.md) | Complete field reset map |
| [status.md](status.md) | Status recalculation after renewal |

## Flow Summary

```
Grace window opens
       ↓
User clicks "Renew" button
       ↓
Dialog: fill new contract period
       ↓
Server method (whitelisted):
  1. Append current period → contract_records
  2. Apply all field resets + new period values on doc object
  3. doc.flags.ignore_validate_update_after_submit = True
  4. doc.save()  ← triggers before_update_after_submit
       ↓
before_update_after_submit recalculates status → "Unsigned"
       ↓
Document reloaded on client
```
