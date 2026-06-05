# Client Side — JS Approval Buttons

**File**: `erp_contract/erp_contract/doctype/erp_contract/erp_contract.js`  
**Concern**: Render approval UI when relevant; collect signature; call server APIs

---

## Entry Point

`add_approval_buttons(frm)` is called from `refresh` whenever `docstatus === 1`:

```js
if (frm.doc.docstatus === 1) {
    add_status_action_buttons(frm);   // existing status buttons
    add_approval_buttons(frm);        // new approval buttons
}
```

---

## `add_approval_buttons(frm)`

Calls `erp_contract.utils.approval.get_approval_context` with the contract name.

### If no chain exists (feature off)
`ctx.chain` is empty — function returns silently.

### Always (when chain exists)
Renders a **progress indicator** in `frm.dashboard` showing every step:

```
1. Financial Approver — user@company.com  [Approved]
2. Legal Approver     — legal@company.com [Pending]
3. Manager            — mgr@company.com   [Waiting]
```

Colours: green = Approved, orange = Pending, grey = Waiting, red = Rejected.

### Only when `ctx.is_approver === true`
The current session user is the active `Pending` approver.
Two buttons are added under the **"Approvals"** group:

| Button | Style | Action |
|---|---|---|
| Approve | `btn-success` (green) | Opens signature dialog → calls `approve_contract` |
| Reject | `btn-danger` (red) | Opens reason prompt → calls `reject_contract` |

---

## Signature Dialog

`open_signature_dialog(frm, callback)` opens a minimal Frappe Dialog with a
single `Signature` field. On confirmation it calls `callback(signature)`, which
then calls `approve_contract` with the captured signature string. Signature
is optional — if the user leaves it blank, an empty string is passed.

---

## After Each Action

Both callbacks call `frm.reload_doc()` on success. This re-runs `refresh`,
which re-calls `add_approval_buttons` with the updated chain state — so the
progress indicator always reflects the latest state without a full page reload.

---

## Security Note

Button visibility is purely a convenience — users who are not the current
approver simply don't see the buttons. Server-side, `_assert_is_current_approver`
enforces the same constraint and throws `frappe.PermissionError` if a non-approver
calls the API directly.
