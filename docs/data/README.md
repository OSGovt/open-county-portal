# Using the open data

Every government running Open County Portal publishes the same free API,
the same daily bulk files and the same catalog format. Code you write for one
county works for all of them.

Everything here is free. No account, key, fee or contract is required.

## Where to start

Replace `portal.example-county.gov` with the county's portal address.

| What | Address |
|---|---|
| API index | `https://portal.example-county.gov/api/v1` |
| Full API reference (OpenAPI 3) | `https://portal.example-county.gov/api/v1/openapi.json` |
| Daily bulk files | `https://portal.example-county.gov/api/v1/bulk` |
| Change feed | `https://portal.example-county.gov/api/v1/changes?since=2026-10-01T00:00:00Z` |
| Data catalog (DCAT-US 3.0) | `https://portal.example-county.gov/data.json` |
| Data catalog (DCAT-US 1.1) | `https://portal.example-county.gov/data-v1.1.json` |
| Plain-language page | `https://portal.example-county.gov/data` |

The OpenAPI document is generated from the running code, so it's always
exact for that portal's version. Load it into any OpenAPI tool to browse or
generate a client.

## Endpoints

All are `GET`, return JSON, and allow cross-origin requests from any website.

| Endpoint | Returns | Parameters |
|---|---|---|
| `/api/v1/instruments` | Recorded documents (deeds, liens, plats) | `name`, `role` (`any`, `grantor`, `grantee`), `doc_type`, `recorded_from`, `recorded_to` (YYYY-MM-DD), `property_id`, `updated_since`, `limit` (up to 200), `page` |
| `/api/v1/instruments/{number}` | One document with its page images, image checksums and machine-read text | |
| `/api/v1/meetings` | Meetings with agendas and minutes | `updated_since`, `limit` |
| `/api/v1/postings` | Public notices | `updated_since` |
| `/api/v1/fees` | Current and scheduled fees with their legal authority | |
| `/api/v1/services` | Services residents can use | |
| `/api/v1/offices` | Offices, hours and contacts | |
| `/api/v1/pages` | Published information pages, in Markdown | |
| `/api/v1/public-information` | Released public information responses | |
| `/api/v1/changes` | Everything created, changed or removed since a time | `since` (required), `limit` |
| `/api/v1/bulk` | The bulk file manifest | |

Lists come in this shape:

```json
{"data": [ ... ], "total": 5, "next": "https://portal.example-county.gov/api/v1/instruments?limit=50&page=2"}
```

Follow `next` until it's `null`.

## Examples

Documents where SMITH is a grantor, recorded in 2025:

```
curl "https://portal.example-county.gov/api/v1/instruments?name=smith&role=grantor&recorded_from=2025-01-01&recorded_to=2025-12-31"
```

One document with its pages:

```
curl "https://portal.example-county.gov/api/v1/instruments/2026-004812"
```

Each page image URL serves the image as residents see it, with any lawful
redactions applied. Each `sha256` lets you confirm a downloaded image is
unaltered.

## Staying in sync

1. Download the bulk files once.
2. Then poll the change feed, daily or hourly, with the time of your last
   sync:

```
curl "https://portal.example-county.gov/api/v1/changes?since=2026-10-13T00:00:00Z"
```

Each entry has a `type` (`instrument`, `meeting`, `posting`, `service`,
`office`, `fee`), an `id`, a `change` (`upsert` or `delete`) and a time.
Fetch upserted items from their endpoint; remove deleted ones. A document that
becomes restricted, or a notice, service, office or meeting that stops being
public, appears as a `delete`.

## Bulk files

`/api/v1/bulk` lists the files made each night: what's in each, its size,
row count and SHA-256 checksum, and when the set was generated.
Instruments come as CSV and JSON Lines; everything else as JSON. Downloads
have no rate limit.

## Rate limits

The live API allows a set number of requests per minute from each address,
120 by default (each portal shows its own limit on its `/data` page). Over
the limit, you get HTTP 429 with a `Retry-After` header; wait and retry.

Need more? Ask the county for a free key (contact on the `/data` page) and
send it in the `X-API-Key` header. Keys only raise the limit; all data is
available without one. For large jobs, the bulk files are faster anyway.

## What's never published

Staff accounts, payments, residents' uploads and requests, documents that
are sealed or confidential by law, and anything hidden by a redaction. The
machine-read text of a redacted page comes from the redacted image, not the
original.

## Official copies

Data from the API is not a certified copy. Certified copies are ordered from
the county; each certified PDF has a verification code anyone can check at
`/verify/{code}` on that county's portal.

## Many counties at once

Each portal's `/data.json` is harvested by Data.gov, so
[catalog.data.gov](https://catalog.data.gov) is a good place to find portals.
Because the API is the same everywhere, a single script can read many
counties: loop over their addresses.
