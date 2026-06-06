# Post-Renewal Payment Setup — "Create" Buttons

Applies to: **renewed** ERP Contracts only (`is_renewed = 1`, `docstatus = 1`).

## Why this exists

Renewal ([renew_contract](field_resets.md)) attaches the new period's Sales Order
and its financials, but **resets** the advance-payment and installment fields and
sets `payment_status = "Unpaid"`. Those fields
(`advance_payment_entry`, `advance_amount`, `apply_installment_payment`,
`due_start_date`, `payment_periodicity`, `installment_count`, `amount_due`,
`payment_schedule`) have **no `allow_on_submit`**, so the form cannot edit them on
the submitted contract.

To let the user build the new period's payment structure, the form's
**`Create`** primary button group gains two actions, each backed by a whitelisted
server method that writes through `ignore_validate_update_after_submit` (the same
strategy as `renew_contract`).

> The `Create` group is shared. On **any** submitted contract it also hosts
> **Payment** and **Payment Request** (made against the linked Sales Order,
> mirroring Sales Order) — see
> [../payments/create_payment_buttons.md](../payments/create_payment_buttons.md).
> The two buttons below are added **in addition**, only for renewed contracts.

---

## The two buttons

| Button | Group | Server method |
|---|---|---|
| **Advance Payment** | `Create` (primary) | `erp_contract.utils.payment.set_renewal_advance` |
| **Installment Payment** | `Create` (primary) | `erp_contract.utils.payment.set_renewal_installments` |

### Visibility (client-side, in `add_renewal_payment_buttons`)

Both require `docstatus == 1 && is_renewed`. In addition:

| Button | Shown when |
|---|---|
| **Advance Payment** | `!advance_payment_entry` **and** `!(apply_installment_payment && payment_schedule.length)` |
| **Installment Payment** | `!apply_installment_payment` |

> **Note on the advance condition.** Once an installment schedule exists, the
> advance is **locked out** — see the ordering constraint below. The check uses
> `payment_schedule.length >= 1` (any rows), *not* `> 1`: a single-installment
> schedule still counts as "installments set up".

Server-side guards mirror these conditions exactly, so direct API calls cannot
bypass them.

---

## The ordering constraint (critical)

```
amount_due = net_total - advance_amount
payment_schedule rows sum to amount_due
```

Because the installment schedule is generated from `amount_due`, the **advance
must be set before the installments**. After a schedule exists, changing the
advance would invalidate the row sums — so:

```
Advance Payment  ──(optional)──►  Installment Payment  ──►  (locked)
```

- You may add an advance, then build installments on the remainder.
- You may build installments directly (no advance) — then the schedule sums to
  the full `net_total` and the advance button disappears.
- You may **not** add an advance after installments are built.

Actual cash collection is **downstream and separate**: payments are recorded as
Payment Entries / Journal Entries against the Sales Order and tracked passively
(see [../payments/README.md](../payments/README.md)). These two buttons only build
the **structure**, not the payments.

---

## `set_renewal_advance(contract_name, advance_payment_entry)`

Links an existing advance Payment Entry to the renewed period.

**Guards**
1. `write` permission on the contract.
2. `docstatus == 1`, `is_renewed == 1`.
3. `advance_payment_entry` is provided.
4. Contract has **no** existing `advance_payment_entry`.
5. Installments are **not** already built (`!(apply_installment_payment && payment_schedule)`).

**Payment Entry validation** (the selected PE must):
- exist and be submitted (`docstatus == 1`), `payment_type == "Receive"`;
- match the contract's `company` and `customer` (`party`);
- reference the contract's **current** `sales_order` (via `Payment Entry Reference`);
- not already be linked as the advance of another submitted ERP Contract;
- its `paid_amount` must not exceed `net_total`.

**Writes** (single `save()` under the ignore flag)
- `advance_payment_entry`, `advance_amount = PE.paid_amount`, `advance_amount_in_words`;
- `amount_due = net_total - advance_amount` (forward value for a later schedule).

**After save:** calls `recalculate_contract_payment({sales_order})` so
`per_payment` / `payment_status` immediately reflect the linked advance.

---

## `set_renewal_installments(contract_name, due_start_date, payment_periodicity, installment_count)`

Builds the installment schedule for the renewed period.

**Guards**
1. `write` permission, `docstatus == 1`, `is_renewed == 1`.
2. `apply_installment_payment` is **not** already set.
3. `amount_due = net_total - advance_amount` must be `> 0`.

**Writes** (single `save()` under the ignore flag)
- `amount_due = net_total - advance_amount`;
- `apply_installment_payment = 1`, `due_start_date`, `payment_periodicity`, `installment_count`;
- `payment_schedule` rebuilt from `create_payment_schedule(due_start_date, installment_count, payment_periodicity, amount_due, currency)`.

The schedule rows sum to `amount_due` by construction, so the
`validate_installment_payment` check (skipped under `update_after_submit`) holds
without re-running it.

**After save:** calls `recalculate_contract_payment({sales_order})`, which (because
`apply_installment_payment` is now set) runs the chronological waterfall and sets
each row's `paid_amount` / `installment_per_payment` / `installment_payment_status`.

---

## Why these are server methods, not form edits

The target fields lack `allow_on_submit`, so a normal `frm.set_value` + `save()`
on the submitted contract would be rejected. The whitelisted methods set the
fields on the document object and persist them with
`doc.flags.ignore_validate_update_after_submit = True` — the same pattern
`renew_contract` uses. This also re-derives `status` via
`before_update_after_submit` (no manual status writes).

---

## Edge cases & notes

- **`amount_due` upkeep:** `set_renewal_advance` sets `amount_due` so a later
  installment build starts from the correct remainder; `set_renewal_installments`
  recomputes it from the *current* advance at build time regardless.
- **Advance equal to net_total:** `amount_due` becomes `0`, so installments can't
  be created (`create_payment_schedule` rejects `amount_due <= 0`) — correct, the
  period is fully covered by the advance.
- **Old advance is not archived as a field — and does not need to be.** Renewal
  archives the previous period's `sales_order` into `contract_records`, and that
  Sales Order is the join key for *all* of its payments (advance Payment Entry,
  other Payment Entries, Journal Entries) via `Payment Ledger Entry`
  (`against_voucher_type = "Sales Order"`). The old advance PE is therefore fully
  recoverable from the archived SO — see [../payments/aggregation.md](../payments/aggregation.md).
- **Pre-existing payments on the new SO:** the `recalculate_contract_payment` call
  after each method syncs `per_payment` from the Payment Ledger Entry, so payments
  already booked against the new Sales Order are reflected immediately.
