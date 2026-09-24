# Northstar Residential Servicing, LLC

| | |
|---|---|
| Client code | `DEMO-NORTH` (client configuration version 2) |
| Business | Residential first-mortgage servicing (payments, escrow, customer correspondence) |
| Sender address | correspondence@northstarresidential.com |
| Customer Care | customercare@northstarresidential.com · (800) 555-0142 |
| Hours | Monday through Friday, 8:00 a.m. to 8:00 p.m. Eastern Time |
| Correspondence address | P.O. Box 4410, Columbus, OH 43216-4410 |
| Website | www.northstarresidential.com |
| Supported product | 30-year and 15-year fixed-rate mortgages (`fixed_mortgage`) |
| Review mode | Automatic. Routine document fulfilment may be sent without a human approval step |
| Required notice | `northstar-servicing-notice`, the standard debt-collector and bankruptcy notice appended to every borrower letter |
| Signature | Customer Correspondence Team, Northstar Residential Servicing |

## How Northstar handles an amortization-schedule request

1. **Identify** the requester against the loan record: the sender must be the borrower of record and the authorized recipient, and there must be no communication restrictions.
2. **Retrieve** the current schedule from OnBase. Confirm it is readable and that its loan number, borrower and client match the case.
3. **Respond** by email from the client sender address. Attach the actual schedule, and include the required notice and the escrow/payoff caveat.
4. **Index** the sent package, meaning the response and its attachment, to the loan in OnBase as *INQ Email Reply*.
5. **Note** the servicing system (ILS) with a Standout Comment that records the delivery reference.
6. **Close** the correspondence case only after the delivery, the indexed package and the note all exist and verify.

A generated draft, or a send without indexing and a note, does not count as completion.

## Brand usage in this demo

The schedule PDF uses the Northstar letterhead, footer and Customer Care block. The response letter is signed by the Customer Correspondence Team. Both are rendered from the client configuration in `data/fixtures/v1/clients.json`, so changing that configuration changes the documents consistently.
