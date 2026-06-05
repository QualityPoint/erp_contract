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
| Chain definition | `Contract Settings → Roles` child table (`Contract Approval Role`) |
| Per-contract state | `ERP Contract → Approvals` child table (`Contract Approver`) |
| Contract-level status | `ERP Contract → Approval Status` (Select) |
| Triggered at | `before_submit` (chain populated) and `on_submit` (gate check) |
| Approver actions | Approve / Reject buttons rendered client-side when it is the user's turn |
| Notifications | Email to next approver on each step advance; email to owner on final approval or rejection |

---

## End-to-End Flow

```
┌──────────────────────────────────┐
│  Contract Settings               │
│  apply_hierarchical_approvals=1  │
│  roles:                          │
│    precedence=1 → Financial      │
│    precedence=2 → Legal          │
│    precedence=3 → Manager        │
└────────────────┬─────────────────┘
                 │ read on before_submit
                 ▼
┌────────────────────────────────────────────────────────┐
│  populate_approval_chain(contract)                     │
│                                                        │
│  1. Resolves first enabled user per role               │
│  2. Populates contract.approvals:                      │
│       row 1: precedence=1, role=Financial, status=Pending   │
│       row 2: precedence=2, role=Legal,     status=Waiting   │
│       row 3: precedence=3, role=Manager,   status=Waiting   │
│  3. Shares doc with row-1 user (submit permission)     │
└────────────────┬───────────────────────────────────────┘
                 │ before_submit saves populated rows
                 │
   User clicks Submit → on_submit fires
                 │
                 ▼
┌──────────────────────────────────────────────────────┐
│  assert_approval_chain_complete(contract)            │
│                                                      │
│  If any row is not Approved → throw (blocks submit)  │
│  If all rows Approved → proceed                      │
└──────────────────────────────────────────────────────┘
                 │
   After submit, Financial user sees the form
                 ▼
┌──────────────────────────────────────────────────────┐
│  approve_contract(contract_name, signature)          │
│                                                      │
│  1. Validates submitter == Pending row user          │
│  2. Marks row-1 Approved, sets approved_on           │
│  3. Advances row-2 to Pending                        │
│  4. Shares doc with row-2 user                       │
│  5. Emails row-2 user                                │
└──────────────────────────────────────────────────────┘
                 │  … repeat for Legal …
                 ▼
         Manager approves (last step)
                 │
                 ▼
┌──────────────────────────────────────────────────────┐
│  No more Waiting rows                                │
│  contract.approval_status = "Approved"               │
│  Owner is notified                                   │
└──────────────────────────────────────────────────────┘
```

At any point an approver may **reject** instead:

```
reject_contract(contract_name, reason)
  → row marked Rejected
  → contract.approval_status = "Rejected"
  → owner notified with reason
  → chain halted
```

---

## When Hierarchical Approvals Are Disabled

If `apply_hierarchical_approvals = 0` in Contract Settings:

- `populate_approval_chain` is a no-op — no rows are added.
- `assert_approval_chain_complete` is a no-op — `on_submit` proceeds normally.
- No buttons are rendered on the form.
- The `Approvals` child table remains empty.

The feature is entirely additive; disabling it does not affect existing contracts.

---

## Documents

| File | Content |
|---|---|
| [README.md](README.md) | This overview |
| [data_model.md](data_model.md) | Field definitions across all three doctypes |
| [approval_module.md](approval_module.md) | Full walkthrough of `utils/approval.py` |
| [controller_integration.md](controller_integration.md) | How `erp_contract.py` hooks into the chain |
| [client_side.md](client_side.md) | JS button rendering and signature dialog |
