# All settings

Most settings are in the staff console (**Settings**) and take effect
immediately. A few that concern the server itself are in the file
`/opt/county-portal/.env`. After changing that file, run
`sudo countyctl restart`.

Edit it with:

```
sudo nano /opt/county-portal/.env
```

Format: one `NAME=value` per line, no spaces around `=`, no quotes needed.
Avoid `$` in values.

## Site

| Setting | Default | Meaning |
|---|---|---|
| `PORTAL_HOST` | set at install | The web address without `https://` |
| `PORTAL_SITE_URL` | set at install | The full address with `https://`; used in links, emails, the API and the data catalog. Keep it matching `PORTAL_HOST` |
| `PORTAL_TLS_MODE` | `public` | `public`, `internal` or `provided`. See [HTTPS](https.md) |
| `PORTAL_ADMIN_EMAIL` | set at install | Receives certificate notices |
| `PORTAL_ENV` | `production` | Leave as is |

## Secrets

| Setting | Meaning |
|---|---|
| `PORTAL_SECRET_KEY` | Signs sign-in sessions. Generated at install. Changing it signs everyone out |
| `POSTGRES_PASSWORD` | The database password. Generated at install. **Don't change it** after install: the database keeps the original. |

## Email

See [Outgoing email](email.md).

| Setting | Default | Meaning |
|---|---|---|
| `PORTAL_SMTP_HOST` | empty (no email) | Relay server |
| `PORTAL_SMTP_PORT` | `587` | `587` or `465` |
| `PORTAL_SMTP_USER` | empty | Username, if the relay needs one |
| `PORTAL_SMTP_PASSWORD` | empty | Password |
| `PORTAL_SMTP_FROM` | | The From address on emails |
| `PORTAL_SMTP_STARTTLS` | `true` | Encrypt on port 587. Set `false` only for an internal relay without encryption |

## Backups

See [Backups](backups.md).

| Setting | Default | Meaning |
|---|---|---|
| `PORTAL_BACKUP_COPY_CMD` | empty | Command that copies each backup off the server; `{path}` and `{name}` are filled in. Takes effect without a restart |
| `PORTAL_BACKUP_KEEP` | `14` | How many nightly backups to keep on the server |

## Tuning

| Setting | Default | Meaning |
|---|---|---|
| `PORTAL_WORKERS` | `4` | Web worker processes. About one per processor, up to 8 |
| `PORTAL_API_RATE` | `120` | Open API requests per minute for each address without a key |
| `PORTAL_API_RATE_KEYED` | `1200` | Requests per minute with a free API key |
| `PORTAL_UPLOAD_MAX_MB` | `15` | Largest file a resident can upload with a form |
| `PORTAL_ID_RETENTION_DAYS` | `30` | Days before uploaded ID photos are deleted automatically |
| `PORTAL_SESSION_MAX_AGE` | `86400` | Seconds a resident's cart is remembered |
| `PORTAL_STAFF_SESSION_MAX_AGE` | `36000` | Longest staff sign-in, in seconds (staff are also signed out after 60 idle minutes) |
| `PORTAL_IMAGE_TAG` | `current` | Leave as is; `countyctl update` manages it |

## In the staff console

| Page | What's there |
|---|---|
| **Settings > Site identity** | Name, address, phone, accessibility contact, population, time zone, alert banner |
| **Settings > Theme** | Colors, font, logo, preview, publish, earlier versions. See [Styling](styling.md) |
| **Settings > Payments, records and open data** | Processor, payment methods, processing fees, merchant accounts, free downloads, open data terms and contact. See [Payments](payments.md) and [Data.gov](data-gov.md) |
| **Settings > Staff accounts** | Add, change roles, reset, disable. See [Staff accounts](staff-accounts.md) |
| **Settings > API keys** | Free keys for heavy users of the open API (they only raise the rate limit) |
| **Settings > Custom forms** | Forms residents can submit, beyond those in the state pack |
| **Content > Fee schedule** | Fees with effective dates and the adopting order |
| **System** | Version, backups, imports, go-live checklist, audit log |

Every settings change is recorded in the audit log with who made it.
