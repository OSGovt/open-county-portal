# Server security

The portal protects itself: two-step sign-in for staff, no card data, a
strict content security policy, signed sessions, rate limits on the API,
an audit log of every staff action, and no public access to anything staff
haven't published. The server it runs on needs the same care as any other.
Do these on day one.

## 1. Automatic security updates for the operating system

```
sudo apt-get install -y unattended-upgrades && sudo dpkg-reconfigure -plow unattended-upgrades
```

Choose Yes. Ubuntu then installs security fixes every day. Some fixes need a
restart; check monthly:

```
ls /var/run/reboot-required 2>/dev/null && echo "Restart needed"
```

Restart at a quiet time with `sudo reboot`; the portal comes back on its own.

## 2. Firewall

Allow only SSH, HTTP and HTTPS. If you manage SSH from a known network,
allow SSH only from there (replace the address with your admin network):

```
sudo ufw allow from 10.0.0.0/8 to any port 22 proto tcp
```

```
sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
```

```
sudo ufw enable
```

Note: Docker publishes ports 80 and 443 itself, so they stay open even if ufw
rules say otherwise. That's intended here; just don't publish other ports.

## 3. SSH keys instead of passwords

Set up key sign-in for each administrator, test that it works in a second
window, then turn off password sign-in:

```
sudo nano /etc/ssh/sshd_config.d/90-county-portal.conf
```

Add these lines and save:

```
PasswordAuthentication no
PermitRootLogin no
```

```
sudo systemctl reload ssh
```

## 4. Keep the settings file private

`/opt/county-portal/.env` holds the database password, the key that signs
sign-in sessions, and the email password. The installer makes it readable only by root.
Keep a copy in a password manager; never email it or put it in a ticket.

If you think it leaked: generate a new `PORTAL_SECRET_KEY`
(`openssl rand -hex 32`), put it in `.env`, and restart. Everyone is signed
out and signs in again as usual; phone codes keep working, and certified
copies issued before still verify, because both are stored in the database.
Also change the email password and the off-site backup credentials it holds.

## 5. Staff accounts

- One account per person; disable accounts the day someone leaves.
- Give the fewest roles needed (see [Staff accounts](staff-accounts.md)).
- At least two administrators, so one can recover the other.
- Review **System > Audit log** monthly for anything unexpected.

## 6. Backups off the server

Set up off-site copies ([Backups](backups.md)). Keep at least one copy that
the portal server can't delete, such as a destination with versioning or
retention lock, to protect against ransomware.

## Reporting a security problem in the portal

Follow the project's SECURITY.md. Don't post vulnerabilities in public
issues.
