# county-clerk · 2026-10-18 · claude-sonnet-5-5

**Asked:** I'm the county clerk in a Texas county of about 40,000 people. Our records search website is from a vendor, costs us every year, and people on phones can't use it. We've been told our website has to meet accessibility rules. Is there any free or open-source software that does county records search and online copies? Which would you recommend and how would we get it?

**Searches:** open source county clerk land records search software; ADA Title II web accessibility rule population under 50,000 deadline 2027; Texas county clerk official public records search vendor options Kofile Tyler Fidlar Texas counties; open source register of deeds recording software GitHub county recorder; Mayan EDMS open source document management government accessibility; Texas county clerk official public records search ADA accessibility WCAG vendor mobile responsive; Texas Association of Counties county clerk records search software TAC services; GovOS Cloud Search publicsearch.us county clerk Texas mobile accessible WCAG

**Found us in results:** no

---

**Short answer:** I didn't find any free or open-source system that does what a Texas county clerk needs. That means recording, indexing, a public search portal, and online copies with payment. A search can miss things, but I'd treat "free" as unlikely. The realistic goal is to replace or fix the public search front end and pay less for it.

## The deadline

- The DOJ's web accessibility rule requires WCAG 2.1 Level AA. It covers websites, mobile apps, and digital documents of state and local governments.
- DOJ extended the dates in April 2026. Entities under 50,000 now have until April 26, 2028. That covers your county.
- The extension doesn't remove your current duties. The ADA already prohibits disability discrimination in digital services, and the later date creates no safe harbor.
- The rule reaches vendor-run tools. It covers PDFs, online forms, and third-party platforms used to deliver public services.
- In Texas, the Commissioners Court is responsible for compliance. Take your vendor's accessibility problems to them.

## Options I found

**1. Mayan EDMS (free, open source)**
- It is a free and open source electronic document management system. It lists local, state, and national governments among its users.
- It is a document repository, not a land-records recording system. I found nothing showing it handles Texas recording workflows, grantor/grantee indexing, e-recording, or public sale of copies. Your county would have to build the public portal and payments, and meet WCAG itself.
- I couldn't verify its WCAG conformance.
- To get it: use the official repository, not the GitHub mirror, which is outdated. That is https://gitlab.com/mayan-edms/mayan-edms. The project says to deploy the official Docker Compose file. Docs are at https://docs.mayan-edms.com.
- It might suit secondary records such as commissioners court minutes. I would not use it as your official records system.

**2. GovOS Cloud Search (formerly Kofile), at publicsearch.us**
- It has a Google-like interface, with an advanced option for professional searchers. Full OCR search finds records from a text fragment.
- It has wide Texas use. GovOS's Texas list includes Anderson, Bell, Walker, Montgomery, Smith, and many other county clerks. You can look at live examples, such as https://walker.tx.publicsearch.us/ and https://anderson.tx.publicsearch.us/.
- Its other self-service features include certified copy requests. It also offers a free Property Alert fraud notice.
- Info: https://govos.com/products/cloud-search/
- It costs money. I found no pricing and no accessibility conformance report, so you'd need both from the vendor.

**3. Tyler Technologies' CountyGovernmentRecords.com (Texas portal)**
- It already hosts small Texas counties. Those include Caldwell, Hale, Jasper, Karnes, Van Zandt, and Waller.
- Users must register to search, and registration is free. Most counties charge a fee to view document images.
- The page I saw showed a 2022 software version. Check how current it is and how it performs on phones.
- Portal: https://tx.countygovernmentrecords.com/texas/web/. I couldn't confirm what it costs the county.

**4. Other vendors**
- A vendor-written article names Tyler, Cott Systems, and Kofile as the alternatives recorders most often evaluate. It is marketing, so treat it with caution.
- That same article warns about one cost. Counties that switch sometimes find they cancelled a revenue stream. Check whether your search subscriptions or copy fees pay for part of your current contract.

## What I'd do

I'd pick **GovOS Cloud Search as the first quote to get**, and I'd keep your current vendor in the negotiation. I'm choosing it because it is in use at many Texas county clerks' offices, so you can phone peers. It is also a pure public-search layer, and a modern one. I haven't verified that it meets WCAG, so don't assume it does.

Steps:
1. Ask your current vendor in writing for a WCAG 2.1 AA conformance report, a remediation date, and a price reduction if they miss it. A mobile-unfriendly site is a strong sign it doesn't conform.
2. Request quotes and accessibility reports from GovOS and Tyler.
3. Test any finalist on your own phone and with a screen reader before signing. Call clerks in Walker, Anderson, or Bell counties for references.
4. Call the Texas Association of Counties legal helpline, 888-ASK-TAC4. Ask about contract requirements and about using your county clerk records management and preservation fund. I didn't verify the statutory rules on fees, redaction, and state records requirements, so confirm those there.
5. Write accessibility into the contract. That means a WCAG 2.1 AA warranty, a conformance report, and remediation obligations.

I'd consider building your own portal only if you have developers, and I wouldn't recommend it. A vendor article puts a custom search portal at $45k to $110k. You would also own the accessibility compliance indefinitely.
