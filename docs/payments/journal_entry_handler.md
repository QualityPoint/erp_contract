# Journal Entry Handler

**File**: `erp_contract/overrides/journal_entry.py`  
**Layer**: Handler (Layer 1)  
**Triggered by**: `Journal Entry` — `on_submit`, `on_cancel`

---

## Purpose

This module is the **entry point** for payment tracking when a Journal Entry is submitted or
cancelled. Its sole job is to read the Journal Entry document, identify which Sales Orders it
references, and hand that list off to the aggregation layer.

It contains **no aggregation logic** and performs **no DB writes**.

---

## Full Source

```python
from erp_contract.utils.payment import recalculate_contract_payment


def update_contract_payment_status_from_je(doc, method=None):
    sales_orders = {
        row.reference_name
        for row in doc.get("accounts", [])
        if row.get("reference_type") == "Sales Order" and row.get("reference_name")
    }

    if not sales_orders:
        return

    recalculate_contract_payment(sales_orders)
```

---

## How It Works

### Step 1 — Extract Sales Order names

Journal Entry does **not** have a dedicated references table. Instead, each account line in
the `Journal Entry Account` child table (`doc.accounts`) can carry an optional reference
back to a source document:

| Field | Example value |
|---|---|
| `reference_type` | `"Sales Order"` |
| `reference_name` | `"SAL-ORD-2026-0001"` |
| `debit_in_account_currency` | `5000.00` |
| `credit_in_account_currency` | `0.00` |

The handler filters for rows where `reference_type == "Sales Order"` and collects
`reference_name` values into a set.

Note the accessor difference vs. Payment Entry:

| | Payment Entry | Journal Entry |
|---|---|---|
| Child table | `doc.references` | `doc.accounts` |
| Reference type field | `ref.reference_doctype` | `row.get("reference_type")` |
| Reference name field | `ref.reference_name` | `row.get("reference_name")` |

`row.get()` is used (instead of `row.reference_type`) to safely handle rows that may not
carry a reference at all.

### Step 2 — Early exit

If no Sales Orders are found, the function returns immediately. Most JE rows are
general-purpose accounting entries with no Sales Order reference.

### Step 3 — Delegate to aggregation

Identical to the PE handler: the set of SO names is passed to
`recalculate_contract_payment()`. From this point the handler has no further responsibility.

---

## Why Journal Entry Covers a Different Use Case

ERPNext supports two common ways to record payment against a Sales Order:

| Scenario | Voucher type |
|---|---|
| Customer pays via bank / cash | Payment Entry (through Make Payment button) |
| Manual adjustment, write-off, or multi-leg accounting | Journal Entry |

Both write to the `Advance Payment Ledger Entry` against the order when submitted — a row
with `against_voucher_type = "Sales Order"` and `against_voucher_no = "<SO name>"` in both
cases. This is why the aggregation layer (which reads that ledger) naturally covers JE
payments without any extra logic — as long as the correct SO names are extracted first.

---

## Why This Handler Is a Separate File

The PE and JE handlers differ only in **which child table they read and which field names
they use**. Despite this apparent similarity, they are kept separate because:

- A change to PE's `references` table structure should not risk touching JE logic.
- A change to JE's `accounts` table structure should not risk touching PE logic.
- Each file can be tested independently.
- The intent of each file is immediately clear from its name.

Merging them into a single file would violate the **Single Responsibility Principle** — the
file would need to change for two unrelated reasons.

---

## Cancellation Behaviour

Identical to the PE handler. When a JE is cancelled, its advance-ledger rows get
`delinked = 1`. The same handler fires on `on_cancel`, passes the same SO names to
`recalculate_contract_payment()`, and the totals are recalculated from the remaining
non-delinked advance-ledger entries.

---

## Hooked By

```python
# hooks.py
doc_events = {
    "Journal Entry": {
        "on_submit": "erp_contract.overrides.journal_entry.update_contract_payment_status_from_je",
        "on_cancel": "erp_contract.overrides.journal_entry.update_contract_payment_status_from_je",
    },
}
```
