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
| [renewal_payment_setup.md](renewal_payment_setup.md) | "Create" buttons that rebuild advance/installment payment on a renewed contract |

## Flow Summary

```
Grace window opens
       ↓
User clicks "Renew" button
       ↓
Dialog: pick the new Sales Order + fill the new contract period
       ↓
Server method (whitelisted):
  0. Validate: status/grace window, start_date > current end_date,
     new Sales Order (submitted, same party, not already used)
  1. Append current period (incl. its Sales Order) → contract_records
  2. Apply new period values, attach new Sales Order + its financials,
     reset signature/advance/installment fields
  3. doc.flags.ignore_validate_update_after_submit = True
  4. doc.save()  ← triggers before_update_after_submit
       ↓
before_update_after_submit recalculates status → "Unsigned"
       ↓
Document reloaded on client
```
