# Status After Renewal

## Immediate Result

After renewal, `is_signed` is reset to `0` before `doc.save()` is called. `before_update_after_submit` then runs:

```python
# erp_contract.py
def before_update_after_submit(self):
    if self.status not in ("On Hold", "Completed", "Terminated"):
        self.update_contract_status()
```

Renewal only fires from `status in ("Active", "Inactive")`, so the guard condition always passes. `update_contract_status()` calls `get_contract_status(is_signed=False, ...)` which returns `"Unsigned"`.

The status is therefore always **"Unsigned"** immediately after renewal, regardless of `start_date`. **Do not set `status` manually in the renewal method.**

## Subsequent Status Transitions

These follow the existing lifecycle — no special renewal rules:

| Trigger | Status |
|---|---|
| User checks `is_signed` | Active / Inactive (date-driven) |
| Daily scheduler (`update_status_for_contracts`) | Active ↔ Inactive |
| Manual buttons: On Hold, Resume, Terminate, Mark Completed | On Hold / Active / Terminated / Completed |

## Status Decision Tree (reference)

```
is_signed = 0          → Unsigned
is_signed = 1
  Duration-Based
    today > end_date   → Inactive
    today >= start_date → Active
    today < start_date  → Unsigned
  Milestone-Based       → Active
```

Source: `get_contract_status()` in `erp_contract/utils/contract_status.py`.
