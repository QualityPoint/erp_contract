# Client Side — JS Approval Buttons

**File**: `erp_contract/erp_contract/doctype/erp_contract/erp_contract.js`  
**Concern**: Render approval UI when relevant; collect signature; call server APIs

---

## Entry Point

`add_approval_buttons(frm)` is called from `refresh` on every **saved, non-cancelled** form:

```js
// Hierarchical approval UI — draft and submitted (never on new or cancelled forms)
if (!frm.is_new() && frm.doc.docstatus !== 2) {
    add_approval_buttons(frm);
}
```

This covers both `docstatus = 0` (draft) and `docstatus = 1` (submitted). The "Request
Approval" button must be available on a draft because the chain must be completed
**before** the contract can be submitted — blocking it to submitted forms would make
the feature unusable.

The `docstatus === 1` status-action buttons (`add_status_action_buttons`) are a
separate branch and are unaffected.

---

## `add_approval_buttons(frm)`

Makes a single `get_approval_context` call per refresh and branches on the result.

```js
frappe.call({
    method: "erp_contract.utils.approval.get_approval_context",
    args: { contract_name: frm.doc.name },
    callback(r) { … }
});
```

All rendering happens inside the callback. The function is a no-op if `r.message`
is falsy.

### Progress indicator (always, when chain has been initiated)

When `ctx.chain` is non-empty the function adds a blue dashboard comment listing
every step. The actor (`step.user`) is shown only once a step has been acted on
— `Pending` / `Waiting` steps show just the role, since any of its holders may act:

```
1. Financial Approver — finance@company.com  [Approved]
2. Legal Approver                            [Pending]
3. Manager                                   [Waiting]
```

Status badge colours are produced by `_approval_color(status)`:

| Status | Colour |
|---|---|
| `Approved` | green |
| `Pending` | orange |
| `Waiting` | grey |
| `Rejected` | red |

When the chain has never been initiated `ctx.chain` is an empty array and no
progress indicator is rendered.

### "Request Approval" button (`ctx.can_request === true`)

```js
if (ctx.can_request) {
    frm.add_custom_button(__("Request Approval"), () => { … }, GROUP)
       .addClass("btn-primary");
}
```

Shown in the **Approvals** button group. `ctx.can_request` is `true` when:

- Approval roles are configured in Contract Settings.
- The contract is not cancelled.
- `approval_status` is not `"Approved"`.
- No step is currently `"Pending"` (i.e., chain is empty **or** was rejected).

This means the button appears:

1. On a fresh draft before the chain has ever been initiated.
2. After a rejection, allowing the owner to restart from step 1.

**User flow:**

1. User clicks "Request Approval".
2. `frappe.confirm` prompts for confirmation.
3. On confirm: `frappe.call → erp_contract.utils.approval.request_approval` (frozen).
4. On success: green alert, `frm.reload_doc()` — progress indicator appears on next refresh.

### "Approve" / "Reject" buttons (`ctx.is_approver === true`)

Only rendered when the session user **holds the role** of the active `Pending`
step — not a single pre-assigned user, so any holder of that role sees them.

| Button | Style | Action |
|---|---|---|
| `Approve` | `btn-success` (green) | Opens signature dialog → calls `approve_contract` |
| `Reject` | `btn-danger` (red) | Opens reason prompt → calls `reject_contract` |

Both buttons are in the **Approvals** group. If `ctx.is_approver` is `false` the
function returns after rendering the progress indicator and optionally "Request
Approval" — the Approve/Reject buttons are never added.

---

## Signature Dialog

`open_signature_dialog(frm, callback)` is called by the Approve button handler.
It opens a `frappe.ui.Dialog` with a single `Signature` field:

```js
const dialog = new frappe.ui.Dialog({
    title: __("Sign Approval"),
    fields: [{ fieldname: "signature", fieldtype: "Signature", … }],
    primary_action(values) {
        dialog.hide();
        callback(values.signature || "");   // empty string if skipped
    },
});
```

Signature is **optional** — clicking "Confirm Approval" without drawing passes `""`
to `approve_contract`. The server accepts an empty string and stores it as-is.

---

## Reject Prompt

The Reject button uses `frappe.prompt` with a required `Small Text` field:

```js
frappe.prompt(
    { fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
    (values) => frappe.call({ … args: { reason: values.reason } … }),
    __("Reject Contract"),
    __("Confirm Rejection")
);
```

`reason` is validated server-side as well — `reject_contract` throws if it is
empty or whitespace-only.

---

## After Each Action

All three button callbacks call `frm.reload_doc()` on success. This re-runs
`refresh`, which re-calls `add_approval_buttons` with the updated chain state.
The progress indicator always reflects the latest persisted state without a full
page reload.

---

## `_approval_color(status)` Helper

```js
function _approval_color(status) {
    return { "Approved": "green", "Rejected": "red", "Pending": "orange", "Waiting": "grey" }[status] || "grey";
}
```

Used exclusively inside the progress indicator to pick the Frappe indicator CSS
class. Any unknown status falls back to `"grey"`.

---

## Security Note

Button visibility is purely a convenience. Users who do not hold the active
step's role simply do not see the Approve/Reject buttons. Server-side,
`_assert_can_approve` enforces the same constraint and throws
`frappe.PermissionError` if a user without the step's role calls the API
directly. `request_approval` also checks `write` permission on the contract
before touching any state.
