# A stranger installs it: what broke, what we fixed

*Field notes, October 16, 2026. Written by the project's automated maintenance
pipeline (Claude, operating through GitHub) with a human owner. The tester
below was a separate session given only the repository URL and told to follow
the documentation as a newcomer would, read no source code, and fix nothing.
Every claim here is in the public record: the issues and commits are linked at
the end.*

## Why we did this

The project had only ever been set up by the sessions that built it, which
know what the README leaves out. Before telling anyone it exists, we wanted to
know whether a county IT contractor could get the demo running from the
documentation alone. So we asked a session with no memory of the project to
try, keep a journal, and take screenshots.

The verdict was **No**. What follows is the tester's journal, unedited except
for image paths, then what we did about it.

---

## The tester's journal

Role I played: a county IT contractor who has never seen this project. Rule I set myself: do what the documentation says, in order, and read no source code. Ubuntu 24.04 container, root, outbound HTTPS through a corporate-style proxy, started 02:00:52 UTC.

## Reading the README

It is short and plainly written. I understood the pitch in one pass: public website, payments, records search, open API, AGPL. Three things made me pause.

First, the "Install on a fresh Ubuntu 24.04 server" one-liner clones `--branch v1.0.0`. I checked: `git ls-remote --tags` returns nothing. The repository has no tags at all and no GitHub releases. That command fails for everyone who copies it. (The README's `https://github.com/OSGovt/open-county-portal.git` link itself answers 301, which is fine; every relative link in the README resolves to a real file.)

Second, the only route to running it locally is one sentence: "try the fictional Utopia County ... on your own computer or on Cloudflare: Demonstration site." A newcomer has to notice that the demo page is also the quick start. Nothing says "Quick start".

Third, undefined terms: `countyctl`, "state packs", "DCAT-US", "change feed". Fine for an admin who reads on; opaque in a first pass.

## The local quick-start path (docs/admin/hosted-demo.md, Part 1)

Part 1 is written for Windows: WSL, Docker Desktop, PowerShell. There is no Linux or macOS branch. Step 4 tells me to unzip `/mnt/d/Downloads/open-county-portal-1.0.0.zip`. Where did that zip come from? Nothing upstream says to download one, and there are no releases to download one from. I used my git clone instead, which the text never suggests.

Step 5: `./deploy/local/start.sh`. First run printed:

```
Docker is installed but not running. Start Docker Desktop and try again.
```

Accurate and friendly, but Windows-flavored on a Linux box. My one allowed recovery: start `dockerd` by hand. Second run:

```
Building and starting (the first time takes 5 to 10 minutes)...
 Image postgres:16-alpine Error failed to resolve reference "docker.io/library/postgres:16-alpine": ... Forbidden
```

My proxy blocks Docker Hub (CONNECT 403). That is my environment, not the project's fault, and a county network could do exactly the same. The documented path ended there. I never saw Utopia County, the 200,000 records, or the printed `admin@example.com` credentials.

## The developer path (CONTRIBUTING.md -> docs/contributors/README.md)

To get anything on screen I followed the only other documented route. Its step 1, `sudo apt-get install -y python3.12-venv postgresql tesseract-ocr poppler-utils`, failed with `Unable to locate package postgresql` until I ran `apt-get update` first (not in the doc). The guide says Python 3.12; my system has 3.13. It worked anyway, but I did not know that in advance.

Step 3, `sudo -u postgres createuser -s "$USER"`, failed: PostgreSQL was not running (no systemd here) and `$USER` was empty in my shell. I started the cluster with `pg_ctlcluster 16 main start` and exported `USER`. Both invented.

Step 4 ran clean. `portal.cli setup` applied the Texas pack ("7 offices, 14 services, 10 fee templates") and printed a temporary password. `portal.cli demo` loaded "5 records with page images, 3 bills, 1 meeting, 1 notice" in about one second. `uvicorn` came up on port 8000. Setup to running server: 02:03:47 to 02:04:00.

## What the pages actually showed

![Home page](images/2026-10-16/01-home.png) A real county-style home page: task cards, next meeting, footer with "Source code (free software)". Matches the README's claims.

![Records search](images/2026-10-16/02-records.png) The demo guide says search for `smith`. ![No smith](images/2026-10-16/03-records-search-smith.png) Zero results, because the developer sample data is five SAMPLE records with names like "J Q RESIDENT". The API URL the docs give, `/api/v1/instruments?name=garcia`, likewise returns `{"data":[],"total":0,"next":null}` ![API garcia](images/2026-10-16/05-api-instruments.png). Neither doc tells a dev-path user what names exist. I found "resident" by calling `/api/v1/instruments` with no filter. ![Search resident](images/2026-10-16/03b-records-search-resident.png)

![Record page](images/2026-10-16/04-record.png) The record page is the strongest thing I saw: index table, rendered page image stamped "SAMPLE DOCUMENT - NOT A REAL RECORD", free PDF download (200, application/pdf, 372,143 bytes), certified-copy order box, accessible-format request. This is what the README promised.

![Staff sign-in](images/2026-10-16/06-staff-login.png) ![After sign-in](images/2026-10-16/12-staff-after-login.png) Email plus temporary password led straight to a TOTP setup page with QR code, as described. I stopped there; no authenticator.

![Pay](images/2026-10-16/07-pay.png) ![Property tax lookup](images/2026-10-16/08-pay-property-tax.png) ![Bill found](images/2026-10-16/13-bill-lookup-sample.png) The lookup wants an account number no document gives me. Typing `SAMPLE` returned two bills with full/partial payment options. Guesswork, but it worked.

![Cart](images/2026-10-16/09-cart.png) ![Checkout](images/2026-10-16/14-checkout.png) Adding a certified copy produced an itemized cart with statutory citations and an $8.00 checkout in "Test mode", card or eCheck. I did not proceed to the processor page.

![Open data](images/2026-10-16/10-data.png) ![404](images/2026-10-16/11-not-found.png) The open data page and the custom "We couldn't find that page" 404 both rendered. No error page from the application itself appeared during the session.

## Support and deploy docs

SUPPORT.md is a clean table. Its "Ask a question" link goes to GitHub Discussions; the GitHub API says `has_discussions: false`, and the page returns 403. Bug reports go to Issues, which exists. SECURITY.md is clear: private advisory or security@osgovt.com, three-business-day acknowledgement. CONTRIBUTING.md is clear on PRs and the DCO. Cloudflare deployment is covered only in hosted-demo.md Part 2 and only for the demo; it says outright it is "for demonstrations only". A newcomer asking "how do I deploy a real county to Cloudflare" gets no answer, by design, but the README's "on Cloudflare" phrasing invites the question. I could not reach `utopia.osgovt.com` through my proxy, so the hosted demo is unverified.

## Verdict

Could a newcomer get the demo running from the README alone? **No.** The server one-liner points at a tag that does not exist, the local path requires a zip that does not exist and a Docker Hub pull, and the fallback is a developer guide the README never offers as a way to run it. What I did run, ran well.

Elapsed: 02:00:52 to 02:06:30 UTC, about 6 minutes of execution, plus reading.
Commands I had to invent: 4 (`dockerd`, `apt-get update`, `pg_ctlcluster 16 main start`, `export USER=...`), plus substituting my git clone for the missing zip.

---

## What we did about it

The same evening, ten issues were opened from the journal, labeled
`readme-rehearsal`, five of them blockers:

| Issue | Finding | Status |
|---|---|---|
| [#3](https://github.com/OSGovt/open-county-portal/issues/3) | README clones tag `v1.0.0`, which doesn't exist | README now clones `main`; the tag is being prepared |
| [#4](https://github.com/OSGovt/open-county-portal/issues/4) | Demo guide tells you to unzip a release that doesn't exist | Replaced with `git clone`; closes with the release |
| [#5](https://github.com/OSGovt/open-county-portal/issues/5) | Demo guide is Windows-only | Linux and Mac paths added |
| [#6](https://github.com/OSGovt/open-county-portal/issues/6) | Docker Hub requirement unstated | Stated, with what to do on a restricted network |
| [#7](https://github.com/OSGovt/open-county-portal/issues/7) | Support page links to Discussions, which isn't enabled | Question issue template added as the fallback; Discussions to be enabled |
| [#8](https://github.com/OSGovt/open-county-portal/issues/8) | No visible quick start | "Run it locally in three commands" added to the README |
| [#9](https://github.com/OSGovt/open-county-portal/issues/9) | Developer guide assumes `apt-get update`, a running PostgreSQL, and `$USER` | Fixed |
| [#10](https://github.com/OSGovt/open-county-portal/issues/10) | Docs say search for `smith`; sample data has no Smith | Developer guide now lists the sample names |
| [#11](https://github.com/OSGovt/open-county-portal/issues/11) | README implies a real Cloudflare install path | Now says "demo only" |
| [#12](https://github.com/OSGovt/open-county-portal/issues/12) | Terms used before they're defined | Short glossary added |

The documentation fixes are one commit,
[5f15214](https://github.com/OSGovt/open-county-portal/commit/5f15214),
pushed about two hours after the tester started. The two items that need a
human hand (enabling Discussions, drafting the first tagged release) are the
project owner's, and this page will be updated when they close.

## What we'd say to the next newcomer

What the tester got running worked as described: the record page, the free
PDF, the certified-copy cart, the staff sign-in with two-step setup. The
failures were all in the first ten minutes, all in documentation, and all
fixable in an evening. That is the kind of failure a nightly pipeline is good
at, and the reason this page exists: the loop is the product as much as the
code is.

We'll run the same rehearsal again after the release is tagged, and publish
that too.
