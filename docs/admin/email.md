# Outgoing email

The portal emails receipts, certified-copy notices and request updates. It
sends through an email relay you already have; it doesn't run its own mail
server. Until email is set up, everything still works, but nothing is emailed.

## What you need from your email administrator

| Setting | Example |
|---|---|
| Relay server name | `smtp.office365.com`, `smtp.gmail.com`, or your own relay |
| Port | `587` (most common) or `465` |
| Username and password | an account allowed to send, often a dedicated mailbox |
| From address | `no-reply@example-county.gov` |

Use an address on your own domain so receipts aren't marked as spam, and ask
your email administrator to make sure the domain's SPF and DKIM records cover
the relay.

Common relays:

- **Microsoft 365:** server `smtp.office365.com`, port `587`, a licensed
  mailbox with "Authenticated SMTP" turned on for it in the Microsoft 365
  admin center. The From address must be that mailbox or one it can send as.
- **Google Workspace:** server `smtp-relay.gmail.com` (relay service set up in
  the Google admin console) or `smtp.gmail.com` with an app password.
- **Your own relay that allows the server's IP without a password:** leave
  username and password empty.

## 1. Open the settings file

```
sudo nano /opt/county-portal/.env
```

## 2. Fill in the email lines

```
PORTAL_SMTP_HOST=smtp.office365.com
PORTAL_SMTP_PORT=587
PORTAL_SMTP_USER=no-reply@example-county.gov
PORTAL_SMTP_PASSWORD=the-password
PORTAL_SMTP_FROM=no-reply@example-county.gov
PORTAL_SMTP_STARTTLS=true
```

For port 465, leave `PORTAL_SMTP_STARTTLS=true`; the portal uses a secure
connection from the start on that port. For a relay that offers no encryption
on 587 or 25 inside your network, set `PORTAL_SMTP_STARTTLS=false`.

Avoid the characters `$`, `"` and `'` in the password line; if your password
has them, ask for a different one for this mailbox.

Save with Ctrl+O, Enter, then Ctrl+X.

## 3. Apply

```
sudo countyctl restart
```

## 4. Send a test

```
sudo countyctl app email-test --to you@example-county.gov
```

Check that it arrives, and that it isn't in the spam folder.

## If the test fails

| Message contains | Usually means |
|---|---|
| `ConnectionRefusedError` or `timed out` | Wrong server or port, or a firewall blocks the server from reaching it. Test with `nc -vz smtp.office365.com 587` |
| `SMTPAuthenticationError` | Wrong username or password, or the mailbox isn't allowed to send by SMTP (Microsoft 365: turn on Authenticated SMTP for it) |
| `SMTPSenderRefused` | The From address isn't one the account may send as |
| `certificate verify failed` | The relay's certificate isn't trusted. Ask your email administrator; don't turn encryption off on a relay outside your network |

Fix the line in `.env`, run `sudo countyctl restart`, and test again.

## Undo

Empty the `PORTAL_SMTP_HOST=` line and restart. The portal goes back to not
sending email.

Next: [Off-site backups](backups.md).
