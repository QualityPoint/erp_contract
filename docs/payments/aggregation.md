# Aggregation Logic — `recalculate_contract_payment()`

**File**: `erp_contract/utils/payment.py`  
**Layer**: Core business logic (Layer 2)  
**Called by**: `overrides/payment_entry.py`, `overrides/journal_entry.py`, `erp_contract.py :: on_submit()`

---

## Purpose

This function is the **single source of truth** for how ERP Contract computes payment
progress. It receives a set of Sales Order names (regardless of which voucher type triggered
the call), queries the GL layer, and writes the result to every matching ERP Contract.

---

## Full Source

```python
def recalculate_contract_payment(sales_orders):
    from frappe.utils import flt

    PLE = frappe.qb.DocType("Payment Ledger Entry")

    for so_name in sales_orders:
        contracts = frappe.get_all(
            "ERP Contract",
            filters={"sales_order": so_name, "docstatus": 1},
            fields=["name", "net_total", "advance_amount", "apply_installment_payment"],
        )

        if not contracts:
            continue

        result = (
            frappe.qb.from_(PLE)
            .select(
                frappe.qb.fn.Abs(
                    frappe.qb.fn.Sum(PLE.amount_in_account_currency)
                ).as_("total_paid")
            )
            .where(PLE.against_voucher_type == "Sales Order")
            .where(PLE.against_voucher_no == so_name)
            .where(PLE.delinked == 0)
        ).run(as_dict=True)

        total_paid = flt(result[0].total_paid if result else 0)

        for contract in contracts:
            net_total = flt(contract.net_total)
            per_payment = flt(total_paid / net_total * 100, 2) if net_total else 0

            if total_paid <= 0:
                payment_status = "Unpaid"
            elif per_payment >= 100:
                payment_status = "Fully Paid"
            else:
                payment_status = "Partially Paid"

            frappe.db.set_value(
                "ERP Contract",
                contract.name,
                {
                    "per_payment": per_payment,
                    "payment_status": payment_status,
                },
                update_modified=False,
            )
```

---

## Step-by-Step Walkthrough

### 1. Iterate over Sales Orders

The function iterates over the supplied set of SO names. Each SO is processed
independently, so a PE that references two SOs triggers two independent recalculations —
each touching only the contracts linked to that specific SO.

### 2. Find linked submitted ERP Contracts

```python
contracts = frappe.get_all(
    "ERP Contract",
    filters={"sales_order": so_name, "docstatus": 1},
    fields=["name", "net_total"],
)
```

Only `docstatus = 1` (submitted) contracts are updated. Drafts and cancelled contracts are
ignored. If no contracts are linked to the SO, the loop continues to the next SO — no
unnecessary PLE query is made.

### 3. Query Payment Ledger Entry (PLE)

```python
frappe.qb.from_(PLE)
.select(Abs(Sum(PLE.amount_in_account_currency)).as_("total_paid"))
.where(PLE.against_voucher_type == "Sales Order")
.where(PLE.against_voucher_no == so_name)
.where(PLE.delinked == 0)
```

#### Why PLE?

`Payment Ledger Entry` is written by the Frappe GL layer when any voucher that affects a
party's outstanding balance is submitted or cancelled. It is the **canonical record of what
has been paid against a document**, covering:

- Payment Entries
- Journal Entries
- Reconciliation write-offs

Querying PLE directly means a single aggregation captures all payment sources without
knowing which specific voucher types were used.

This mirrors ERPNext's own `calculate_total_advance_from_ledger()` function used on
Sales Order — the most battle-tested approach in the codebase.

#### Filter breakdown

| Filter | Purpose |
|---|---|
| `against_voucher_type == "Sales Order"` | Only entries targeting an SO (not direct invoices) |
| `against_voucher_no == so_name` | Only for this specific SO |
| `delinked == 0` | Exclude cancelled / reversed entries (set to 1 on cancel) |

#### Why `Abs(Sum(...))`?

PLE stores amounts with a sign that reflects the direction of the accounting entry (debit vs.
credit). Payment Entries and Journal Entries may store amounts with opposite signs depending
on account type. `Abs()` normalises the sign so the sum is always a positive paid amount,
regardless of how the bookkeeping was recorded.

### 4. Compute per_payment

```python
per_payment = flt(total_paid / net_total * 100, 2) if net_total else 0
```

- Result is rounded to 2 decimal places.
- If `net_total` is zero (data entry error), `per_payment` defaults to 0 to avoid division
  by zero.

### 5. Determine payment_status

| Condition | Value set |
|---|---|
| `total_paid <= 0` | `"Unpaid"` |
| `per_payment >= 100` | `"Fully Paid"` |
| otherwise | `"Partially Paid"` |

`>= 100` rather than `== 100` handles over-payment (advance payment exceeding contract value).

### 6. Write to ERP Contract

```python
frappe.db.set_value(
    "ERP Contract",
    contract.name,
    {"per_payment": per_payment, "payment_status": payment_status},
    update_modified=False,
)
```

- `frappe.db.set_value` writes directly to the DB without loading the full document —
  efficient for bulk updates.
- `update_modified=False` preserves the document's `modified` timestamp, avoiding noise in
  version history and activity feeds.
- Both `per_payment` and `payment_status` are `allow_on_submit = 1` fields, so writing
  them on a submitted contract is valid without `ignore_validate_update_after_submit`.

---

## What This Function Does NOT Know

- Which voucher type (PE or JE) triggered the call.
- Whether the event was a submit or a cancel.
- How the Sales Order names were extracted from the source document.

This is intentional. The function is **voucher-agnostic** — it only knows about Sales Orders
and PLE. Adding a new voucher type in the future requires only a new handler in `overrides/`;
this function does not change.

---

## ERPNext Parity Table

| ERPNext function | ERP Contract equivalent |
|---|---|
| `calculate_total_advance_from_ledger()` | `recalculate_contract_payment()` |
| PLE query with `against_voucher_type` | Same |
| `Abs(Sum(...))` aggregation | Same |
| `delinked = 0` filter | Same |
| `frappe.db.set_value` write | Same |
| `update_modified=False` | Same |
