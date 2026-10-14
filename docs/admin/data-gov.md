# Register with Data.gov

The portal publishes all of your public data for free:

- **An open API** at `/api/v1`: no key, no sign-up, no charge. Free keys are
  available only to raise the rate limit.
- **Daily bulk files** at `/api/v1/bulk`, with checksums, for anyone who wants
  everything at once.
- **A change feed** at `/api/v1/changes`, so others can stay in sync without
  downloading everything again.
- **A data catalog** at `/data.json` in the DCAT-US 3.0 format Data.gov reads,
  and at `/data-v1.1.json` in the older DCAT-US 1.1 format it still accepts.

Data.gov, the federal government's open data catalog, lists state, local and
tribal data as well as federal data, by reading ("harvesting") a catalog
file like yours on a schedule. Registering puts your county's data in front
of researchers, journalists, title companies and developers nationwide.

## 1. Fill in the catalog details

**Settings > Payments, records and open data > Open data.**

| Field | What to enter |
|---|---|
| Data terms | A sentence on how the data may be used. For example: "Free to use for any purpose. Official copies are available from the County Clerk." |
| License address | For a public-domain dedication: `https://creativecommons.org/publicdomain/zero/1.0/`. Ask the county attorney which your county prefers |
| Open data contact name | An office or role, such as "County Clerk's Office" |
| Open data contact email | A monitored address. **Required by Data.gov** |

Save.

## 2. Check the catalog

Open `https://portal.example-county.gov/data.json` in a browser. You should
see your datasets, each with your contact email.

Run the catalog part of the conformance suite, from its `conformance` folder
(setup is in [Accessibility testing](accessibility-testing.md#part-1-automated-check)):

```
.venv/bin/python run.py --url https://portal.example-county.gov --only catalog,api,bulk
```

It should show no failures.

## 3. Check whether your government already has a harvest source

Search for your government's name at
[harvest.data.gov](https://harvest.data.gov). If a source already exists (for
example, from a previous open data portal), you'll ask for a change to its
address instead of a new one.

## 4. Submit the request

Use the Harvest.data.gov setup or modification form, linked from Data.gov's
guide [How to get your open data on Data.gov](https://resources.data.gov/resources/data-gov-open-data-howto/).

| Form field | What to enter |
|---|---|
| Your name and email | Use your government email address |
| Organization | Your government's name |
| Source name | Letters and hyphens only, such as `example-county-tx-json` |
| Source URL | `https://portal.example-county.gov/data.json` |
| Notification emails | The open data contact email |
| Harvest frequency | Daily |
| Schema type | DCAT-US (JSON) |
| Source type | Document (single file) |

Questions or status: DataGovHelp@gsa.gov.

## 5. Confirm it worked

After the first harvest, search [catalog.data.gov](https://catalog.data.gov)
for your county's name. Your datasets should appear with your contact
details.

Mark "The Data.gov harvest request was submitted" on the go-live checklist.

## What's in the catalog

| Dataset | Source in the portal |
|---|---|
| Real property records index | recorded instruments that aren't restricted, with names, dates and legal descriptions, and links to page images |
| Meetings and agendas | posted meetings, agendas and minutes |
| Public notices | posted notices |
| Fee schedule | current and scheduled fees, with the order or statute for each |
| Services directory | services offered to residents |

Nothing private is ever in the API, the bulk files or the catalog: staff
accounts, payments, uploads, requests, restricted documents and redacted
areas of page images are excluded.

## Telling people about it

The public **Open data** page (`/data`) explains the API and bulk files in
plain language and links to the full API reference generated from the
running code (`/api/v1/openapi.json`). Point local developers and the press
to it. The [data users' guide](../data/README.md) can be shared as is.

Next: [Go-live checklist and cutover](cutover.md).
