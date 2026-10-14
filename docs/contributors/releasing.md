# Releasing (maintainers)

Counties update with `countyctl update`, which installs the newest `v*` git
tag, or a release file. A release must therefore be complete, tested, and
safe to install unattended.

## Version numbers

`MAJOR.MINOR.PATCH`:

- PATCH: fixes only, no new settings, no manual steps.
- MINOR: new features; may add numbered schema steps; no manual steps.
- MAJOR: anything an administrator must do by hand. The changelog lists the
  steps, in order, with commands.

## Checklist

1. CI is green on `main`, including the image build job.
2. Install the release candidate on a clean Ubuntu 24.04 server with
   `deploy/install.sh`, and update a server running the previous release with
   `countyctl update --from` the candidate archive. Both must pass
   `countyctl doctor` and the conformance suite.
3. Test the automatic rollback once per minor release: break the candidate's
   health check on purpose and confirm `countyctl update` returns to the
   previous version.
4. Update `VERSION` and `CHANGELOG.md` (sections for residents, staff and
   administrators, and any action needed).
5. Tag and push:

```
git tag -a v1.1.0 -m "Open County Portal 1.1.0" && git push origin v1.1.0
```

6. Attach a release archive to the GitHub release, for servers without git:

```
git archive --format=tar.gz --prefix=open-county-portal-1.1.0/ -o open-county-portal-1.1.0.tar.gz v1.1.0
```

7. Publish the release notes, and post to the project's announcement channel
   for administrators.

## Security releases

Fix privately (see SECURITY.md), release as a PATCH, and say plainly in the
release notes what was affected and whether any action beyond updating is
needed.

## Pinned dependencies

`requirements.txt` pins every package. Review updates monthly; update in a
PATCH or MINOR release after the full checklist. The Docker base image and
`postgres:16-alpine` / `caddy:2-alpine` tags pick up security fixes when an
administrator updates; a PostgreSQL major-version change would be a MAJOR
release with a dump-and-restore step.
