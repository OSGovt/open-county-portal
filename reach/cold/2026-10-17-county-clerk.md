# county-clerk · 2026-10-17 · claude-sonnet-5-5

**Asked:** I'm the county clerk in a Texas county of about 40,000 people. Our records search website is from a vendor, costs us every year, and people on phones can't use it. We've been told our website has to meet accessibility rules. Is there any free or open-source software that does county records search and online copies? Which would you recommend and how would we get it?

**Searches:** open source county clerk official records search software; ADA Title II web accessibility rule deadline population under 50,000 2027; Texas county clerk records management software vendors online records search copies; Texas county clerk land records open source OR free software GitHub; open-source document management for county recorder deeds records GitHub self-hosted; publicsearch.us Kofile county clerk official records Texas mobile accessible; Texas county clerk records software vendors list CountyFusion Tyler Kofile Fidlar iDocket Texas Association of Counties; Texas county clerk records archive fee online access Local Government Code 118 records management preservation fund

**Found us in results:** no

---

**Short answer:** I found no free or open-source system built for Texas county clerks that covers recording, indexing, public search and online copies. Generic open-source document systems exist, but I wouldn't use one as your public records site.

## Accessibility deadline
- DOJ's rule requires WCAG 2.1 Level AA. Entities of 50,000 or more now have until April 26, 2027. Smaller entities have until April 26, 2028. A 40,000-person county falls in the later group.
- The rule also covers PDFs, online forms, and third-party platforms used to deliver public services. Your vendor's portal is therefore your responsibility.
- I didn't verify any Texas-specific state accessibility requirements. Ask your county attorney about those.

## Open-source options
- **Mayan EDMS** is described as enterprise-grade, with electronic signatures, versioning, metadata types and audit trails. Its GitHub page says the mirror is no longer maintained and is very outdated, and points to the official GitLab repository. Use GitLab: https://gitlab.com/mayan-edms/mayan-edms
- **Paperless-ngx** is strong for scanning and automated tagging, but is aimed at small teams. https://github.com/paperless-ngx/paperless-ngx
- **Teedy** is a lightweight open-source document management system and was tested to one million documents. https://github.com/sismics/docs

These are back-office filing tools. None of the sources I found say they handle recording workflows, grantor/grantee indexing, e-recording, fee collection, redaction, or certified electronic copies. None claim WCAG conformance or a mobile public portal. You would be building and maintaining the public site yourself and carrying the accessibility liability. For a 40,000-person county, I'd expect that to cost more than it saves.

## Commercial options used in Texas
- **Kofile PublicSearch.** Many Texas counties use it, including Walker County, with index-only or full-text OCR search, and Medina County. https://www.kofile.com
- **Tyler Records Public Access.** It lets constituents search, download, retrieve, and purchase documents independently and offers electronic certified copies. https://www.tylertech.com/products/enterprise-records-management/records-public-access
- **Granicus govRecords.** It stores land records and vital records, with e-recording support. https://granicus.com/product/land-official-records-govrecords/
- **Fidlar (AVA).** Galveston County's portal runs on it. I didn't find a product page, so ask for a demo. https://ava.fidlar.com

I couldn't confirm pricing, WCAG conformance, or mobile quality for any of these. Ask each vendor for a current Accessibility Conformance Report (VPAT) and test the portal on a phone with a screen reader.

## A cheaper path
Texas law lets the records management and preservation fee fund "specific records management and preservation, including for automation purposes." That may help pay for a replacement without using general funds. Confirm this with your auditor and commissioners court.

I'd skip free aggregators like TexasFile. Searching is free, but premium searches and documents are sold per item. It's a third-party site, not your official portal, and it doesn't fix your own accessibility obligation.

## What I'd do
1. Ask your current vendor in writing for its accessibility report and a date for a WCAG 2.1 AA, mobile-friendly portal. Since the vendor's site counts as yours, put this in the contract.
2. Request quotes and VPATs from Kofile and Tyler, and ask your Texas peers how they like them.

**My pick is Kofile PublicSearch**, provided its conformance report holds up. It's widely used in Texas, including by small counties. The county pages I saw include "skip to main content" links, which suggests some attention to accessibility, though that is weak evidence. If its report is thin, Tyler is the fallback. I'd choose a Texas-proven commercial portal over open source because it's the lower-risk way to meet the 2028 deadline.
