# Troubleshooting

Start every time with:

```
sudo countyctl doctor
```

It checks everything and says what to do in plain English. If that doesn't
settle it, find the symptom below.

## The site doesn't load at all

1. Is it running?

```
sudo countyctl status
```

   All three parts (`db`, `app`, `web`) should say `running`. If not:

```
sudo countyctl restart
```

2. Still down? See why the portal won't start:

```
sudo countyctl logs app
```

   Common messages:

   | Message | Fix |
   |---|---|
   | `PORTAL_SECRET_KEY is not set` | The settings file is missing or damaged. Restore your saved copy of `/opt/county-portal/.env` |
   | `The database isn't reachable` | `sudo countyctl logs db`; often the disk is full (below) |
   | `No space left on device` | The disk is full (below) |
   | `Permission denied: '/data/...'` | Run `sudo chown -R 1000:1000 /var/lib/county-portal/data` and restart |

3. Is the server reachable at all? From another computer, `ping` the server.
   If that fails, it's the network or the server itself, not the portal.

## "Your connection is not private" or a certificate warning

- **Public mode:** the certificate couldn't be issued. `sudo countyctl logs web`
  shows why. Nearly always DNS doesn't point at this server yet, or ports 80
  and 443 aren't open from the internet. See [HTTPS](https.md#public-automatic).
- **Internal mode:** expected until the computer trusts the server's
  certificate authority. See [HTTPS](https.md#internal).
- **Provided mode:** the certificate expired or doesn't match the address.
  Check with `sudo openssl x509 -enddate -subject -noout -in /var/lib/county-portal/caddy/certs/portal.crt`.

## The disk is full

See what's using it:

```
sudo sh -c 'du -sh /var/lib/county-portal/* /var/lib/county-portal/data/*'
```

- **Backups** are usually the biggest. Make sure off-site copies are working,
  then lower `PORTAL_BACKUP_KEEP` in `.env` (for example to 7). Old labeled
  backups you're sure you don't need can be deleted:
  `sudo rm -rf /var/lib/county-portal/data/backups/NAME`.
- **Import files** you've finished with: delete them from
  `/var/lib/county-portal/import`.
- **Cached page images** can always be deleted safely; they're made again as
  needed: `sudo rm -rf /var/lib/county-portal/data/cache/pages`.
- **Docker's old build layers:** `sudo docker system prune -f` (this doesn't
  touch your data).

Then grow the disk for the long term.

## Staff can't sign in

| Problem | Fix |
|---|---|
| Forgot password or lost phone | Reset: **Settings > Staff accounts**, or `sudo countyctl app user reset --email E` |
| "Account locked" | Wait 15 minutes, or reset as above |
| The six-digit code is always wrong | The phone's clock or the server's clock is off. On the server: `timedatectl` should say `System clock synchronized: yes`; if not, `sudo timedatectl set-ntp true`. On the phone, turn on automatic date and time |
| Signed out too often | Staff are signed out after 60 minutes without activity, by design |

## Emails don't arrive

```
sudo countyctl app email-test --to you@example-county.gov
```

It prints the reason if sending fails. See [Outgoing email](email.md#if-the-test-fails).
If it says sent but nothing arrives, check spam, and ask your email
administrator to check the relay's logs and the domain's SPF record.

## A payment problem

- **A resident says they paid but the portal shows unpaid.** Find the order
  in **Finance** or **Counter > Saved online orders**. Look the payment up in
  the processor's dashboard by the order number. If the processor shows it
  paid, the resident's browser probably closed before returning to the
  portal: record the payment at the counter with the processor's reference.
- **Every online payment fails.** `sudo countyctl logs app` shows the
  processor's message. Usually the processor key in **Settings > Payments**
  was changed or revoked.
- **A refund is needed for an online payment.** A supervisor voids the order;
  the refund goes through the processor automatically. If the processor
  refuses, the order isn't voided, and the message says why.

## Records search is slow

- The first search after a restart is slower; later ones are fast.
- With millions of records, give the server more memory (16 GB) and check
  `sudo countyctl logs db` for warnings.

## An import went wrong

Undo the batch and try again; nothing else is affected:

```
sudo countyctl app migrate records undo --batch N
```

## The open data catalog or API shows the old address

After changing the web address, run `sudo countyctl app export-bulk`.

## After an update, something's wrong

If the update itself failed, it already went back on its own. If it worked
but something's off: `sudo countyctl rollback` (read [Updates](updates.md)
first; it also rolls back data).

## Asking for help

Collect this (it contains no passwords) and attach it to a GitHub issue,
after checking it for any residents' personal information:

```
cd /opt/county-portal && (sudo countyctl status; sudo countyctl doctor; sudo docker compose logs --tail=200 app) > help-request.txt 2>&1
```

Never share `.env` or backups.
