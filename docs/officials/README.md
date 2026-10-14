# For elected officials and department heads

## In one paragraph

Open County Portal is a complete public website for a county, city or
special district: services, offices, meetings and notices, property records
search with free copies, online payments for taxes, court costs, utilities
and fees, a counter point-of-sale for cashiers, online forms, and public
information requests. It meets the federal accessibility standard, works on
any phone, and publishes all public data free through an open API that
Data.gov lists nationally. It's free, open-source software: there is no
license fee, ever, and no vendor can take it away.

## Why now

**Federal accessibility deadline.** The Department of Justice's ADA Title II
rule requires government websites and online services to meet WCAG 2.1 Level
AA. Under the April 2026 interim final rule, the compliance date is **April
26, 2027** for governments of 50,000 people or more, and **April 26, 2028**
for smaller governments and for every special district. Many existing county
websites and records systems don't meet the standard, and retrofitting them
is often impractical. The portal was built to meet it from the start, and
every release is checked automatically.

**Residents expect to do business online,** on a phone, at any hour.

**Open data.** Publishing public records data in standard formats is
increasingly expected by residents, the press and other agencies, and it
reduces routine records requests.

## What it costs

| Item | Cost |
|---|---|
| The software | Free. No license, subscription or per-transaction fee to the project |
| A server | Your own hardware, or a cloud server; roughly $50 to $250 a month for most counties (a rough estimate; it depends on provider and the size of your records) |
| Staff time | Your network administrator: a few days to install and set up, then about an hour a week. Each office: a few hours of training and content review |
| Moving records | Usually staff time; sometimes a fee from your current records vendor to export your data |
| Card payments | Your payment processor's fees, as today. Many states let you recover them with a processing fee your governing body adopts |
| Optional help | Independent implementers can do the setup, migration and training for you, at whatever price you agree. Nothing requires one |

## What happens to what you have now

Nothing, until you choose. The portal runs on its own server. Your current
website and records system keep running, unchanged, while staff train and
records are copied over. On go-live day, the web address is pointed at the
new portal, and it can be pointed back the same day. The old system stays
available for months afterward.

Every import from the old system can be undone, every update can be undone,
and every design change can be undone. The project was designed around one
idea: no one should be afraid to make the change.

## Who controls it

You do. It runs on servers you control, with your data in a standard database
you can export at any time. The source code is public under the GNU Affero
General Public License: you may use, change and share it freely. If anyone
changes it and runs it for the public, they must offer their changes to the
public too; the portal does that automatically with a "Source code" link in
its footer. No company can make the software proprietary, and no vendor can
hold your data hostage.

## Decisions for your governing body and offices

Before go-live, some decisions are yours, not IT's:

- **Fees.** Confirm every fee in the portal against your adopted fee
  schedule. The portal won't let you go live until each one is confirmed.
- **Card processing fee.** Whether to charge one, and adopting it if state
  law requires.
- **Payment processor.** Use your current one if an adapter exists for it, or
  choose one.
- **Data license.** The terms under which the public may reuse your data. A
  public-domain dedication is simplest; your attorney decides.
- **Accessibility contact.** Who residents contact about a barrier, and how
  quickly they'll get an answer.
- **Records online.** Your state's rules on what may appear online and who
  may ask for information to be hidden; your clerk and attorney confirm the
  state pack's rules.
- **Content ownership.** Each office owns and keeps current its own pages.

## Procurement

The software itself is free, so there's nothing to purchase or bid. If you
hire an implementer for setup, migration, training or support, that's an
ordinary purchase of services under your procurement rules. Purchasing
cooperatives may help where your state allows them. Ask your purchasing agent
or auditor.

## A typical timeline

Estimates for a mid-sized county with one administrator; yours will vary.

| Phase | Time |
|---|---|
| Install, set up, train staff with sample data | 2 to 4 weeks |
| Move records, bills and old web pages; offices review content | 4 to 12 weeks, mostly waiting on exports and reviews |
| Accessibility testing, go-live checklist | 1 to 2 weeks |
| Go live, with the old site kept running in the background | 1 day |

## Questions to ask an implementer

- How many installations have you done, and may we call those counties?
- Will you run the conformance suite and give us the report?
- Will you contribute fixes and payment adapters you write back to the
  project, so we're never dependent on you?
- What exactly will our staff do, and how much of their time will it take?
- What does ongoing support cost, and what happens if we stop paying? (The
  answer should be: the site keeps running, and our administrator can
  maintain it.)

## Where to go next

- Your network administrator: [Administrator guide](../admin/README.md)
- Your staff: [Staff guide](../staff/README.md)
- Implementers: [Implementer guide](../implementers/README.md)
