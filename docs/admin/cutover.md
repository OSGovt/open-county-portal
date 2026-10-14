# Go-live checklist and cutover

Cutover is the moment the county's web address starts showing the new portal
instead of the old site. Done this way, it's a DNS change you can reverse the
same day, and the old site keeps running untouched until you decide to turn
it off.

## Weeks before: run both side by side

1. **Give the new portal a temporary address**, such as
   `new.example-county.gov`, during install (or change it later: see
   [HTTPS](https.md#change-the-web-address)). Staff use it for training and
   testing while residents keep using the old site.
2. **Train every office** with sample data (`sudo countyctl app demo`).
   Cashiers run practice sales and close drawers with the test processor.
3. **Import for real**, office by office, with sign-off (see
   [Moving your records](migration.md)). Keep bill imports running nightly
   so balances stay current.
4. **Remove the sample data** when training is done:

```
sudo countyctl app demo --remove
```

## The go-live checklist

**System > Go-live checklist** in the staff console. The top half is checked
automatically and says how to fix anything not done:

- Sample data removed
- All fees confirmed against the adopted fee order
- A real payment processor is connected (or pay-at-office chosen on purpose)
- Outgoing email works
- Site name, address, phone and accessibility contact are filled in
- Open data contact email is set
- Every staff account has its phone code set up
- A backup finished in the last 24 hours
- Bulk open data files have been generated
- No required postings are missing
- Every records import has been signed off
- The site uses HTTPS

The bottom half is for people to confirm, by checking each box:

- Keyboard and screen reader testing done ([Accessibility testing](accessibility-testing.md))
- The clerk or finance office reviewed every fee against the adopted order
- Every office's staff practiced with sample data
- Each office reviewed its service and office pages
- The County Clerk signed off on the records import report
- The Data.gov harvest request was submitted ([Data.gov](data-gov.md))
- Backups are copied off the server, and a restore was practiced ([Backups](backups.md))
- This cutover plan and the way back were reviewed

Don't cut over until everything is checked.

## Choose the day

Pick a weekday morning when IT and someone from each office are available,
not the week taxes are due and not the day before a holiday. Tell the public
a week ahead with the alert banner on the old site, if you can, and on social
media.

## The day before

1. **Lower the DNS "time to live"** for the main address to 300 seconds (5
   minutes), so the change spreads quickly and can be reversed quickly. Do
   this at least a day ahead, because the old, longer value has to expire
   first. Write down the current DNS record exactly; that's your way back.
2. **Take a labeled backup:**

```
sudo countyctl backup --label before-cutover
```

3. **Run the doctor:**

```
sudo countyctl doctor
```

## Cutover morning

1. **Final bill import** so balances are current (if you don't run it
   nightly).

2. **Change the web address** of the portal from the temporary one to the
   main one. In `/opt/county-portal/.env`:

```
sudo nano /opt/county-portal/.env
```

   Set `PORTAL_HOST=www.example-county.gov` and
   `PORTAL_SITE_URL=https://www.example-county.gov`. Save.

```
sudo countyctl restart
```

3. **Change DNS** for the main address to point at the portal server's IP.

4. **Watch the certificate arrive** (public mode). It needs DNS to point at
   the server first, so this may take a few minutes:

```
sudo countyctl logs web
```

   Look for `certificate obtained successfully`. Ctrl+C to stop.

5. **Check from outside your network** (a phone on cellular data works):
   - the home page loads with a padlock
   - an old address you know redirects to the right new page
   - a records search works
   - a test purchase works, then void it

6. **Rewrite the open data files** with the new address:

```
sudo countyctl app export-bulk
```

7. **If you also want the bare domain** (`example-county.gov` without `www`)
   to work, point it at the same server and add it on the old web server or
   your DNS provider as a redirect to `https://www.example-county.gov`.

## The way back (same day)

If something serious is wrong:

1. Change DNS back to the record you wrote down. With a 5-minute time to
   live, most people see the old site again within minutes.
2. Change `PORTAL_HOST` and `PORTAL_SITE_URL` back to the temporary address
   and run `sudo countyctl restart`.
3. Payments taken on the portal in the meantime are in **Finance**; post them
   as usual with **Download bill payments to post**.

Nothing on the old site changed, so it simply carries on.

## The weeks after

- Keep the old site running, unreachable to the public, for at least 90 days
  in case something was missed.
- Look for old addresses people still use that land on "page not found",
  and add redirects for them in **Content > Redirects**. This lists the most
  common ones from the last day:

```
cd /opt/county-portal && sudo docker compose logs --since 24h app | grep '" 404' | grep -o 'GET [^ ]*' | sort | uniq -c | sort -rn | head -30
```
- Tell Data.gov if your catalog address changed.
- Raise the DNS time to live back to its usual value after a week.
- Send the old site's hosting or vendor the termination notice your contract
  requires.

Next: [Everyday operations](countyctl.md).
