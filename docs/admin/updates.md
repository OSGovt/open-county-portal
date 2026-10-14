# Updates

New releases fix problems, add features and keep up with laws and standards.
Updating is designed to be uneventful: a backup is taken first, and if the new
version doesn't start properly, the old one comes back on its own with your
data as it was.

## How releases are numbered

Versions look like `1.4.2`.

- The last number changes for fixes only: update promptly.
- The middle number changes for new features: read the changelog, update when
  convenient.
- The first number changes only for changes that need you to do something.
  The changelog says exactly what, step by step.

The changelog is `/opt/county-portal/CHANGELOG.md`, and on the project's
GitHub page.

## Update

1. Read what's new in the release notes on GitHub.

2. Choose a quiet time. The site is offline for about a minute while the new
   version starts.

3. Run:

```
sudo countyctl update
```

It shows six steps:

```
1/6 Checking the server...
2/6 Backing up...
3/6 Getting the new release...
4/6 Building version 1.4.2...
5/6 Starting version 1.4.2...
6/6 Checking it works...
Updated to version 1.4.2.
```

To install a particular version instead of the newest:

```
sudo countyctl update v1.4.2
```

**Without internet access from the server,** download the release `.tar.gz`
from GitHub on another computer, copy it to the server, and run:

```
sudo countyctl update --from open-county-portal-1.4.2.tar.gz
```

## If the update fails

You'll see:

```
Version 1.4.2 didn't come up healthy. Going back to 1.4.1 automatically...
Update undone; version 1.4.1 is running again.
```

Nothing more is needed to keep the site running. To help get it fixed, save
the log and attach it to a GitHub issue (remove any personal information
first):

```
cd /opt/county-portal && sudo docker compose logs --tail=300 app > update-problem.log
```

## Go back after a successful update

If the update worked but something about the new version is wrong for you:

```
sudo countyctl rollback
```

This returns the program **and the data** to just before the update. Anything
entered since the update (payments, requests, edits) is removed from the
portal, so check **Finance** for payments taken since the update and record
them before rolling back. A safety backup labeled `before-rollback` is taken
first.

## Operating system updates

Separate from portal updates. See [Server security](security.md).

## Edited files by hand?

`countyctl update` replaces the program files in `/opt/county-portal` (it
never touches `.env` or your data). If someone changed program files there,
the update stops with a message. Put the changes somewhere else, then:

```
cd /opt/county-portal && sudo git status
```

shows what was changed. `sudo git stash` sets the changes aside so the update
can proceed. Changes to the program belong in the project itself, as a
contribution, so they survive updates and other counties benefit.
