# Aggregation Logic — `recalculate_contract_payment()`

**File**: `erp_contract/utils/payment.py`
**Layer**: Core business logic (Layer 2)
**Called by**: `overrides/payment_entry.py`, `overrides/journal_entry.py`, `erp_contract.py :: on_submit()`

---

## Purpose

This function is the **single source of truth** for how ERP Contract computes payment
progress. It receives a set of Sales Order names (regardless of which voucher type
triggered the call), reads how much has been received against each order, and writes the
result to every matching ERP Contract.

---

## Source of truth — the Sales Order, via `Advance Payment Ledger Entry`

The contract tracks payment through **one** reference: its `sales_order`. It does **not**
distinguish "advance" from "final" payment, and it does **not** consult Sales Invoices —
an invoice may or may not be raised or paid, so the order is the only reliable anchor.

In ERPNext v15+, every payment that **references a Sales Order** (Payment Entry or Journal
Entry) is recorded in the **`Advance Payment Ledger Entry`** with
`against_voucher_type = "Sales Order"`. This is exactly the figure ERPNext surfaces as
`Sales Order.advance_paid`. So the total received against an order is:

```python
def _total_paid_against_so(so_name) -> float:
    from frappe.utils import flt
    APLE = frappe.qb.DocType("Advance Payment Ledger Entry")
    result = (
        frappe.qb.from_(APLE)
        .select(Abs(Sum(APLE.amount)).as_("total_paid"))
        .where(APLE.against_voucher_type == "Sales Order")
        .where(APLE.against_voucher_no == so_name)
        .where(APLE.delinked == 0)
    ).run(as_dict=True)
    return flt(result[0].total_paid if result else 0)
```

> **Why not `Payment Ledger Entry` (the old design)?** PLE is the *party* ledger; its
> `against_voucher` is whatever the payment **settles** — a Sales Invoice (invoice
> payment) or the Payment Entry itself (order advance / unallocated). In v15+ it is
> **never** keyed to a Sales Order, so a PLE query on `against_voucher_type = "Sales Order"`
> always returns zero for orders. The pre-v15 model *did* post advances to the GL/PLE
> against the order — that is why the old query worked on older ERPNext versions.

---

## Full Source

```python
def recalculate_contract_payment(sales_orders):
    from frappe.utils import flt

    for so_name in sales_orders:
        contracts = frappe.get_all(
            "ERP Contract",
            filters={"sales_order": so_name, "docstatus": 1},
            fields=["name", "net_total", "advance_amount", "apply_installment_payment"],
        )
        if not contracts:
            continue

        total_paid = _total_paid_against_so(so_name)

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
                "ERP Contract", contract.name,
                {"per_payment": per_payment, "payment_status": payment_status},
                update_modified=False,
            )

            if contract.apply_installment_payment:
                recalculate_installment_payment(
                    contract.name,
                    total_paid=total_paid,
                    advance_amount=flt(contract.advance_amount),
                )
```

---

## Step-by-Step Walkthrough

### 1. Iterate over Sales Orders

The supplied set of SO names is processed independently — a voucher that references two
SOs triggers two independent recalculations, each touching only the contracts linked to
that specific SO.

### 2. Find linked submitted ERP Contracts

Only `docstatus = 1` (submitted) contracts are updated. If no contract is linked to the
SO, the loop skips it — no ledger query is made.

### 3. Read the total paid against the SO

`_total_paid_against_so(so_name)` sums `Advance Payment Ledger Entry.amount` where
`against_voucher = Sales Order` and `delinked = 0`.

| Filter | Purpose |
|---|---|
| `against_voucher_type == "Sales Order"` | Money received against this order |
| `against_voucher_no == so_name` | Only this specific SO |
| `delinked == 0` | Exclude cancelled / reversed entries (set to 1 on cancel) |

`Abs(Sum(...))` normalises the ledger sign so the total is a positive paid amount.

### 4. Compute `per_payment`

```python
per_payment = flt(total_paid / net_total * 100, 2) if net_total else 0
```

Rounded to 2 dp; defaults to 0 when `net_total` is 0 (avoids division by zero).

### 5. Determine `payment_status`

| Condition | Value |
|---|---|
| `total_paid <= 0` | `"Unpaid"` |
| `per_payment >= 100` | `"Fully Paid"` |
| otherwise | `"Partially Paid"` |

`>= 100` handles over-payment.

### 6. Write to ERP Contract

`frappe.db.set_value(..., update_modified=False)` writes `per_payment` + `payment_status`
directly (both `allow_on_submit = 1`), without bumping `modified`.

---

## What This Function Does NOT Do

- It does **not** read Sales Invoices or their paid/outstanding state.
- It does **not** distinguish advance vs final payment.
- It does **not** know which voucher type (PE or JE) triggered the call, or whether the
  event was a submit or cancel — cancellation is handled implicitly by `delinked = 0`.

The Sales Order is the only bridge between a contract and its payments.

---

## ERPNext Parity

| ERPNext | ERP Contract equivalent |
|---|---|
| `Sales Order.advance_paid` (`calculate_total_advance_from_ledger`) | `_total_paid_against_so()` |
| `Advance Payment Ledger Entry`, `against_voucher_type = "Sales Order"` | Same |
| `Abs(Sum(amount))`, `delinked = 0` | Same |
