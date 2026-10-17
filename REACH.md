# Reach: who should find this project, and how we'll know

This file is the objective for the project's discoverability, the way the
live-check walk-through is the objective for its correctness. A weekly
measurement (`.github/workflows/reach-check.yml`, data in `reach/`) records
where the project stands; a weekly maintenance pass reads this file and that
data, makes one improvement, and writes what it did to `reach/log.md`.

Nothing here is a promise to anyone. It is a list of questions and the places
that should answer them.

## Who is looking

- A county or district clerk, treasurer, or tax office lead who has been told
  the website must be accessible, or who is tired of paying for a records
  portal that residents can't use.
- A county IT manager or the one-person IT shop at a small county, comparing
  vendor quotes.
- A city or special-district administrator with no IT staff at all.
- A civic-tech volunteer or a small consultancy that implements software for
  local governments (an "implementer").
- Open-data people at state agencies and Data.gov who want DCAT-US catalogs.

Most of them will ask a search engine or an AI assistant in plain words. The
assistant runs a web search and reads the pages it finds, so the project is
found when an indexed page answers the question in the asker's words.

## The questions they type

Each should be answered, in those words, by a page we control. "Answered by"
names the page that should rank; "status" is updated from `reach/` data.

| # | Question, as typed | Answered by |
|---|---|---|
| 1 | free open source county records portal | osgovt.com home; `README.md`; `docs/officials/README.md` |
| 2 | county website online payments records search open source | `README.md`; demo home |
| 3 | WCAG 2.1 AA accessible county website software | `ACCESSIBILITY.md`; `docs/officials/README.md` |
| 4 | ADA Title II website deadline county what do we need | `docs/officials/README.md` ("Why now") |
| 5 | replace county records vendor no license fee | `docs/officials/README.md`; osgovt.com/for-officials/ (cost table) |
| 6 | county open data portal DCAT-US Data.gov free | `docs/data/README.md`; `docs/admin/data-gov.md`; demo `/data` |
| 7 | counter point of sale software county clerk open source | `README.md`; `docs/staff/README.md` |
| 8 | install county portal one command Docker | `README.md` "Run it locally"; `docs/admin/install.md` |

Baseline, 2026-10-16 (web search, top ten results): no page from this
project appears for questions 1, 2, 3, or for the project's own name.

## Where it should be listed

Third-party listings are drafted into `reach/submissions/` and opened as a
GitHub issue for a human yes before anything is sent. The maintenance pass
never posts to another site on its own.

For people searching:
- Awesome lists: civic tech, govtech, open data, self-hosted software.
- Code for America brigade project directories; Civic Tech Field Guide.
- Data.gov / DCAT-US implementer lists; state open-data program pages.
- Docker Hub or GitHub Container Registry image page with a full description.
- Texas: TAC (Texas Association of Counties) and county clerks' association
  resource pages, only when there is a real, measured claim to make.

For agents consulting registries (verified to exist 2026-10-17; weights unknown):
- A `SKILL.md` in this repository that an agent can load to install and
  operate the portal, and a listing on skills.sh (`npx skills add`).
- `/.well-known/agent-skills/index.json` on osgovt.com, per Cloudflare's
  agent-skills discovery RFC, pointing at that skill.
- The MCP Registry and the ARD (Agentic Resource Discovery) registry for the
  public API, once an MCP server exists over the OpenAPI document. These are
  two separate registries with two submission paths.

## Cold discovery probe

`tools/cold_probe.py` (weekly, `.github/workflows/cold-probe.yml`) asks a
Claude model with web search the questions in `reach/personas.json`, in the
askers' own words and with no URL, and records in `reach/cold.csv` whether
any of our properties appeared, in `reach/harvest.csv` every query the
model ran, and in `reach/cold/` the answer a person would have read. This
is the adoption metric: the Sunday maintenance pass reads it first, and the
harvested queries are the words our titles and READMEs should use.

## Properties and what measures them

| Property | Role | Measured by |
|---|---|---|
| `github.com/OSGovt/open-county-portal` | the project | GitHub traffic API (nightly `docs/traffic/traffic.csv`; weekly referrers and paths in `reach/github.csv`) |
| `utopia.osgovt.com` | the live demo | Search Console and Bing Webmaster once verified; robots/agent access probe weekly |
| `osgovt.com` | project site (repository `OSGovt/osgovt.com`: home, For officials, For IT, Open data, `/llms.txt`) | Search Console Domain property `sc-domain:osgovt.com` (covers the demo too), Bing Webmaster, robots/agent access probe weekly. Live since 2026-10-17; before that the domain carried mail only. |
| `oscivic.com` | family home page | links here; measured in its own repository |

## Rules for the maintenance pass

1. One improvement per week, then stop. Indexing moves on a weeks scale;
   changing faster than we can measure is noise with commits attached.
2. Every factual claim on any page traces to a file in this repository
   (a test, a doc, a workflow). No compliance promises, no dates, no counts
   we didn't measure. If a claim can't be traced, it isn't written.
3. Measure before changing. Each `reach/log.md` entry records the probe
   results for the question it targets, so the next pass can tell whether the
   change did anything.
4. Prefer pages that answer a question over pages that describe the project.
5. Never post, submit or message outside this repository. Draft it, open an
   issue, wait.
6. Never add tracking scripts, cookies or third-party analytics to the portal
   to get a number. Search Console, Bing Webmaster and GitHub's own traffic
   API are the only measurement sources.
