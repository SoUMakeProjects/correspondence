# Correspondence thread — loan 0099000001

The full two-round thread from the live Mailbox rehearsal. Every outbound letter was rendered by the server from persisted records; the model chose only the structure (response type, concern dispositions and evidence-bound claims).

## 1. Inbound request

| | |
|---|---|
| From | Lauren Castellano &lt;lauren.whitaker@outlook.com&gt; |
| To | Northstar Residential Servicing &lt;correspondence@servicing.example.com&gt; |
| Date | Thu, 17 Sep 2026 10:30:00 -0400 |
| Subject | Name change request – loan ending 0001 |
| Attachments | Signed-Name-Change-Request.pdf (1 page; her signed and dated letter) |

```text
Hello,

I was recently married and would like to update the name on my mortgage account. My name is changing from Lauren E. Whitaker to Lauren E. Castellano. The loan number is 0099000001, for the property at 2214 Bramblewood Drive, Upper Arlington, OH 43221.

I've attached a signed and dated letter requesting the change. Please let me know if you need anything else from me to get this done.

Thank you,
Lauren Castellano (formerly Whitaker)
(614) 555-0182
```

## 2. Outbound information request (live agent run 1)

| | |
|---|---|
| From | Northstar Residential Servicing &lt;correspondence@northstarresidential.com&gt; |
| To | "Lauren E. Whitaker" &lt;lauren.whitaker@outlook.com&gt; |
| Date | Tue, 22 Sep 2026 09:10:00 -0400 |
| Subject | RE: Name change request – loan ending 0001 |
| Attachments | None |
| Delivery reference | DEMO-DELIVERY-4702ffc5-a288-46b1-a87a-bd35b5c85abd |

```text
Dear Lauren E. Whitaker,

Thank you for contacting Northstar Residential Servicing. We received your request on September 17, 2026 to change the name on your mortgage loan ending in 0001 from Lauren E. Whitaker to Lauren E. Castellano.

Thank you for including your signed and dated request, dated September 16, 2026. Before we can update our records, we also need a copy of a legal document that shows your name change, such as a marriage certificate or marriage record, a divorce decree, or a court order for a name change.

You can reply to this email and attach a clear, complete copy, or mail a copy to Northstar Residential Servicing, LLC, Attn: Customer Correspondence, P.O. Box 4410, Columbus, OH 43216-4410. Please include your loan number with anything you send, and please do not send original documents.

We have not changed the name on your loan yet. When we receive the document, we will review it, update our records and confirm the change to you in writing. Your loan terms, monthly payment and due date are not affected, so please continue to make your payments as scheduled.

If you have questions, please reply to this email or call Customer Care at (800) 555-0142, Monday through Friday, 8:00 a.m. to 8:00 p.m. Eastern Time.

Thank you for choosing Northstar Residential Servicing.

Sincerely,
Customer Correspondence Team
Northstar Residential Servicing

Requested name: Lauren E. Castellano
Loan number: 0099000001

Northstar Residential Servicing, LLC is a debt collector. This communication is an attempt to collect a debt, and any information obtained will be used for that purpose. If you are a debtor in bankruptcy or have received a bankruptcy discharge of this debt, this communication is provided for informational purposes only and is not an attempt to collect a debt from you personally.
```

## 3. Borrower reply with the legal document

| | |
|---|---|
| From | Lauren Castellano &lt;lauren.whitaker@outlook.com&gt; |
| To | Northstar Residential Servicing &lt;correspondence@servicing.example.com&gt; |
| Date | Tue, 22 Sep 2026 11:32:00 -0400 |
| Subject | Re: Name change request – loan ending 0001 |
| Attachments | Marriage-Record-Certified-Copy.pdf (1 page) |

```text
Hello,

Thank you for getting back to me. I've attached a certified copy of our marriage record from the Probate Court of Linden County. It shows my name change from Lauren E. Whitaker to Lauren E. Castellano.

Please go ahead and update the name on loan 0099000001. Let me know if you need anything else.

Thank you,
Lauren Castellano
(614) 555-0182
```

## 4. Outbound confirmation (live agent run 2)

| | |
|---|---|
| From | Northstar Residential Servicing &lt;correspondence@northstarresidential.com&gt; |
| To | "Lauren E. Castellano" &lt;lauren.whitaker@outlook.com&gt; |
| Date | Tue, 22 Sep 2026 12:05:00 -0400 |
| Subject | RE: Name change request – loan ending 0001 |
| Attachments | None |
| Delivery reference | DEMO-DELIVERY-5a7f9de5-3537-4ee8-a35f-0193321ae947 |

```text
Dear Lauren E. Castellano,

Thank you for sending the documents we requested. We have reviewed your signed request and the supporting legal document, and we have updated the name on your mortgage loan ending in 0001.

Our records now show your name as Lauren E. Castellano, replacing Lauren E. Whitaker. The change was made on September 22, 2026. Your future statements, letters and year-end mortgage interest statement will be issued in your new name.

This change does not affect your loan terms, interest rate, monthly payment or due date, and no further action is needed from you. It updates your loan servicing records only. It does not change the name on your property deed or on your homeowners insurance policy; to update those, please contact your county recorder's office and your insurance provider.

If you have questions, please reply to this email or call Customer Care at (800) 555-0142, Monday through Friday, 8:00 a.m. to 8:00 p.m. Eastern Time.

Thank you for choosing Northstar Residential Servicing.

Sincerely,
Customer Correspondence Team
Northstar Residential Servicing

Loan number: 0099000001
Name on loan: Lauren E. Castellano
Name change reference: DEMO-NAME-24129e1c-f924-4575-b53d-219835096d40

Northstar Residential Servicing, LLC is a debt collector. This communication is an attempt to collect a debt, and any information obtained will be used for that purpose. If you are a debtor in bankruptcy or have received a bankruptcy discharge of this debt, this communication is provided for informational purposes only and is not an attempt to collect a debt from you personally.
```

## 5. Servicing notes (ILS, Standout Comments)

One *INQ Email Reply* note per delivery, each carrying the delivery reference and the exact letter. See [`05-servicing-notes.txt`](05-servicing-notes.txt).

## 6. What happens after the confirmation

Both letters are sent, indexed and noted, and the name on the loan is changed, but the CCT case is **not closed**. The source taxonomy has no approved Work Type/Class/Sub Class for an ordinary name change (`classification_mapping_missing`), so the agent records a department handoff and the case waits on a supervisor's classification decision (**Waiting on department**). This is the intended end state for this demo.

Raw files: [`01-inbound-request.eml`](01-inbound-request.eml), [`02-outbound-information-request.eml`](02-outbound-information-request.eml), [`03-inbound-reply.eml`](03-inbound-reply.eml), [`04-outbound-confirmation.eml`](04-outbound-confirmation.eml), [`05-servicing-notes.txt`](05-servicing-notes.txt).
