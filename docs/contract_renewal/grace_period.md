# Grace Period — Button Visibility

## Source

Settings are read from `Contract Settings` (Single doctype):

| Field | Type | Default |
|---|---|---|
| `renewal_grace_period` | Int | 1 |
| `grace_period_uom` | Select (Day / Month) | Month |

## Visibility Conditions

The **Renew** button is shown when **all** of the following are true:

1. `contract_category == "Duration-Based"`
2. `docstatus == 1` (submitted)
3. `status in ("Active", "Inactive")` — blocked for: Draft, Unsigned, On Hold, Completed, Terminated, Cancelled
4. `today >= end_date - grace_period` (grace window is open)

Condition 4 expressed in code:
```python
from dateutil.relativedelta import relativedelta
from frappe.utils import getdate, nowdate, add_days

today = getdate(nowdate())

if grace_period_uom == "Month":
    window_start = getdate(end_date) - relativedelta(months=renewal_grace_period)
elif grace_period_uom == "Day":
    window_start = add_days(getdate(end_date), -renewal_grace_period)

is_in_window = today >= window_start
```

## Grace Window Check

The grace window is computed **client-side** on every form load — no scheduled job or stored flag is needed.

Grace period settings are fetched once via `erp_contract.utils.contract.get_renewal_settings` and the date comparison is pure arithmetic:

```js
// Inside refresh(frm), after fetching settings:
const endDate = frappe.datetime.str_to_obj(frm.doc.end_date);
let windowStart;
if (settings.grace_period_uom === "Month") {
    windowStart = frappe.datetime.add_months(frm.doc.end_date, -settings.renewal_grace_period);
} else {
    windowStart = frappe.datetime.add_days(frm.doc.end_date, -settings.renewal_grace_period);
}
const inWindow = frappe.datetime.get_today() >= windowStart;
```

No field, no scheduler, no stale state.
