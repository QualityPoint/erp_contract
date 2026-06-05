# Copyright (c) 2026, QualityPoint and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe.utils.user import get_users_with_role


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def get_approval_roles() -> list[dict]:
    """
    Return the ordered approval chain from Contract Settings.
    Each dict has keys: role (str), precedence (int).
    Returns [] if apply_hierarchical_approvals is not enabled.
    """
    if not frappe.db.get_single_value("Contract Settings", "apply_hierarchical_approvals"):
        return []

    rows = frappe.get_all(
        "Contract Approval Role",
        filters={"parent": "Contract Settings", "parentfield": "roles"},
        fields=["role", "precedence"],
        order_by="precedence asc",
    )
    return rows


# ---------------------------------------------------------------------------
# Population  (called on before_submit)
# ---------------------------------------------------------------------------

def populate_approval_chain(contract):
    """
    Build the approvals child table from Contract Settings roles.
    Each role maps to the first enabled user who holds that role.
    Raises if hierarchical approvals are on but no roles are configured,
    or if a role has no eligible user.

    Row states after population:
      precedence=1  → Pending   (active step)
      precedence>1  → Waiting   (not yet reached)
    """
    roles = get_approval_roles()
    if not roles:
        return  # feature disabled — nothing to do

    # Deduplicate precedence values defensively
    seen_precedence = set()
    for row in roles:
        p = int(row.precedence)
        if p in seen_precedence:
            frappe.throw(
                _("Duplicate precedence {0} in Contract Settings approval roles.").format(p)
            )
        seen_precedence.add(p)

    contract.approvals = []  # clear any stale rows

    for i, row in enumerate(roles):
        users = get_users_with_role(row.role)
        if not users:
            frappe.throw(
                _("No active user found for approval role \"{0}\" (precedence {1}). "
                  "Assign this role to at least one user before submitting.").format(
                    row.role, row.precedence
                )
            )

        contract.append("approvals", {
            "precedence": int(row.precedence),
            "role": row.role,
            "user": users[0],  # first eligible user for this role
            "approval_status": "Pending" if i == 0 else "Waiting",
        })

    # Share the document with the first approver so they can see and act on it
    _share_with_user(contract, contract.approvals[0].user)


# ---------------------------------------------------------------------------
# Guard  (called on before_submit after populate)
# ---------------------------------------------------------------------------

def assert_approval_chain_complete(contract):
    """
    Raise if hierarchical approvals are enabled and the chain is not fully
    approved.  Called from on_submit as the final gate.
    """
    if not get_approval_roles():
        return

    for row in contract.get("approvals", []):
        if row.approval_status != "Approved":
            frappe.throw(
                _("Contract cannot be submitted until all approvals are granted. "
                  "Step {0} ({1}) is still \"{2}\".").format(
                    row.precedence, row.role, row.approval_status
                ),
                title=_("Pending Approvals"),
            )


# ---------------------------------------------------------------------------
# Approve / Reject  (whitelisted — called from JS buttons)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def approve_contract(contract_name: str, signature: str | None = None) -> dict:
    """
    Record approval for the current user on the active Pending step.
    Advances the chain to the next step (or marks the contract Approved).

    Returns a dict with keys:
      chain_complete (bool) — True when all steps are done
      next_approver  (str|None) — user email of the next pending step
    """
    contract = frappe.get_doc("ERP Contract", contract_name)
    _assert_can_act(contract)

    pending_row = _get_pending_row(contract)
    _assert_is_current_approver(pending_row)

    # Record the approval
    frappe.db.set_value(
        "Contract Approver", pending_row.name,
        {
            "approval_status": "Approved",
            "approved_on": now_datetime(),
            "signature": signature or "",
        },
        update_modified=False,
    )

    # Advance chain or close it
    next_row = _next_row(contract, pending_row.precedence)
    if next_row:
        frappe.db.set_value(
            "Contract Approver", next_row.name,
            {"approval_status": "Pending"},
            update_modified=False,
        )
        _share_with_user(contract, next_row.user)
        _notify_approver(contract, next_row.user)
        return {"chain_complete": False, "next_approver": next_row.user}
    else:
        # All steps approved
        frappe.db.set_value(
            "ERP Contract", contract_name,
            {"approval_status": "Approved"},
            update_modified=False,
        )
        _notify_owner(contract, approved=True)
        return {"chain_complete": True, "next_approver": None}


