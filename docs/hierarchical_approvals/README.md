# Hierarchical Approvals — Overview

ERP Contract supports an optional, company-configurable approval chain that must
be completed before a contract can be submitted. Each step in the chain is bound
to a Frappe Role; the sequence and the roles are set once in **Contract Settings**
and apply to every new contract submission.

---

## Feature Summary

| Aspect | Detail |
|---|---|
| Master switch | `Contract Settings → Apply Hierarchical Approvals` (Check) |
| Notification mode | `Contract Settings → Follow via Email` (Check): email all role-holders or in-app notification only |
| Chain definition | `Contract Settings → Roles` child table (`Contract Approval Role`) |
| Per-contract state | `ERP Contract → Approvals` child table (`Contract Approver`) |
| Contract-level status | `ERP Contract → Approval Status` (Select) |
| Chain initiated at | "Request Approval" button on the contract form (draft or submitted) |
| Submit gate | `before_submit` — blocks if chain was never started or any step is not Approved |
| Who may act | **Any** user who currently holds the step's role (role-based, not a single pre-assigned user) |
| Approver actions | Approve / Reject buttons rendered client-side when the current user holds the active step's role |
| Notifications | Configurable: email all role-holders **or** in-app Notification Log to all role-holders; owner notified on final outcome. Notification failures never roll back a decision. |

---

## End-to-End Flow

```
┌──────────────────────────────────┐
│  Contract Settings               │
│  apply_hierarchical_approvals=1  │
│  follow_via_email=0 or 1         │
│  roles:                          │
│    precedence=1 → Financial      │
│    precedence=2 → Legal          │
│    precedence=3 → Manager        │
└────────────────┬─────────────────┘
                 │ read on "Request Approval"
                 ▼
┌────────────────────────────────────────────────────────────┐
│  request_approval(contract_name)          [whitelisted]    │
│                                                            │
│  Validates: not cancelled, not approved, no pending step   │
│  Calls _populate_approval_chain(contract, roles):          │
│    1. Validates each role has ≥1 enabled user              │
│    2. Clears any stale rows (empty or rejected chain)      │
│    3. Inserts Contract Approver rows via direct DB writes:  │
│         row 1: precedence=1, role=Financial, Pending       │
│         row 2: precedence=2, role=Legal,     Waiting       │
│         row 3: precedence=3, role=Manager,   Waiting       │
│       (no user is pre-assigned — the role is the authority) │
│    4. Sets contract.approval_status = "Pending Approval"   │
│    5. Shares doc (read) with ALL holders of row-1 role     │
│    6. Notifies all row-1 role-holders (email or system)    │
└────────────────┬───────────────────────────────────────────┘
                 │ committed as its own HTTP request
                 │ (no rollback risk from on_submit)
                 ▼
         A Financial role-holder opens the form
                 ▼
┌──────────────────────────────────────────────────────┐
│  approve_contract(contract_name, signature)          │
│                                                      │
│  1. Validates session user holds the Pending role    │
│  2. Stamps acting user, marks row-1 Approved, sets   │
│     approved_on                                      │
│  3. Advances row-2 to Pending                        │
│  4. Shares doc (read) with ALL holders of row-2 role │
│  5. Notifies all row-2 role-holders (email or system)│
└──────────────────────────────────────────────────────┘
                 │  … repeat for Legal …
                 ▼
         Manager approves (last step)
                 │
                 ▼
┌──────────────────────────────────────────────────────┐
│  No more Waiting rows                                │
│  contract.approval_status = "Approved"               │
│  Owner notified (email or system)                    │
└──────────────────────────────────────────────────────┘
                 │
   User clicks Submit
                 ▼
┌──────────────────────────────────────────────────────┐
│  assert_approval_chain_complete(contract)            │
│                                                      │
│  • Chain never initiated → throw                     │
│  • Any row not Approved  → throw                     │
│  • All rows Approved     → proceed                   │
└──────────────────────────────────────────────────────┘
```

At any point an approver may **reject** instead:

```
reject_contract(contract_name, reason)
  → row marked Rejected
  → contract.approval_status = "Rejected"
  → owner notified with reason
  → chain halted

Owner may re-initiate by clicking "Request Approval" again
  → _populate_approval_chain clears rejected rows and starts fresh
```

---

## Notification Modes (`follow_via_email`)

| Setting | Approver notification | Owner notification |
|---|---|---|
| `follow_via_email = 1` | `frappe.sendmail` to **all** users who hold the role | `frappe.sendmail` to the contract owner's email address |
| `follow_via_email = 0` | `Notification Log` insert for **every** user who holds the role | `Notification Log` insert for the contract owner |

In both modes the notification fans out to every current holder of the step's
role — consistent with the fact that **any** of them may act on the step. The
toggle only changes the *channel* (email vs. in-app bell), not the audience.

Notifications are best-effort: a mail or queue failure is logged via
`frappe.log_error` and swallowed, so it can never roll back an approval that has
already been recorded.

---

## When Hierarchical Approvals Are Disabled

If `apply_hierarchical_approvals = 0` in Contract Settings:

- `request_approval` throws immediately — no chain is built.
- `assert_approval_chain_complete` is a no-op — `on_submit` proceeds normally.
- No buttons are rendered on the form.
- The `Approvals` child table remains empty.

The feature is entirely additive; disabling it does not affect existing contracts.

---

## Documents

| File | Content |
|---|---|
| [README.md](README.md) | This overview |
| [data_model.md](data_model.md) | Field definitions across all doctypes |
| [approval_module.md](approval_module.md) | Full walkthrough of `utils/approval.py` |
| [controller_integration.md](controller_integration.md) | How `erp_contract.py` hooks into the chain |
| [client_side.md](client_side.md) | JS button rendering and signature dialog |
