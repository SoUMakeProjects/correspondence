# Harbor Point Mortgage Services, LLC

| | |
|---|---|
| Client code | `DEMO-HARBOR` (client configuration version 2) |
| Business | Residential first-mortgage servicing, including escrow administration for property taxes and insurance |
| Sender address | correspondence@harborpointmortgage.com |
| Customer Care | customercare@harborpointmortgage.com · (888) 555-0187 |
| Hours | Monday through Friday, 8:30 a.m. to 7:00 p.m. Eastern Time |
| Correspondence address | P.O. Box 7720, Wilmington, DE 19803-7720 |
| Website | www.harborpointmortgage.com |
| Supported product | Fixed-rate mortgages (`fixed_mortgage`) |
| Review mode | **Review required.** Every outgoing borrower letter needs a human approval of its exact current version before it is sent |
| Required notice | `harbor-servicing-notice`, the standard debt-collector and bankruptcy notice appended to every borrower letter |
| Signature | Customer Care Team, Harbor Point Mortgage Services |

## How Harbor Point handles a tax-bill inquiry on an escrowed loan

1. **Identify** the requester against the loan record. The sender must be the borrower of record and the authorized recipient, and there must be no communication restrictions.
2. **Reconcile** the supplied bill with the servicing tax line: the payee, the amount and the due date must match. A mismatch is a tax evidence conflict. It blocks any response and stays with the Tax Team.
3. **Reuse** the existing Tax Team task for this tax period. Do not open a duplicate. A task that is still pending leaves the schedule as recorded in servicing.
4. **Answer both questions separately.** Say whether the bill was received (with the date), and say what the payment status and timing are. *Scheduled* is not *paid*. Say "paid" only with a disbursement date and a payment reference in the servicing record.
5. **Tell the borrower what to do**: when a disbursement is scheduled, tell them not to pay the bill themselves, to avoid a double payment.
6. **Review.** Every letter waits for a reviewer. New evidence, such as a Tax Team result, makes an earlier draft stale; only the current version can be approved. A reviewer can change the letter only through structured, evidenced claims, which are re-validated.
7. **Send, index, note, close.** Send the approved version from the client sender address. Index it to the loan in OnBase as *INQ Email Reply*, record an ILS Standout Comment with the delivery reference, and close the case only after all three exist and verify.

## Brand usage in this demo

The letter is signed by the Customer Care Team and ends with the Harbor Point notice. Both come from the client configuration in `data/fixtures/v1/clients.json` and the curated disclosure in `data/knowledge/curated.v1.json`. The township tax bill is a third-party document: it names Harbor Point only as the mortgage company on file.
