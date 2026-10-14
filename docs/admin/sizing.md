# Server size and network needs

## The server

One server runs everything. A virtual machine is fine, on your own hardware
or in a cloud.

| | Minimum | Recommended |
|---|---|---|
| Operating system | Ubuntu 22.04 LTS or Debian 12 | **Ubuntu 24.04 LTS** |
| Processors | 2 | 4 |
| Memory | 4 GB | 8 GB (16 GB above about 5 million record pages) |
| Disk for the system | 20 GB | 40 GB |
| Disk for data | see below | see below, plus room to double |

The installer stops if the server has less than 4 GB of memory or 20 GB free
under `/var/lib/county-portal`.

Put `/var/lib/county-portal` on a disk you can grow later (an LVM volume or a
cloud disk). Most growth comes from record images.

## Estimating data disk

Count the pages of recorded documents you'll put online, then add these
together. The figures are typical, not guarantees: scan resolution and
compression change them a lot, so measure a sample of your own images (see
below).

| What | Typical size |
|---|---|
| Scanned record pages (black-and-white TIFF, 300 dpi) | 40 to 100 KB per page |
| Pages viewed recently (cached display copies) | about 10% on top of the images |
| Database | about 1 GB per million index entries |
| Backups (on the same disk) | the first backup copies all images; later nightly backups add only new or changed files, plus a database copy each night |
| Old website pages and documents | usually under 10 GB |

**Measure your own images:** after you copy an export to the server (see
[Moving your records](migration.md)), run

```
sudo du -sh /var/lib/county-portal/import/*
```

The size of the images folder there is close to what the portal will use for
images, because it keeps your files as they are. While migrating you need
room for both: the export in `import/` and the copy in the portal. Delete the
export once the clerk has signed off.

**A worked example** (an estimate): a county with 2 million pages at 60 KB
per page needs about 120 GB for images, 12 GB for display copies, 3 GB for
the database, and about 130 GB for backups on the same disk the first night.
Plan a 400 GB data disk so there's room to grow.

## Network

**Coming in** (from the internet to the server):

| Port | Why |
|---|---|
| 443 (HTTPS) | the website |
| 80 (HTTP) | redirects to HTTPS, and lets the free certificate be issued and renewed |
| 22 (SSH) | your administration; limit it to your network or VPN |

**Going out** (from the server):

| Destination | Port | Why |
|---|---|---|
| Let's Encrypt (`acme-v02.api.letsencrypt.org`) | 443 | free HTTPS certificate (public mode only) |
| Docker Hub, `download.docker.com`, `apt.postgresql.org`, PyPI (`pypi.org`, `files.pythonhosted.org`), Ubuntu or Debian mirrors | 443 and 80 | installing and updating |
| GitHub | 443 | updates, if you installed with git |
| your email relay | 587 or 465 | receipts and notices |
| your payment processor's API | 443 | card payments |
| your off-site backup destination | depends | backups |
| your old website | 443 or 80 | only while copying old pages |

If your network only allows listed destinations, give your firewall team
this table before you start.

## Where to put it

- **In your own data center:** the server needs a public address, or your
  firewall forwards ports 80 and 443 to it.
- **In a cloud:** any provider with Ubuntu 24.04 works. Choose a region in the
  United States. A government cloud region is fine but not required for this
  data, which is all public except staff accounts, uploads and payment
  records (card numbers never reach the portal).
- **Behind your existing load balancer or reverse proxy:** use
  [provided certificate mode](https.md#provided-certificate) or pass traffic
  through unchanged on 443. Tell your network team the portal handles HTTPS
  itself.

## Check

You're ready when you can SSH to the server and

```
lsb_release -d && nproc && free -g && df -h /var/lib
```

shows a supported system, enough processors and memory, and enough disk.
Next: [Install](install.md).
