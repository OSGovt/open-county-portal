# Backups and restore

## What happens on its own

Every night at about 2:30 a.m. the server:

1. copies the whole database
2. snapshots images, documents and uploads (files that haven't changed are
   linked to the previous night's copy instead of copied again, so this is
   fast and small)
3. copies the backup off the server, if you've set that up (below)
4. writes the day's open data files, reads text from new scanned pages, and
   deletes ID uploads past the retention period

It keeps the last 14 nightly backups. Backups with a label (taken before an
update, a restore, or by hand with a label) are kept 60 days.

A backup is a folder in `/var/lib/county-portal/data/backups`, named by its
date and time in UTC, such as `20261014-073000`.

**What isn't in the backup:** the settings file `/opt/county-portal/.env`
(it holds passwords; keep your own copy, see below) and any provided HTTPS
certificate.

## Off-site copies: set this up before go-live

A backup on the same server doesn't help if the server is lost. Pick a
destination you already have and give the portal one command that copies a
folder there. The portal replaces `{path}` with the backup folder's full path
and `{name}` with just its name. Don't use the `$` character in this line.

**A network share (NAS or file server) mounted on the server:**

```
PORTAL_BACKUP_COPY_CMD=rsync -a {path} /mnt/portal-backups/
```

**Another server over SSH** (set up an SSH key for root to that server first):

```
PORTAL_BACKUP_COPY_CMD=rsync -a -e "ssh -i /root/.ssh/portal_backup" {path} backup@backup-server:/portal-backups/
```

**Cloud storage with rclone** (after `sudo apt-get install -y rclone` and
`sudo rclone config` to add a remote named `offsite`):

```
PORTAL_BACKUP_COPY_CMD=rclone copy {path} offsite:county-portal-backups/{name}
```

To set it:

1. Open the settings file:

```
sudo nano /opt/county-portal/.env
```

2. Put your command on the `PORTAL_BACKUP_COPY_CMD=` line. Save with Ctrl+O,
   Enter, then Ctrl+X. (No restart needed: the command runs on the server
   itself, not inside the portal.)

3. Test it:

```
sudo countyctl backup
```

The last lines should say `Off-site copy finished.` Check the destination.

Off-site copies are full folders, so each night's copy is the size of the
database plus all files, unless your destination de-duplicates (rclone with
most cloud storage copies only changed files). Delete old copies at the
destination on your own schedule.

## Keep a copy of the settings file

Store this file somewhere safe and private, such as your password manager. A
restore to a new server needs it:

```
sudo cat /opt/county-portal/.env
```

## Back up now

```
sudo countyctl backup
```

With a label, kept 60 days:

```
sudo countyctl backup --label before-big-import
```

Staff with the administrator role can also start a backup from **System** in
the staff console. That backup isn't copied off-site until the next nightly
run or the next `sudo countyctl backup`.

## See backups

```
sudo countyctl backups
```

## Check a backup is good

```
sudo countyctl app verify-backup 20261014-073000
```

It checks the database copy against its checksum and that PostgreSQL can read
it.

## Restore

Restoring puts the database, images, documents and uploads back the way they
were at that backup. Anything entered since (payments, requests, edits) is
gone from the portal, so check the finance report for payments taken in
between before you restore.

1. Pick the backup:

```
sudo countyctl backups
```

2. Restore it:

```
sudo countyctl restore 20261014-073000
```

It checks the backup, asks you to type its name to confirm, takes a safety
backup labeled `before-restore`, stops the site for a few minutes, restores,
and starts the site again.

**To undo a restore**, restore the `before-restore` backup it just made.

## Practice a restore

Do this once before go-live and once a year. It's how you know backups work.
The practice runs on a test server so the live site isn't affected.

1. Install the portal on a test server ([Install](install.md), `internal`
   certificate mode).
2. Copy a backup folder from your off-site destination to the test server's
   `/var/lib/county-portal/data/backups/` folder, then fix its owner:

```
sudo chown -R 1000:1000 /var/lib/county-portal/data/backups
```

3. Restore it:

```
sudo countyctl restore 20261014-073000
```

4. Sign in and look up a few records and payments you know.

Mark "a restore was practiced" on the go-live checklist when done.

## Rebuild after losing the server

1. Build a new server and install the portal ([Install](install.md)) with the
   same web address and certificate mode.
2. Replace the new settings file with your saved copy (this brings back your
   email, off-site backup and other settings; everything else, including
   staff accounts and payment settings, comes back with the database):

```
sudo nano /opt/county-portal/.env
```

3. Apply it. The database password in the saved copy doesn't match the new
   empty database, so reset the database folder first (it's empty on a new
   server):

```
cd /opt/county-portal && sudo docker compose down && sudo rm -rf /var/lib/county-portal/postgres && sudo docker compose up -d
```

4. Copy the newest backup from off-site into
   `/var/lib/county-portal/data/backups/`, fix the owner as above, and
   restore it with `sudo countyctl restore NAME`.
5. Point DNS at the new server if its address changed.
6. Run `sudo countyctl doctor`.

## Check

`sudo countyctl doctor` reports the age of the last backup and whether
off-site copies are set up. The staff console dashboard shows it too.

Next: [Staff accounts](staff-accounts.md).
