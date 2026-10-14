# Staff accounts and sign-in

Every staff member has their own account. Nobody shares a sign-in. Each
sign-in needs a password and a six-digit code from an app on the person's
phone, so a stolen password alone doesn't get anyone in.

## Roles

Give each person only the roles their job needs. One person can have several.

| Role | Can |
|---|---|
| `admin` | everything, including staff accounts, theme, settings, fees and system |
| `content` | edit pages, services, offices, meetings, public notices and redirects |
| `records` | manage records, redactions, and certified copy orders |
| `cashier` | run the counter point of sale for the offices they're assigned |
| `supervisor` | voids and refunds, drawer close-out review, finance reports |
| `finance` | finance reports and ledger exports |
| `pia` | handle public information (open records) requests |
| `applications` | review submitted forms such as permits and jury responses |

Cashiers must also be assigned to one or more offices; they can only sell for
those offices.

## Add a staff member

In the staff console: **Settings > Staff accounts > Add a staff member**.
Enter the name, work email, roles and (for cashiers) offices, then **Create
account**. The page shows a temporary password. Give it to the person
privately, in person or by phone, not by email.

Or from the server:

```
sudo countyctl app user add --email pat.lee@example-county.gov --name "Pat Lee" --role cashier --office county-clerk
```

Repeat `--role` or `--office` for several. Office names are the short names
shown in **Content > Offices** (for example `county-clerk`, `tax-office`).

## First sign-in (for the staff member)

1. Go to `https://your-portal-address/staff`.
2. Enter your work email and the temporary password.
3. Install an authenticator app on your phone if you don't have one
   (Microsoft Authenticator, Google Authenticator, 1Password and others all
   work). In the app, add an account and scan the square code on the screen.
   If you can't scan, type the setup key shown under it.
4. Enter the six-digit code the app shows.
5. Choose your own password: at least 12 characters. A short sentence works
   well.

After 60 minutes without activity you're signed out. Five minutes before
that, a message offers to keep you signed in.

## Someone lost their phone or forgot their password

**Settings > Staff accounts**, find the person, **Reset password and phone
code**. Give them the new temporary password; they set up the app again at
next sign-in.

Or from the server:

```
sudo countyctl app user reset --email pat.lee@example-county.gov
```

## Locked out after wrong passwords

Five wrong passwords in a row lock the account for 15 minutes. Wait, or reset
it as above.

## Someone leaves

Disable the account the same day: **Settings > Staff accounts > Disable**. Or:

```
sudo countyctl app user disable --email pat.lee@example-county.gov
```

Disabled accounts stay in the audit log; their history isn't lost.
**Re-enable** brings an account back.

## If you're the only administrator and you're locked out

From the server, give yourself a new temporary password:

```
sudo countyctl app user reset --email you@example-county.gov
```

Make at least two people administrators so this is rarely needed.

## See everyone

```
sudo countyctl app user list
```

## What's recorded

Every sign-in, setting change, void, record change and import is in the audit
log: **System > Audit log**. It shows who, what, when, and from which network
address.

Next: [Style the site](styling.md).
