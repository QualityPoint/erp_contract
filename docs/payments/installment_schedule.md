# Installment Schedule Generation

How the `payment_schedule` (Installment Schedule rows) is built and kept consistent.
This is the **schedule structure** — distinct from the payment **waterfall** in
[installment_payment.md](installment_payment.md).

---

## Generation — `create_payment_schedule()`

**File**: `erp_contract/utils/payment.py`

Splits `amount_due` (= `net_total − advance_amount`) into `installment_count` rows:

- Equal `base_amount` per row; the **last row absorbs the rounding remainder**, so the
  amounts sum to `amount_due` exactly.
- Each row gets an `installment_percent` (see below).
- Due dates step by periodicity (Monthly / Quarterly / Half-Yearly / Yearly).

Used by:
- the form **Create Schedule** button (client preview), and
- the renewal path `set_renewal_installments()` (which writes via
  `ignore_validate_update_after_submit`, so `validate` does **not** run there — the
  percent must already be correct from generation).

---

## `installment_percent` — share of Amount Due

```
installment_percent = installment_amount / amount_due * 100   (amount_due = net_total − advance_amount)
```

Computed by the shared helper **`installment_percents(amounts, amount_due)`**:

- rounds each row to 2 dp;
- the **last row absorbs the rounding drift**, so the rounded percentages sum to **exactly 100**;
- returns zeros when `amount_due <= 0` (no division).

Works identically for equal (generated) and unequal (hand-edited) amounts.

### Do not confuse with `installment_per_payment`

| Field | Meaning | Set by |
|---|---|---|
| `installment_percent` | planned **share of Amount Due** (structure) | schedule generation + save-time recompute |
| `installment_per_payment` | how much of the row is **paid** (progress) | payment waterfall — see [installment_payment.md](installment_payment.md) |

---

## Manual edits & validation — `validate_installment_payment()`

**File**: `…/doctype/erp_contract/erp_contract.py`

`installment_amount` (and due date, notes) are **editable** in the grid after generating.
On every save, when `apply_installment_payment = 1`:

1. Validates `Σ installment_amount == amount_due` (within 0.1) — else throws.
2. **Recomputes** `installment_percent` for every row from the current amounts.
   It is `read_only` / derived, so it is never trusted from input — it is always
   re-derived, guaranteeing the column mirrors the amounts and sums to 100.

So however the amounts are hand-edited, the percentages are correct after save.

---

## Keeping Amount Due and the schedule in sync

`amount_due = net_total − advance_amount`. Anything that changes those inputs —
the **Sales Order** (net_total), the **Advance Payment Entry**, or toggling
**Apply Installment Payment** — recomputes `amount_due` and **clears the existing
schedule** (client-side `refresh_amount_due()`), because a schedule built for the old
`amount_due` is now stale and must be rebuilt.

On save, `validate_installment_payment()` is the backstop:
- it sets `amount_due = net_total − advance_amount` (**authoritative** — never trusts a
  possibly-stale stored value), and
- throws if the schedule total no longer matches it.

An advance is **optional**: with none linked, `amount_due = net_total` and a full-amount
schedule is valid.

## DRY

`installment_percents()` is the single source for the percent math — used by both
`create_payment_schedule()` (generation) and `validate_installment_payment()`
(save-time recompute). On the client, `refresh_amount_due()` / `clear_payment_schedule()`
are the single helpers every relevant field handler routes through.
