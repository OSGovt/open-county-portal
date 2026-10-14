# Texas state pack

`portal/statepacks/tx/pack.yaml`, edition 2026.10.

**Status: draft, not yet legally reviewed.** It was written from the cited
statutes and agency guidance, but no Texas county attorney has reviewed it.
Each county should have its county attorney review the fees, postings and
redaction rules before go-live, and the project welcomes a formal review
(see [Writing a state pack](writing-a-state-pack.md#rules)).

## What it sets up

**Counties: 7 offices.** County Clerk, District Clerk, Tax
Assessor-Collector, Justice of the Peace, Sheriff, Commissioners Court,
Environmental Health.

**14 services.** Property records search, certified copies, recording,
property tax payment, vehicle registration (hand-off to the state), vital
records, marriage licenses, jury service, court payments, e-filing (hand-off),
septic permits, public information requests, meetings and agendas, voter
information (hand-off).

**10 fee templates.** Recording (first and additional pages), records
management and records archive fees, copies and certification, all under
Local Government Code 118.011; and marriage licenses (with the Twogether in
Texas reduced fee), certified birth certificates and septic permits, which
are marked "confirm locally" because the pack doesn't cite a statute amount
for them (the septic permit amount is left at $0 for the county to enter). **Every fee must be confirmed by
the county against its adopted order;** amounts change by statute and by
commissioners court order.

**8 required online postings,** with the dashboard warning when one is
missing or late: meeting notices and agendas (Government Code 551.056), tax rate and
budget information (Tax Code 26.18), the proposed and adopted budget (Local
Government Code chapter 111), election office contact information and polling
places (Election Code 31.125), notices of election (Election Code 4.003 and
4.008), conflict of interest disclosures (Local Government Code 176.009),
Chapter 381 economic development agreements (Local Government Code
381.005(c)), and how to request public information (Government Code
552.234).

**Online records rules:**

- The notice Property Code 11.008(k) requires on an online real property
  records database (added by HB 4350, 2025).
- Redaction requests under Property Code 11.008(j) and Government Code
  552.117 and 552.1175: which fields can be hidden and which groups of people
  may ask.

**Public information:** the Texas Public Information Act's name and response
rule, shown on the request page.

**Card payments:** Local Government Code 132.002 and 132.003 (processing fee
set by commissioners court; vendor transaction fee pass-through) and 132.004
(dishonored payments).

**4 forms:** vital record request, marriage license application, jury summons
response, septic permit application.

**Special and school districts** get a simpler profile: a district office and
board, bill payment, meetings and agendas, and the postings that apply to
them.

## Sources

The pack lists its sources at the top of the file: Local Government Code
chapters 118 and 132, Property Code 11.008 as amended by HB 4350 (2025), the
Texas Administrative Code county website posting requirements, and
Government Code 551.056 as amended by HB 3440 (2023).

## Not covered

- County-specific fees adopted by commissioners court order
- Court costs (these come from the court case management system as bills;
  see [Moving your records](../admin/migration.md#part-2-bills))
- Property tax calculations (the appraisal district and tax office systems
  remain the source; the portal takes payments on their bills)
- E-recording submission (the pack records who may submit; the portal links
  to the county's e-recording vendor)

## Procurement note for Texas counties

The software is free, so there is nothing to bid for it. Paid implementation
or support services are a normal purchase under your county's procurement
rules (Local Government Code 262.023 sets the competitive bidding threshold
for counties; purchasing cooperatives can satisfy it). Ask your county
auditor or purchasing agent.

## Maintainer

Open. If you work with Texas county law or Texas county clerks, consider
maintaining this pack.
