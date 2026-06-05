# Hooks — `doc_events` and `scheduler_events` Wiring

**File**: `erp_contract/hooks.py`  
**Layer**: Configuration (wiring only)

---

## Purpose

`hooks.py` is the **glue** between Frappe's event system and the override handlers. It
contains no business logic — only path strings that tell Frappe which Python functions to
call when specific document events fire.

---

## Relevant Configuration

```python
doc_events = {
    "Payment Entry": {
        "on_submit": "erp_contract.overrides.payment_entry.update_contract_payment_status",
        "on_cancel": "erp_contract.overrides.payment_entry.update_contract_payment_status",
    },
    "Journal Entry": {
        "on_submit": "erp_contract.overrides.journal_entry.update_contract_payment_status_from_je",
        "on_cancel": "erp_contract.overrides.journal_entry.update_contract_payment_status_from_je",
    },
}
```

---

## How Frappe Resolves These Paths

When a Payment Entry is submitted, Frappe:

1. Looks up `doc_events["Payment Entry"]["on_submit"]` across all installed apps.
2. Resolves `"erp_contract.overrides.payment_entry.update_contract_payment_status"` by
   splitting on the last `.` — module path is `erp_contract.overrides.payment_entry`,
   function name is `update_contract_payment_status`.
3. Imports the module and calls the function with `(doc, method="on_submit")`.

The same resolution applies to `on_cancel` and to the Journal Entry paths.

---

## Event Symmetry

Both `on_submit` and `on_cancel` point to the **same function** in each case. This is
intentional:

- On submit: PLE rows are created with `delinked = 0` → `total_paid` increases.
- On cancel: PLE rows for the cancelled voucher are set to `delinked = 1` →
  `recalculate_contract_payment()` re-aggregates using only the remaining active rows →
  `total_paid` decreases (or reaches zero).

The handler does not need to know whether the event was a submit or cancel — the PLE state
already reflects the correct net amount at the time of the call.

---

## Scheduler Events

```python
scheduler_events = {
    "daily": [
        "erp_contract.utils.payment.update_overdue_installments",
        "erp_contract.utils.contract_status.update_status_for_contracts",
    ],
}
```

| Path in hooks.py | Function |
|---|---|
| `erp_contract.utils.payment.update_overdue_installments` | Safety-net: marks overdue installment rows |
| `erp_contract.utils.contract_status.update_status_for_contracts` | Recalculates Active/Inactive for Duration-Based contracts |

---

## Adding a New Voucher Type

If a future voucher type (e.g. a custom `Advance Payment Entry`) also needs to update
contract payment status:

1. Create `erp_contract/overrides/<new_doctype>.py` with an extraction handler.
2. Add an entry to `doc_events` in `hooks.py`:

```python
"Advance Payment Entry": {
    "on_submit": "erp_contract.overrides.advance_payment_entry.update_contract_payment_status_from_ape",
    "on_cancel": "erp_contract.overrides.advance_payment_entry.update_contract_payment_status_from_ape",
},
```

3. No changes needed to `recalculate_contract_payment()` — it is voucher-agnostic.

---

## What hooks.py Does NOT Do

- No import of any handler module.
- No conditional logic.
- No knowledge of PLE, SO names, payment fields, or installment rows.

A change to a handler function signature, a move to a different module, or the addition of
a new handler or scheduler task — all require updating `hooks.py`. But no change to the
payment formula, the waterfall algorithm, or the overdue logic requires touching `hooks.py`.
