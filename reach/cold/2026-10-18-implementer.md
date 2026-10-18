# implementer · 2026-10-18 · claude-sonnet-5-5

**Asked:** I'm an IT consultant who works with small local governments. I'm looking for open-source software I could deploy for counties: records search, online payments, meetings, open data API. What projects exist, how mature are they, and which would you build a practice around?

**Searches:** open source local government meeting agenda minutes software Councilmatic; open source public records request software OpenRecords Alaveteli government; CKAN open data portal government adoption latest release; open source online payment portal for municipalities county government; DKAN open data Drupal status 2026; Councilmatic DataMade open source city council legislative tracking; Paperless-ngx vs Mayan EDMS document management open source records; open source payment portal government github civic tech Stripe PCI city

**Found us in results:** no

---

The short version is that open data is well covered by mature open-source projects. Records search is partly covered. Meetings and payments are weak spots, where I found nothing I'd recommend a county build on. I searched each area, but I haven't deployed any of this, and I'm giving you only the maturity signals I could verify.

## Open data and API (strongest area)

**CKAN**
- It's AGPL-licensed Python, and the stable release is 2.12.0 (26 August 2026).
- 2.12 is the last 2.x release and lays the groundwork for CKAN 3.0.
- It's used widely in government. Data.gov uses it. It supports the DCAT vocabulary.
- It's actively patched, with recent 2.11.5 and 2.10.10 releases fixing four security advisories.
- A UI revamp with WCAG 2.2 AAA accessibility is merged and targeted for release in 2026, with full integration in CKAN 3.0. This matters for ADA obligations.
- A commercial support ecosystem exists. Link Digital is an official co-steward.

**DKAN** (Drupal-based)
- 109 sites report using it. That's a much smaller footprint than CKAN.
- 4.1.2 is a stable release covered by the Drupal Security Team and works with Drupal 10.2 or 11.
- CivicActions has sponsored and maintained it since 2017.
- The datastore imports tabular files and exposes them through a JSON API.
- An access-bypass advisory was published on 7 October 2026. The fixes are 4.1.5 and 4.0.4. Patching works, but you need to track advisories.
- It's a good fit if the county already runs Drupal. Avoid DKAN 1.x, which is deprecated and unmaintained.

## Records search

This is a partial gap, and "records search" covers two different needs.

- **Public records requests.**
  - Alaveteli is AGPL Ruby on Rails software from mySociety. It has helped make over 1,000,000 requests in 25+ jurisdictions.
  - It is built for requester-facing sites. I didn't find evidence of agency-side redaction or workflow comparable to commercial tools.
  - RecordTrac was built in Oakland as a records request portal. That work is more than a decade old, and I couldn't verify that it's maintained.
  - The market leader, NextRequest, is now a CivicPlus product and is proprietary.
- **Searching the records themselves.**
  - Paperless-ngx is GPL v3 with about 44,700 GitHub stars and a commit within the last week.
  - It's best suited to individuals and small offices, and its sharing is limited.
  - Mayan EDMS adds a workflow engine and full audit trails. Its access controls go down to individual documents. It's Apache 2.0.
  - Alfresco Community is another enterprise-grade option.
  - These are back-office repositories. A public search front end is something you'd have to build.

## Meetings

I found no mature open-source tool for clerks to author and publish agendas and minutes. The products that came up are proprietary: eScribe, Municode Meetings and Catalis.

- **Councilmatic** is the main open-source option. It's a resident-facing tracker, not a clerk-side authoring tool.
  - It's deployed for LA Metro and Chicago. It's MIT-licensed.
  - It works by scraping the Legistar API. That makes it dependent on a proprietary vendor.
  - The Chicago repository's copyright notice runs only through 2023. I'd treat maintenance as DataMade-dependent.
- **4Minitz** is an MIT-licensed self-hosted minutes app. It isn't built for public bodies or for public posting, and I didn't verify that it's actively maintained.

## Online payments

I found no mature open-source county payment portal. The options I found:

- **LocalGov IMS** is an open-source income management system built by local government for local government. It includes a payment portal, admin and API, with a GOV.UK Pay integration. It's UK-oriented and has a small community, so a US county would need a new processor integration.
- **Hyperswitch** is open-source payments infrastructure with PCI-compliant SaaS and self-host options. It routes across Stripe, Adyen, Braintree and others. It's a general-purpose orchestrator with no property-tax or court-fee logic.
- Don't confuse these with the GitHub project named CivicPay. It states that it processes no real payments.
- Proprietary hosted options include Tyler Payments, InvoiceCloud (PCI Level 1) and Paymentus.

My view is that a small county shouldn't self-host card handling. The PCI scope and liability aren't worth it. That's my judgment, not something from a source.

## Short list

1. **CKAN** (https://ckan.org): open data portal and API. Mature, widely used and well supported.
2. **DKAN** (https://www.drupal.org/project/dkan): the alternative for Drupal shops.
3. **Mayan EDMS** (https://www.mayan-edms.com) or **Paperless-ngx** (https://github.com/paperless-ngx/paperless-ng