@frappe.whitelist()
def reject_contract(contract_name: str, reason: str) -> None:
    """
    Record rejection for the current user on the active Pending step.
    Halts the chain and marks the contract Rejected.
    """
    if not reason or not reason.strip():
        frappe.throw(_("A rejection reason is required."))

    contract = frappe.get_doc("ERP Contract", contract_name)
    _assert_can_act(contract)

    pending_row = _get_pending_row(contract)
    _assert_is_current_approver(pending_row)

    frappe.db.set_value(
        "Contract Approver", pending_row.name,
        {
            "approval_status": "Rejected",
            "approved_on": now_datetime(),
            "rejection_reason": reason.strip(),
        },
        update_modified=False,
    )
    frappe.db.set_value(
        "ERP Contract", contract_name,
        {"approval_status": "Rejected"},
        update_modified=False,
    )
    _notify_owner(contract, approved=False, reason=reason.strip())


# ---------------------------------------------------------------------------
# Client-side context  (whitelisted — powers JS button visibility)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_approval_context(contract_name: str) -> dict:
    """
    Return everything the JS layer needs to render approval buttons:
      is_approver      — True if the current user is the active Pending approver
      pending_row      — name of the Pending Contract Approver row (or None)
      approval_status  — contract-level status
      chain            — list of {precedence, role, user, approval_status}
    """
    contract = frappe.get_doc("ERP Contract", contract_name)
    rows = contract.get("approvals", [])

    pending_row = next((r for r in rows if r.approval_status == "Pending"), None)
    is_approver = bool(
        pending_row and pending_row.user == frappe.session.user
    )

    return {
        "is_approver": is_approver,
        "pending_row": pending_row.name if pending_row else None,
        "approval_status": contract.approval_status or "Pending Approval",
        "chain": [
            {
                "precedence": r.precedence,
                "role": r.role,
                "user": r.user,
                "approval_status": r.approval_status,
            }
            for r in sorted(rows, key=lambda r: r.precedence)
        ],
    }


# ---------------------------------------------------------------------------
# Internal helpers  (no whitelist — not callable from outside)
# ---------------------------------------------------------------------------

def _get_pending_row(contract):
    """Return the single Pending row, or throw if none exists."""
    rows = [r for r in contract.get("approvals", []) if r.approval_status == "Pending"]
    if not rows:
        frappe.throw(_("No pending approval step found on this contract."))
    return rows[0]


def _next_row(contract, current_precedence: int):
    """Return the Waiting row with the lowest precedence above current, or None."""
    waiting = sorted(
        [r for r in contract.get("approvals", []) if r.approval_status == "Waiting"],
        key=lambda r: r.precedence,
    )
    return waiting[0] if waiting else None


def _assert_can_act(contract):
    """Raise if the contract is not submitted or is already fully decided."""
    if contract.docstatus != 1:
        frappe.throw(_("Approvals can only be recorded on submitted contracts."))
    if contract.approval_status in ("Approved", "Rejected"):
        frappe.throw(
            _("This contract has already been {0}.").format(
                contract.approval_status.lower()
            )
        )


def _assert_is_current_approver(pending_row):
    """Raise if the current session user is not the expected approver."""
    if pending_row.user != frappe.session.user:
        frappe.throw(
            _("Only {0} can act on this approval step.").format(pending_row.user),
            frappe.PermissionError,
        )


def _share_with_user(contract, user: str) -> None:
    """Give a user Submit-level access to the contract if they don't already have it."""
    if not user:
        return
    if not frappe.has_permission(doc=contract, ptype="submit", user=user):
        frappe.share.add_docshare(
            contract.doctype, contract.name, user,
            submit=1,
            flags={"ignore_share_permission": True},
        )


def _notify_approver(contract, user: str) -> None:
    """Send an email to the next approver that it is their turn."""
    if not user:
        return
    subject = _("Action Required: Contract {0} awaits your approval").format(contract.name)
    message = _(
        "Dear {0},<br><br>"
        "Contract <b>{1}</b> requires your approval.<br>"
        "Please open the contract and click the <b>Approve</b> or <b>Reject</b> button.<br><br>"
        "Thank you."
    ).format(user, frappe.utils.get_link_to_form("ERP Contract", contract.name))
    frappe.sendmail(recipients=[user], subject=subject, message=message, now=True)


def _notify_owner(contract, approved: bool, reason: str = "") -> None:
    """Notify the contract owner of final approval or rejection."""
    owner_email = frappe.db.get_value("User", contract.owner, "email") or contract.owner
    if approved:
        subject = _("Contract {0} has been fully approved").format(contract.name)
        message = _(
            "All approval steps for contract <b>{0}</b> have been completed.<br>"
            "The contract is now ready for submission."
        ).format(frappe.utils.get_link_to_form("ERP Contract", contract.name))
    else:
        subject = _("Contract {0} was rejected").format(contract.name)
        message = _(
            "Contract <b>{0}</b> was rejected.<br>"
            "Reason: {1}"
        ).format(frappe.utils.get_link_to_form("ERP Contract", contract.name), reason)
    frappe.sendmail(recipients=[owner_email], subject=subject, message=message, now=True)
