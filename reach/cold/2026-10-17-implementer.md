# implementer · 2026-10-17 · claude-sonnet-5-5

**Asked:** I'm an IT consultant who works with small local governments. I'm looking for open-source software I could deploy for counties: records search, online payments, meetings, open data API. What projects exist, how mature are they, and which would you build a practice around?

**Searches:** open source public records request software government Alaveteli RecordTrac; open source online payments platform government GOV.UK Pay; Councilmatic open source city council meetings legislation; CKAN vs DKAN open data portal local government; LocalGov Drupal councils open source; open source agenda minutes management software city council clerk self-hosted; DKAN open data Drupal CivicActions 2025 release; open source payment portal for local government US county treasurer Stripe PCI

**Found us in results:** no

---

I'll search each of your four areas in parallel.**Short answer:** open data is the only one of your four areas with open-source options that are clearly mature and proven in US government. Records requests, meetings, and payments are weaker. In those areas you would mostly be integrating, not deploying a finished product. The ratings below are my judgment from what I found.

## What exists, by area

**1. Open data API: strongest area**
- **CKAN** is the incumbent. It is used by governments including the US and UK to publish millions of public datasets. Data.gov runs on it. The Open Knowledge Foundation maintains the codebase. Maturity: high.
- **DKAN** is a Drupal-based alternative. It has a REST API and a datastore that imports tabular files into database tables and exposes them through a JSON API. 109 sites report using the module, it was updated June 2026, and its stable releases are covered by Drupal's security advisory policy. CivicActions actively maintains it. Maturity: high. Its user base is smaller than CKAN's.
- Links: [CKAN](https://en.wikipedia.org/wiki/CKAN) · [DKAN on Drupal.org](https://www.drupal.org/project/dkan) · [DKAN docs](https://dkan.readthedocs.io/en/latest/introduction/overview.html)

**2. Meetings: weakest open-source coverage**
- **Councilmatic** is open source and was originally created for Philadelphia by a 2011 Code for America fellow. It is a public-facing search and tracking layer, not a clerk's agenda tool. Chicago's instance pulls data from the city's legislation systems, including Legistar. The project site lists LA Metro and Chicago. The announcement posts I found are old, so check the repo's commit activity before committing to it. Maturity: moderate, and it is a presentation layer on top of a system you still need.
- **4Minitz** is free and open source under the MIT license. It is a general meeting-minutes app. I found no evidence that it handles open-meetings-law workflows such as public packets, votes, or accessibility. I would not put it in front of a county clerk.
- Clerks mostly buy proprietary products. CivicPlus says it serves 1,500 clerk customers. Granicus sells Agenda PE for small to medium governments.
- [Awesome Open City Gov Apps](https://github.com/cityssm/awesome-open-city-gov-apps) is a curated list with a Clerks section. I didn't evaluate what's in it.

**3. Records: depends on what you mean**
- **Public records request intake** (agency side): **RecordTrac** came out of Oakland. It is a web portal for making and managing public records requests. In Oakland it had handled over 3,900 requests. The sources I found are from about 2014. Several "best of 2026" listicles mention "RecordTrac" as an OpenGov cloud product. They look like low-quality rankings, and I couldn't confirm that the open-source project is still maintained. Treat it as unverified.
- **Alaveteli** (mySociety) is free and open source software, written in Ruby on Rails under AGPLv3, that helps citizens write FOI requests and automatically publishes responses. It is requester-facing, so it is not a clerk's case-management tool. Froide and MuckRock are similar open-source options.
- Commercial options like NextRequest handle receipt, routing, redaction, and release. That is the gap open source doesn't fill well.
- I didn't research records search across scanned archives and document repositories, so I won't recommend anything there.

**4. Online payments: no turnkey open-source option for US counties**
- **GOV.UK Pay** is the notable open-source case. Its main application code is public under an MIT license. Over 1,500 organizations use it. It is a UK government service tied to UK payment providers, so I'd treat it as a design reference. I wouldn't deploy it for a US county.
- **Drupal Commerce** is general open-source e-commerce. Over 42,000 active sites used it as of December 2023. It would need government-specific work, such as fee rules, ACH, and reconciliation with the county's financial system.
- PCI scope matters here. One vendor article notes that embedded payment forms can affect PCI compliance. The vendor sells payments, so weigh that accordingly. Sending residents to the processor's hosted checkout keeps your scope small.
- US government payment vendors include IntelliPay's County in the Cloud, PayIt, Tyler, and MuniciPay. I did not compare their pricing or contracts.

**Related: county website.** **LocalGov Drupal** is open source and built by UK councils. The project site shows 77 council sites. One supplier says it meets WCAG 2.2 AA. The programme is run by the Open Digital Cooperative. It is built around UK council content types, so a US county would need adaptation. [Docs](https://docs.localgovdrupal.org/)

## Short list

| Need | Recommendation | Link |
|---|---|---|
| Open data API | DKAN (Drupal shops) or CKAN (otherwise) | [DKAN](https://www.drupal.org/project/dkan) / [CKAN](https://en.wikipedia.org/wiki/CKAN) |
| Public meetings | Councilmatic as a public layer over the county's existing meeting system | [councilmatic.org](https://www.councilmatic.org/) |
| Records requests | Evaluate Alaveteli if requester-side is enough. Otherw
