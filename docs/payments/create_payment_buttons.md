# "Create" Buttons — Payment & Payment Request

The ERP Contract form exposes a primary **`Create`** button group (top-right),
mirroring the Sales Order's `Create` menu. It hosts up to four actions:

| Item | Scope | Doc |
|---|---|---|
| **Payment** | any submitted contract, not fully paid | this file |
| **Payment Request** | any submitted contract, not fully paid | this file |
| **Advance Payment** | renewed contracts only | [../contract_renewal/renewal_payment_setup.md](../contract_renewal/renewal_payment_setup.md) |
| **Installment Payment** | renewed contracts only | [../contract_renewal/renewal_payment_setup.md](../contract_renewal/renewal_payment_setup.md) |

All four live in the same group; `frm.page.set_inner_btn_group_as_primary("Create")`
makes it primary. The group is built by `add_create_buttons(frm)` in
`erp_contract.js`, called from `refresh` for every submitted contract.

---

## Why these target the Sales Order

ERP Contract is **not** an Accounts document — it has no General Ledger entries and
is not a valid `reference_doctype` for Payment Entry / Payment Request. Payment
tracking is anchored entirely on the linked **Sales Order** (see
[README.md](README.md) — *Join Key*). Therefore the contract's `Payment` and
`Payment Request` buttons operate on `contract.sales_order`, exactly as if the
user had opened the Sales Order and used its own `Create` menu.

A payment recorded this way is booked against the Sales Order in the
`Advance Payment Ledger Entry` (= `SO.advance_paid`), which fires the existing
`doc_events` handler → `recalculate_contract_payment()` → the contract's
`per_payment` / `payment_status` (and the installment waterfall) update
automatically. No contract-specific payment plumbing is needed.

---

## Visibility (mirrors Sales Order)

Sales Order shows these when `flt(per_billed) < 100 + over_billing_allowance`. The
ERP Contract equivalent uses the contract-level paid percentage:

```
show Payment / Payment Request when:
    docstatus == 1
    && sales_order is set
    && flt(per_payment) < 100 + over_billing_allowance
```

Per-button permission gates, identical to Sales Order:

| Button | Extra gate | Server method |
|---|---|---|
| **Payment Request** | `frappe.boot.user.in_create` includes `"Payment Request"` | `erpnext.accounts.doctype.payment_request.payment_request.make_payment_request` |
| **Payment** | `frappe.model.can_create("Payment Entry")` | `erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry` |

When `per_payment >= 100` (fully paid, including over-payment) both buttons
disappear — same as a fully-billed Sales Order.

---

## Behaviour

### Payment

```js
frappe.call({
    method: "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
    args: { dt: "Sales Order", dn: frm.doc.sales_order },
    callback(r) {
        const doclist = frappe.model.sync(r.message);
        frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
    },
});
```

Opens a new, pre-mapped **Payment Entry** against the Sales Order — the same
mapping Sales Order's own `Create → Payment` produces.

### Payment Request

```js
frappe.call({
    method: "erpnext.accounts.doctype.payment_request.payment_request.make_payment_request",
    args: {
        dt: "Sales Order",
        dn: frm.doc.sales_order,
        party_type: "Customer",
        party: frm.doc.customer,
        party_name: frm.doc.customer_name,
        payment_request_type: "Inward",
    },
    callback(r) {
        frappe.model.sync(r.message);
        frappe.set_route("Form", r.message.doctype, r.message.name);
    },
});
```

`payment_request_type` is **Inward** (customer pays us), matching how Sales Order /
Sales Invoice classify it.

---

## Relationship to Advance / Installment

The advance and installment buttons **structure** the contract's payment plan
(see the renewal doc). `Payment` / `Payment Request` **collect** against that plan.
This matches the note in the renewal flow: the advance/installment buttons set up
the schedule, and *actual* payment is recorded later via `Create → Payment`.
