# Administrator guide: start here

This guide takes one network administrator from an empty server to a live
portal, with no outside help. Every step says what to type, what you should
see, and how to undo it.

You need:

- a server or virtual machine you can reach with SSH (see [Server size](sizing.md))
- the ability to change your organization's DNS, or someone who can
- about two hours for the install and first setup, plus time to move records

You don't need to know Python, Docker or PostgreSQL. The `countyctl` command
does the maintenance work, and every change it makes can be undone.

## Why it's safe to try

- **Your old website is never touched.** The portal runs on its own server.
  The old site keeps running until the day you point DNS at the new one, and
  you can point it back the same day.
- **Every import can be undone.** Records and bills come in as numbered
  batches that can be removed as a whole. Old web pages come in as unpublished
  drafts.
- **Every update can be undone.** `countyctl update` takes a backup first, and
  goes back on its own if the new version doesn't start.
- **Every theme change can be undone.** Styles are previewed before
  publishing, and earlier versions can be restored with one click.
- **Sample data is labeled SAMPLE** on every page and removed with one command.

## The path from zero to live

Work through these in order. Each page ends with how to check it worked.

| Step | Guide | Time |
|---|---|---|
| 1 | [Check the server size](sizing.md) | 10 minutes |
| 2 | [Install](install.md) | 30 minutes |
| 3 | [HTTPS certificate](https.md) | 10 minutes |
| 4 | [Outgoing email](email.md) | 15 minutes |
| 5 | [Off-site backups](backups.md) | 20 minutes |
| 6 | [Staff accounts and first sign-in](staff-accounts.md) | 15 minutes |
| 7 | [Style the site](styling.md) | 30 minutes |
| 8 | [Move your records, bills and old pages](migration.md) | hours to days |
| 9 | [Connect a payment processor](payments.md) | 1 hour, after your contract |
| 10 | [Accessibility testing](accessibility-testing.md) | half a day |
| 11 | [Register with Data.gov](data-gov.md) | 20 minutes |
| 12 | [Go-live checklist and cutover](cutover.md) | 1 day |

Want to see it first? [Demonstration site](hosted-demo.md) runs a fictional
county with 200,000 records on your own computer, or on Cloudflare with no
server to maintain.

After launch:

- [Everyday operations with countyctl](countyctl.md)
- [Updates](updates.md)
- [Troubleshooting](troubleshooting.md)
- [Server security](security.md)
- [All settings](settings.md)

## How the pieces fit

```
Residents' browsers ──HTTPS──> web (Caddy) ──> app (the portal) ──> db (PostgreSQL)
                                                     │
                                  /var/lib/county-portal/data  (images, files, backups)
```

- **web** gets and renews the HTTPS certificate and passes requests on.
- **app** is the website, the staff console and the open API.
- **db** holds records, payments, pages and settings.

All three run in Docker containers on one server. Your data lives outside the
containers, in `/var/lib/county-portal`, so replacing a container never
touches it. The program and its settings live in `/opt/county-portal`.

## Where things are

| What | Where |
|---|---|
| Program and settings | `/opt/county-portal` (settings in `/opt/county-portal/.env`) |
| Database files | `/var/lib/county-portal/postgres` |
| Images, documents, uploads, bulk data | `/var/lib/county-portal/data` |
| Backups | `/var/lib/county-portal/data/backups` |
| Put exports from old systems here | `/var/lib/county-portal/import` |
| Log of countyctl actions | `/var/log/county-portal.log` |

## Getting help

- Run `sudo countyctl doctor`. It checks everything and says what to do in
  plain English.
- The same guides are in the staff console under **Help**.
- [Troubleshooting](troubleshooting.md) covers the common problems.
- Search or ask in the project's GitHub issues. Never post passwords, the
  contents of `.env`, or residents' personal information.
