# Loan aging report calculations

## Date and search filters

- Loan Aging uses a single As of date for balances and aging; blank means today.
- All loans disbursed on or before that date with outstanding balances are eligible,
  including older loans. Legacy Start date query parameters are ignored on Loan Aging.
- The internal cutoff parameter remains `end_date`. Related snapshot reports retain
  their optional disbursement Start date and End date filters.
- Search narrows the same loan cohort used by the table and headline indicators.
- Invalid cutoff dates and future cutoffs return validation errors;
  they do not silently produce an unfiltered report or CSV.

## Calculations

Principal balance is original principal minus principal payments dated on or
before the cutoff, with a minimum of zero. Interest balance follows the same rule
using the loan's stored total contractual interest and interest payments. This is
contractual interest outstanding, not interest accrued only through the cutoff.

Paid Amount is cumulative principal, interest, and penalty payments through the
cutoff for the selected loans. It is not collections during the selected period.
Last Payment likewise ignores later repayments.

Penalty balance replays assessments, penalty payments against the oldest unpaid
assessment, and dated reversals through the cutoff. Reversals remove the remaining
unpaid charge. Today's `remaining_amount` and `is_paid` cannot be used to reconstruct
a past balance.

Days in arrears is the number of days since the oldest installment due date that
is not fully covered by cumulative principal and interest payments at the cutoff.
Monthly due dates follow the existing monthly loan schedule. Flat-rate loans use
equal installments; reducing-rate loans use equal principal with declining monthly
interest on the opening principal, rounded down as in the contractual interest
calculation. The final installment settles the stored contractual total and rounding
remainders. On Loan Aging, Overdue is scheduled principal and interest due strictly
before As of date, minus payments through As of date, floored at zero. Installments
due on As of date are current until the following day. Penalties are excluded.
Related Due reports retain the separate due-on-date and overdue-before-date amounts.
Aging displays up to two decimal places so fractional outstanding balances remain visible.

Principal outstanding on loans **over 30 days** in arrears sums the entire remaining
principal of loans with days in arrears strictly greater than 30. It excludes
interest and penalties. A loan at exactly 30 days is excluded.

Active Borrowers counts distinct borrower IDs with a positive total outstanding
balance in the selected disbursement cohort as of the cutoff. Multiple loans for
the same borrower count once. Records counts loans. At today's cutoff, only
Disbursed and Overdue loans with positive balances count as running. For past
cutoffs, repaid and closed loans are reconstructed from dated transactions rather
than excluded by today's status. Closed loans carry an on-page warning because
their administrative closure dates are not stored.

The All running loans / Arrears >30 days links select the table, its totals, and
CSV export. The two headline indicators always describe the full date/search
cohort; the page states this when the arrears-only view is selected.

## Worked example

A loan disbursed on 01/01/2026 has principal 1,000, interest 100, and ten monthly
installments of 110. A payment on 01/02/2026 allocates 100 to principal and 10 to
interest. The remaining 990 is paid on 01/04/2026.

At 03/03/2026: principal balance = 900, interest balance = 90, Paid Amount = 110,
Overdue Amount = 110, and arrears = 2 days (the unpaid 01/03/2026 installment).
The April payment must not change this March snapshot. At 01/04/2026 after the
full repayment, the loan is no longer outstanding.

## Historical data limits

This reconstructs balances from currently retained, dated transactions and current
contract terms. It is not an immutable accounting snapshot. Hard-deleted or edited
payments, direct penalty adjustments without dated payment records, and past loan
term changes cannot be recovered from the existing schema. A deleted penalty with
no deletion timestamp is excluded because its reversal date is unknown. The
schema does not retain dated administrative loan-closure history, so active means
outstanding recorded financial exposure, not a historical administrative status.
Closed loans with unexplained residual debt require reconciliation.

Non-performing loans counts loans with a positive outstanding balance and at least 90 days in arrears at End date, matching the existing Non-Performing Loans report. It follows the disbursement period and search. Multiple qualifying loans for one client count separately.

PAR >30 (%) = outstanding principal on loans strictly over 30 days in arrears / total outstanding principal in the selected disbursement period and search, multiplied by 100. Display uses two decimal places; a zero denominator displays 0.00%. The arrears-only table toggle does not narrow this denominator. Clients in arrears counts distinct borrowers with positive overdue amounts and days in arrears greater than zero. Printouts include the effective End date and filter context.

## Related snapshot reports

Arrears, PAR, NPL, and Due and Overdue now share the Aging disbursement cohort, End-date cutoff, validation, and historical-status limitations. Invalid filters block calculation and CSV export. The old Due report `date` parameter is explicitly rejected; use End date.

- Arrears includes positive unpaid scheduled amounts with days in arrears greater than zero.
- NPL includes positive outstanding balances with days in arrears at least 90, including partially paid loans.
- PAR uses principal only, with cumulative strict >0, >30, >60, >90, >120, and >180 thresholds. The denominator is all outstanding principal in the selected cohort, never just delinquent principal. Zero denominators display 0.00%; overlapping rows are not totalled.
- Due on selected date is the unpaid scheduled amount through End date minus the unpaid scheduled amount before End date, both calculated with all principal/interest repayments through End date. This applies the existing cumulative installment allocation, including prepayments and partial payments. Penalty payments do not settle scheduled installments.
- Due report groups are mutually exclusive: past maturity first, then earlier arrears, then due on selected date. Past-maturity loans with penalty-only balances remain visible. For the past-maturity group, the unpaid summary is the full outstanding balance including penalties; other category unpaid summaries are scheduled principal and interest due through End date. The relevant due date is the oldest unpaid installment, or maturity for a penalty-only balance.

Gender describes the current client record, not a historical gender snapshot. Existing local sample genders remain demo values. Historical reporting cannot reconstruct hard-deleted or edited transactions or missing effective closure/reversal dates.

Defaulted Loans and Outstanding Loan Balances also use the shared snapshot rules. Defaulted preserves the existing strict >90-day threshold (different from NPL >=90). Outstanding includes all positive-balance loans in the selected cohort, including current loans and penalty-only balances. Both exclude loans not yet disbursed and apply the same current/historical status handling as Aging.
