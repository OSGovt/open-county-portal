# Install

About 30 minutes. You'll answer six questions; the installer does the rest.

Before you start:

- [ ] A server that meets [Server size](sizing.md), freshly installed with Ubuntu 24.04 LTS
- [ ] You can SSH to it as a user who can use `sudo`
- [ ] You've chosen the web address, such as `portal.example-county.gov`
- [ ] For a free automatic certificate: that address points at the server's
      public IP in DNS, and ports 80 and 443 reach the server. (You can install
      first and do this later; see [HTTPS](https.md).)

If the server has another web server on it (Apache, nginx, IIS behind a
proxy), the installer will stop and say so. The portal needs ports 80 and 443
to itself.

## 1. Connect to the server

From your computer:

```
ssh you@server-address
```

## 2. Update the operating system

```
sudo apt-get update && sudo apt-get -y upgrade
```

If it says a restart is required, restart and connect again:

```
sudo reboot
```

## 3. Install git

```
sudo apt-get install -y git
```

## 4. Download the portal

```
sudo git clone https://github.com/OWNER/open-county-portal.git /opt/county-portal
```

(Use the address shown on the project's GitHub page.) Installing with git
lets `countyctl update` fetch new releases.

No internet access from the server? Download the release `.tar.gz` file on
another computer, copy it over, and unpack it:

```
sudo mkdir -p /opt/county-portal && sudo tar -xzf open-county-portal-*.tar.gz -C /opt/county-portal --strip-components=1
```

## 5. Start the installer

```
cd /opt/county-portal && sudo ./deploy/install.sh
```

It checks the server first. If something's wrong it stops, says what to fix,
and changes nothing that a second run won't fix.

## 6. Answer the six questions

| Question | What to enter |
|---|---|
| 1. Name of your government | As residents know it: `Example County`, `Example Water District` |
| 2. Type | `county`, `municipality`, `special_district` or `school_district` |
| 3. State | Two letters, such as `tx`. If there's no ready-made state pack yet, you'll be asked for the full state name, and the site starts with no offices or services for you to add |
| 4. Web address | Without `https://`, such as `portal.example-county.gov` |
| 5. Certificate | `public` (free, automatic), `internal` (test server or inside your network) or `provided` (your organization's own). See [HTTPS](https.md) |
| 6. Your email and name | You become the first administrator. Certificate notices go to this email too |

It shows your answers and asks you to confirm. Then it:

1. installs Docker from Docker's official repository
2. copies the settings file to `/opt/county-portal/.env` with new random passwords
3. schedules nightly backups and maintenance
4. builds and starts the portal (5 to 10 minutes the first time)
5. sets up your site from the state pack
6. takes the first backup

## 7. Write down the first sign-in

At the end you'll see:

```
Installed.

Sign in to the staff console:  https://portal.example-county.gov/staff
  First administrator: you@example-county.gov
  Temporary password: Abcde-Fghij-Klmno-Pqrst
```

The temporary password works once. If you lose it, run
`sudo countyctl app user reset --email you@example-county.gov` for a new one.

The same note is saved in `/var/lib/county-portal/data/status/first-admin.txt`
(readable only by the administrator). Delete it after you sign in:

```
sudo rm /var/lib/county-portal/data/status/first-admin.txt
```

## 8. Check the installation

```
sudo countyctl doctor
```

Every line should say OK. Lines marked WARN are things to set up in the next
guides (email, off-site backups). A FAIL line says what to do.

## 9. Sign in

Open `https://your-address/staff` in a browser. You'll:

1. enter the email and temporary password
2. set up a sign-in code app on your phone (any authenticator app works:
   Microsoft Authenticator, Google Authenticator, 1Password and others)
3. choose your own password (at least 12 characters)

See [Staff accounts](staff-accounts.md) for adding everyone else.

If the address doesn't load yet, the certificate is probably waiting for DNS.
See [HTTPS](https.md).

## 10. Load sample data for training (optional)

```
sudo countyctl app demo
```

This adds a few records, bills, a meeting and a notice, each marked SAMPLE on
every page, so staff can practice. Remove it before going live:

```
sudo countyctl app demo --remove
```

## If something goes wrong

- Run the installer again. It keeps your settings and data and only fills in
  what's missing.
- `sudo countyctl logs app` shows what the portal is doing.
- See [Troubleshooting](troubleshooting.md).

## Undo the installation

The portal doesn't change anything outside `/opt/county-portal`,
`/var/lib/county-portal`, Docker, and two scheduled-job files. To remove it
completely (this deletes the data):

```
cd /opt/county-portal && sudo docker compose down
```

```
sudo systemctl disable --now county-portal-nightly.timer && sudo rm /etc/systemd/system/county-portal-nightly.* /usr/local/bin/countyctl /etc/logrotate.d/county-portal
```

```
sudo rm -rf /opt/county-portal /var/lib/county-portal
```

Next: [HTTPS certificate](https.md).
