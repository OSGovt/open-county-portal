# Everyday operations with countyctl

`countyctl` is the one command for running the portal. Run it with `sudo`.
Every action is written to `/var/log/county-portal.log`.

```
sudo countyctl help
```

## Is everything all right?

| Command | What it does |
|---|---|
| `sudo countyctl status` | Version, whether each part is running, disk space, last backup and off-site copy |
| `sudo countyctl doctor` | Checks the whole installation and says what to do about each problem |
| `sudo countyctl logs` | Recent log lines from all parts, following new ones. Ctrl+C to stop |
| `sudo countyctl logs app` | Only the portal (`db` for the database, `web` for HTTPS) |
| `sudo countyctl version` | The installed version |

## Start, stop, restart

| Command | What it does |
|---|---|
| `sudo countyctl restart` | Restart (about 20 seconds offline). Needed after editing `.env` |
| `sudo countyctl stop` | Stop the site |
| `sudo countyctl start` | Start it again |

The portal starts on its own when the server boots.

## Backups

| Command | What it does |
|---|---|
| `sudo countyctl backup` | Back up now, then copy off-site if set up |
| `sudo countyctl backup --label NAME` | Same, kept 60 days instead of 14 |
| `sudo countyctl backups` | List backups |
| `sudo countyctl restore NAME` | Put everything back to that backup (takes a safety backup first) |

Details: [Backups and restore](backups.md).

## Updates

| Command | What it does |
|---|---|
| `sudo countyctl update` | Install the newest release; backs up first and goes back on its own if the new version doesn't start |
| `sudo countyctl update v1.2.0` | Install a specific release |
| `sudo countyctl update --from FILE.tar.gz` | Install a release file you downloaded |
| `sudo countyctl rollback` | Go back to the version and data from before the last update |

Details: [Updates](updates.md).

## Application commands

`sudo countyctl app ...` runs a command inside the portal. The common ones:

| Command | What it does |
|---|---|
| `sudo countyctl app user add --email E --name "N" --role R` | Add a staff account (repeat `--role`; cashiers also need `--office`) |
| `sudo countyctl app user reset --email E` | New temporary password and phone code |
| `sudo countyctl app user disable --email E` | Disable an account |
| `sudo countyctl app user list` | List accounts |
| `sudo countyctl app demo` / `demo --remove` | Add or remove the SAMPLE training data |
| `sudo countyctl app email-test --to E` | Send a test email |
| `sudo countyctl app export-bulk` | Write the open data files now (normally nightly) |
| `sudo countyctl app ocr --limit 5000` | Read text from scanned pages that don't have it yet |
| `sudo countyctl app ssn-scan` | List pages whose text looks like a Social Security number, for review |
| `sudo countyctl app postings-check` | Required public notices that are missing or late |
| `sudo countyctl app purge-uploads` | Delete ID uploads past the retention period (normally nightly) |
| `sudo countyctl app check` | Quick self-test |
| `sudo countyctl app pack list` | State packs available |
| `sudo countyctl app migrate ...` | Imports: see [Moving your records](migration.md) |
| `sudo countyctl app --help` | Everything |

## What runs every night

At about 2:30 a.m. (`county-portal-nightly.timer`): backup and off-site copy,
open data files, text reading for up to 20,000 new pages, removal of expired
ID uploads, and the required-postings check (its result is saved in
`/var/lib/county-portal/data/status/postings.txt`; the dashboard shows the
same check live).

See when it last ran and when it runs next:

```
systemctl list-timers county-portal-nightly.timer
```

See what it printed last time:

```
journalctl -u county-portal-nightly.service -n 50
```

## A weekly five minutes

1. `sudo countyctl doctor`: all OK?
2. Look at the dashboard's **System health** in the staff console.
3. Check the off-site backup destination has last night's copy.
4. Apply operating system security updates (see [Server security](security.md)).
