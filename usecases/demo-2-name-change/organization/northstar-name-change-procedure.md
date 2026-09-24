# Northstar Residential Servicing: borrower name changes

Company profile, contacts and brand usage are the same as in Demo 1: see [Northstar Residential Servicing, LLC](../../demo-1-amortization/organization/northstar-residential-servicing.md). This page covers only the name-change procedure.

| | |
|---|---|
| Client code | `DEMO-NORTH` (client configuration version 2) |
| Review mode | Automatic. Both letters may be sent without a human approval step |
| Guidance used | `profile-evidence`, `profile-missing-template`, `profile-confirmation-template` (curated demo knowledge) |
| Required notice | `northstar-servicing-notice`, appended to both letters |
| Specialist team | Servicing Team (task type `demo_profile_name_update`) |

## How Northstar handles an ordinary (non-HELOC) legal name change

1. **Identify** the requester: the sender must be the borrower of record and the authorized recipient, and there must be no communication restrictions.
2. **Check the evidence.** Two items are required:
   - a written request that the borrower signed and dated by hand, naming the current name and the requested name, and dated no later than the review date;
   - one legal document showing the change, such as a marriage certificate or record, a divorce decree or a court order. The previous and new names on it must match the loan record and the request.
3. **If anything is missing,** send an information request that names the missing item. Record the case as *waiting for borrower* and change nothing on the loan.
4. **When both items are on file,** open or reuse one *Profile name update* task in ILS, carry out the update and read back the completed result. Neither the request nor a pending task counts as proof that the update happened.
5. **Confirm** the change in writing to the borrower. Quote the new name, the previous name, the completion date and the update reference from the task result.
6. **Index** each sent letter to the loan in OnBase, and **note** ILS with a Standout Comment for each delivery.
7. **Classify.** The source taxonomy has no approved Work Type/Class/Sub Class for this request. The case therefore cannot be closed automatically; it is handed to a supervisor for classification and stays *waiting on department*.

## Letters

Both letters are rendered by `name_change_letter` in `backend/app/response_validation.py`, using the client configuration in `data/fixtures/v1/clients.json`:

- **Information request.** Names only the missing item(s), lists acceptable legal documents, gives the reply and postal options and says that no change has been made yet. If the signed request is also missing, it asks for both documents as a two-item list.
- **Confirmation.** Addressed to the borrower by her new name. States the new and previous names and the completion date, notes that loan terms are unchanged, and explains that the deed and homeowners insurance are separate records.

Both letters end with the Northstar signature, a reference block (loan number, requested or current name, update reference) and the required notice.
