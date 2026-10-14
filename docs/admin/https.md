# HTTPS certificate

The portal always uses HTTPS. You chose one of three ways to get a certificate
during install; you can change it at any time.

| Mode | Use it when | Browsers trust it? |
|---|---|---|
| `public` | the site is on the internet | Yes. Free certificate from Let's Encrypt, renewed automatically |
| `internal` | a test server, or a site only reachable inside your network | Only after you install its authority certificate |
| `provided` | your organization buys certificates or requires its own | Yes, if your certificate is valid |

To see which mode you're using:

```
grep PORTAL_TLS_MODE /opt/county-portal/.env
```

## Public (automatic)

For the certificate to be issued:

1. The web address must point at the server's public IP address in public DNS
   (an `A` record, plus `AAAA` if the server has IPv6).
2. Ports 80 and 443 must reach the server from the internet.
3. If your domain has a `CAA` DNS record, it must allow `letsencrypt.org`.

Check DNS from the server:

```
getent hosts portal.example-county.gov
```

The address shown should be the server's public IP.

Once DNS and the firewall are right, the certificate arrives within a minute
or two. No restart is needed; it retries on its own. Watch it happen:

```
sudo countyctl logs web
```

Look for `certificate obtained successfully`. Press Ctrl+C to stop watching.

Renewal is automatic, about 30 days before expiry. Notices about problems go
to the email in `PORTAL_ADMIN_EMAIL`.

**Before cutover:** while the old site still owns the address, the public
certificate can't be issued for it. Either test with a temporary address
(such as `new-portal.example-county.gov`) and switch on cutover day, or use
`internal` mode until then. See [Cutover](cutover.md).

## Internal

The server makes its own certificate authority. Browsers warn until each
computer trusts it, which is fine for a test server and workable inside a
county network where IT can push the certificate to computers.

1. Copy the authority certificate off the server:

```
sudo cat /var/lib/county-portal/caddy/caddy/pki/authorities/local/root.crt
```

2. Save the text as `county-portal-root.crt` and install it as a trusted root
   certificate on staff computers (on Windows with Group Policy: Computer
   Configuration > Windows Settings > Security Settings > Public Key Policies >
   Trusted Root Certification Authorities).

The conformance suite can check an internal-mode server with `--insecure`.

## Provided certificate

1. Get a certificate for the web address in PEM format: the certificate
   followed by any intermediate certificates (the "full chain"), and the
   private key, not password-protected.

2. Copy them to the server as these two files:

```
sudo mkdir -p /var/lib/county-portal/caddy/certs
```

```
sudo cp fullchain.pem /var/lib/county-portal/caddy/certs/portal.crt && sudo cp private.key /var/lib/county-portal/caddy/certs/portal.key
```

```
sudo chmod 600 /var/lib/county-portal/caddy/certs/portal.key
```

3. Switch the mode (next section) or, if you're already in `provided` mode,
   restart:

```
sudo countyctl restart
```

**Renewal is up to you.** Put a reminder on the calendar a month before the
certificate expires; replace the two files and restart. Check the expiry date:

```
sudo openssl x509 -enddate -noout -in /var/lib/county-portal/caddy/certs/portal.crt
```

## Change mode

1. Open the settings file:

```
sudo nano /opt/county-portal/.env
```

2. Change the line `PORTAL_TLS_MODE=` to `public`, `internal` or `provided`.
   Save with Ctrl+O, Enter, then Ctrl+X.

3. Apply it:

```
sudo countyctl restart
```

To undo, change it back and restart.

## Change the web address

1. In `/opt/county-portal/.env`, change both `PORTAL_HOST=` and
   `PORTAL_SITE_URL=` (the second one starts with `https://`).
2. `sudo countyctl restart`
3. Update DNS. The old address stops working, so add it to your DNS as an
   alias only if you also add a redirect on your old web server.

Links in the open data catalog and bulk files use `PORTAL_SITE_URL`; the next
nightly run rewrites them, or run `sudo countyctl app export-bulk` now.

## Check

```
curl -s -o /dev/null -w '%{http_code}\n' https://portal.example-county.gov/healthz
```

shows `200`. `sudo countyctl doctor` checks the certificate too, in
public mode.

Next: [Outgoing email](email.md).
