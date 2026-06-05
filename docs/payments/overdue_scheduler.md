# Overdue Installments — Daily Scheduler

**Function**: `update_overdue_installments()`  
**File**: `erp_contract/utils/payment.py`  
**Layer**: Scheduler task  
**Registered in**: `hooks.py` → `scheduler_events["daily"]`

---

## Why a Scheduler Is Needed

Payment events (PE / JE submit / cancel) only fire when money **moves**. They have no
knowledge of the passage of time.

The transition from `Unpaid` → `Overdue` is a **time-based event**: an installment's due
date passes with no payment. No voucher is created, no `doc_event` fires. A payment
function will never catch this. A daily scheduler is the only correct mechanism.

---

## What It Does

Every day, the scheduler scans all `Installment Schedule` rows where:

1. The parent ERP Contract is submitted (`docstatus = 1`)
2. The parent contract has `apply_installment_payment = 1`
3. `installment_due_date < today`
4. `installment_payment_status` is currently `Unpaid` or `Partially Paid`

For each matching row, it sets `installment_payment_status = "Overdue"`.

> **Scope**: The scheduler is a **safety net** for rows that have had no payment event
> fired against them (no PE or JE was ever submitted for their SO). For rows that DO
> receive a payment event, `recalculate_installment_payment()` already sets `Overdue`
> in real-time during the waterfall (date-aware logic). The scheduler catches the
> remaining case: rows whose due date passed while no payment was ever attempted.

---

## Full Source

```python
def update_overdue_installments():
    from frappe.utils import today

    today_date = today()

    rows = frappe.db.sql(
        """
        SELECT sch.name
        FROM `tabInstallment Schedule` sch
        INNER JOIN `tabERP Contract` con
            ON con.name = sch.parent
        WHERE
            sch.parenttype = 'ERP Contract'
            AND con.docstatus = 1
            AND con.apply_installment_payment = 1
            AND sch.installment_due_date < %(today)s
            AND sch.installment_payment_status IN ('Unpaid', 'Partially Paid')
        """,
        {"today": today_date},
        as_dict=True,
    )

    for row in rows:
        frappe.db.set_value(
            "Installment Schedule",
            row.name,
            "installment_payment_status",
            "Overdue",
            update_modified=False,
        )

    if rows:
        frappe.db.commit()
```

---

## Why Raw SQL Instead of `frappe.get_all`

`frappe.get_all` does not support `INNER JOIN` across parent/child tables in a single call.
A raw SQL query with a join is the cleanest way to filter child rows based on parent
conditions without loading every contract and iterating in Python.

The query uses a parameterised `%(today)s` placeholder — no string interpolation, no SQL
injection risk.

`sch.parenttype = 'ERP Contract'` is included alongside the join condition because Frappe's
child table FK is `(parent, parenttype)` together — `parent` alone is not a unique
identifier across all child tables.

---

## Status Transition Rules

| Current status | Due date | Action |
|---|---|---|
| `Unpaid` | past | → `Overdue` |
| `Partially Paid` | past | → `Overdue` |
| `Paid` | any | **No change** (fully paid rows are never touched) |
| `Overdue` | past | **No change** (already correct, avoid redundant write) |

The filter `IN ('Unpaid', 'Partially Paid')` enforces the last two rules — `Paid` and
already-`Overdue` rows are excluded from the query entirely.

---

## Interaction with Payment Recalculation

The scheduler and the waterfall function are complementary:

| Scenario | What happens |
|---|---|
| Due date passes, no payment ever made | Scheduler fires next day → row becomes `Overdue` |
| Payment arrives for an unpaid/overdue row | PE/JE `doc_events` → `recalculate_installment_payment()` → row becomes `Paid` (waterfall absorbs it fully) |
| Partial payment on an overdue row | Waterfall runs → due date is past → row stays `Overdue` (date-aware logic in waterfall) |
| Payment cancelled for a paid row | Waterfall re-runs → absorbed becomes 0 → due date is past → row immediately becomes `Overdue` again (no 24h gap) |
| Payment cancelled, due date not yet passed | Waterfall re-runs → absorbed becomes 0 → row becomes `Unpaid` |

The scheduler is **idempotent** — running it multiple times on the same day has no
effect after the first run (already-`Overdue` rows are excluded by the filter).

---

## `Pending` Status

The `Installment Schedule` doctype has a `Pending` option in the `installment_payment_status`
field. This value is **not set by any automated function** — it is reserved for manual use
(e.g. a payment is expected but not yet confirmed). The scheduler does not touch `Pending`
rows.

---

## Hooks Registration

```python
# hooks.py
scheduler_events = {
    "daily": [
        "erp_contract.utils.payment.update_overdue_installments",
        "erp_contract.utils.contract_status.update_status_for_contracts",
    ],
}
```

Order matters for readability (installment overdue runs before contract status refresh)
but both are independent — neither depends on the result of the other.
