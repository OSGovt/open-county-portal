# Moving your records

This guide moves three things into the portal:

1. **Recorded documents** (deeds, liens, plats and their page images) from
   your records management system
2. **Bills** (tax roll, court costs, utility accounts) that residents pay
3. **Pages and documents from your old website**

Nothing is ever changed in the old systems or the export files. The portal
only reads them. Records and bill imports are numbered batches that can be
undone as a whole; old web pages come in as unpublished drafts that go live
only when staff publish them.

You run the commands on the server. Staff review and sign off in the staff
console.

## How files get to the server

Exports go in `/var/lib/county-portal/import` on the server. Inside the
portal, that folder is called `/import`, so commands use paths that start
with `/import/`.

The import folder belongs to the administrator who ran the installer, so that
account can copy files straight into it. Exports can be large: copy them
directly into this folder, not to `/tmp` first, which is on the smaller system
disk.

**From a Windows computer:** use WinSCP (free), signed in as the account that
ran the installer, to copy the export folder to
`/var/lib/county-portal/import/`.

**From a Linux or Mac computer:**

```
rsync -a --progress records-export you@server:/var/lib/county-portal/import/
```

(Signed in as a different administrator? Add `--rsync-path="sudo rsync"`.)

**From a USB drive plugged into the server:**

```
sudo cp -r /media/usb/records-export /var/lib/county-portal/import/
```

After copying, let the portal read the files:

```
sudo chmod -R a+rX /var/lib/county-portal/import
```

## Part 1: Recorded documents

### What to ask your records vendor for

Ask for an export of the index and images. Most vendors can produce one;
it's your data. The portal reads:

- **Index:** CSV, tab-delimited, pipe-delimited or Excel (`.xlsx`), in any
  common encoding, including old Windows encodings. Either one row per
  document, or one row per name (the same document repeated for each grantor
  and grantee) is fine.
- **Images:** TIFF (including multi-page), PDF, PNG or JPEG. One file per
  document or one file per page is fine, in any folder layout.

The index should include at least the instrument (document) number and the
document type. Recording date, book and page, grantor and grantee names,
legal description and property ID make the records far more useful. If the
system marks sealed or confidential documents, ask for that column too.

Ask the vendor for 100 documents first, as a sample, before the full export.
Run the whole process below on the sample, then on the full export.

### Step 1. Look at the export

```
sudo countyctl app migrate records inventory /import/records-export
```

It lists the tables it found, each column with how full it is and sample
values, and the image files by type. Nothing is changed.

### Step 2. Draft the mapping

```
sudo countyctl app migrate records map /import/records-export
```

This writes a mapping file at
`/var/lib/county-portal/data/migration/mapping.yaml` with the portal's best
guess for each field. Every guess is marked `# CHECK`.

(Inside the portal, that folder is called `/data/migration`, and the commands
print it that way. Either name works in commands.)

### Step 3. Check every guess

```
sudo nano /var/lib/county-portal/data/migration/mapping.yaml
```

Go line by line. For each `# CHECK` line, make sure the column name after the
colon is the right column from your export (the inventory in step 1 shows the
column names and sample values). The most important lines:

| Line | What it means |
|---|---|
| `index_file` | the table with the documents |
| `layout` | `one_row_per_document`, or `one_row_per_party` if each row holds one name |
| `instrument_number`, `doc_type` | required |
| `date_format` | how dates are written, such as `"%m/%d/%Y"` for 03/14/1999, or `"%Y-%m-%d"` for 1999-03-14 |
| `grantors`, `grantees` | name columns (one-row-per-document layout); `name_separator` if one cell holds several names |
| `party_name`, `party_role`, `role_values` | the name and role columns (one-row-per-party layout), and which codes mean grantor and grantee |
| `restricted` | a column that marks sealed or confidential documents; these are never shown publicly |
| `doc_type_map` | optional: turn codes into names, such as `{WD: Warranty Deed, DT: Deed of Trust}` |
| `images: folder` | the image folder, relative to the export folder |
| `images: file_name` | how image files are named, using `{instrument_number}`, `{book}`, `{page}` |
| `images: page_suffix` | only if each page is its own file, such as `"_{n}"` for `1999-000123_1.tif` |

Save with Ctrl+O, Enter, then Ctrl+X.

### Step 4. Dry run

```
sudo countyctl app migrate records check /var/lib/county-portal/data/migration/mapping.yaml
```

It reads everything and reports counts: documents, image files found,
documents with no image, missing grantors, grantees or dates, restricted
documents, and problems by line. The full problem list is saved in
`/var/lib/county-portal/data/migration/check-problems.csv`. **Nothing is
changed.**

If the numbers look wrong (for example, every document has no image), fix the
mapping and run the check again. Repeat until the numbers match what the
clerk expects. Some problems are real problems in the old data, such as a
date like `13/45/2002`; those documents are imported with the problem noted,
or skipped if the instrument number is missing.

### Step 5. Back up and load

```
sudo countyctl backup --label before-records-import
```

```
sudo countyctl app migrate records load /var/lib/county-portal/data/migration/mapping.yaml
```

Type `yes` to confirm. The documents come in as a new numbered batch. Images
are copied into the portal with a checksum for each file; multi-page TIFFs
and PDFs are split into pages. Progress is shown every few thousand
documents. Large imports take hours; you can disconnect safely if you start
the command inside `screen` or `tmux`:

```
sudo apt-get install -y tmux && tmux
```

(Reconnect later with `tmux attach`.)

At the end it prints the batch number, such as `Batch 3: 412,880 documents
loaded, 37 skipped or rejected.`

### Step 6. Verify

```
sudo countyctl app migrate records verify --batch 3
```

It picks 50 documents at random and compares each one against the export:
number, type, date, names, page count and image checksums. It writes an HTML
report. Use `--sample 200` for a bigger sample.

### Step 7. Clerk sign-off

In the staff console, **System > Imports** lists every batch. The clerk opens
the verification report, looks up a dozen documents they know in the public
search, and, when satisfied, signs off on the batch. The go-live checklist
waits for this.

### Undo a batch

```
sudo countyctl app migrate records undo --batch 3
```

Type `yes`. A backup is taken first, then every document in that batch is
removed. Fix the mapping and load again.

### Restricted documents and redaction

- Documents marked restricted in the mapping never appear publicly.
- Text is read from scanned pages overnight (up to 20,000 pages a night), so
  text search and the scan below improve over the first nights. To read more
  at once (this takes roughly a second or more per page):

```
sudo countyctl app ocr --limit 50000
```

- Then list pages whose text looks like it holds a Social Security number:

```
sudo countyctl app ssn-scan --batch 3
```

  It writes `/var/lib/county-portal/data/migration/ssn-scan.csv` with a review
  link for each page. Records staff open each link, check the suggested boxes,
  and save the redactions. Redaction is applied whenever a page is shown; the
  original image is kept unchanged for the certified copies the law allows.
  Machine reading misses some numbers on poor scans, so this narrows the work
  but doesn't replace your state's redaction-request process.

## Part 2: Bills

Bills are what residents look up and pay: property tax accounts, court costs,
utility accounts. The billing system stays the system of record. The portal
gets a fresh copy of what's owed, takes payments, and gives finance a file to
post those payments back.

### Step 1. Get an export

Ask for a CSV or Excel export with one row per account: account (or case)
number, name, amount due, and if possible address, due date and a
description. Copy it to `/var/lib/county-portal/import/`.

### Step 2. Draft the mapping

```
sudo countyctl app migrate bills map /import/tax-roll.csv --kind property_tax --office tax-office
```

`--kind` is `property_tax`, `court`, `utility`, `permit` or `other`.
`--office` is the office that collects them: its short name, shown as "Web
address" when you edit the office in **Content > Offices**. It writes
`/var/lib/county-portal/data/migration/bills-property_tax.yaml`.

### Step 3. Check the mapping

```
sudo nano /var/lib/county-portal/data/migration/bills-property_tax.yaml
```

Check each column marked `CHECK`, and these settings:

| Setting | Meaning |
|---|---|
| `amount_in_cents` | `true` if the export shows 21843 for $218.43 |
| `allow_partial` | whether residents may pay part of a bill |
| `sync` | `true` sets accounts missing from the file to $0 due, because they were paid or closed in the billing system. Use it only with a complete export of every open account. As a safety net, a load that would set more than 20% of accounts to $0 stops without changing anything (add `--force` if it's really right) |

### Step 4. Dry run

```
sudo countyctl app migrate bills check /var/lib/county-portal/data/migration/bills-property_tax.yaml
```

It shows the row count, account count and total due. Compare the total with
the billing system's report. Nothing is changed.

### Step 5. Load

```
sudo countyctl app migrate bills load /var/lib/county-portal/data/migration/bills-property_tax.yaml
```

New accounts are added and existing ones updated. It prints the batch
number. To put the bills back exactly as they were before the latest load:

```
sudo countyctl app migrate bills undo --batch 7
```

### Keep bills fresh every night

Have the billing system (or a scheduled task on the billing server) drop a
fresh export at the same path each night, then add a nightly load on the
portal server:

1. Create the job:

```
sudo nano /etc/systemd/system/county-portal-bills.service
```

2. Paste this, changing the file name to yours, then save:

```
[Unit]
Description=Load tonight's bill export into the portal
[Service]
Type=oneshot
ExecStart=/usr/local/bin/countyctl app migrate bills load /var/lib/county-portal/data/migration/bills-property_tax.yaml
```

3. Create the schedule:

```
sudo nano /etc/systemd/system/county-portal-bills.timer
```

4. Paste this (4:00 a.m., after the billing export), then save:

```
[Unit]
Description=Load bills nightly
[Timer]
OnCalendar=*-*-* 04:00:00
Persistent=true
[Install]
WantedBy=timers.target
```

5. Turn it on:

```
sudo systemctl daemon-reload && sudo systemctl enable --now county-portal-bills.timer
```

### Post payments back to the billing system

Finance downloads the payments to post: **Finance > Download bill payments to
post (CSV)** for a date range. The file lists each payment with account,
amount, date and receipt number for import into the billing system.

## Part 3: The old website

### Step 1. Copy the old site

```
sudo countyctl app migrate site crawl https://www.example-county.gov
```

It reads the old site one page per second (gentle on old servers), follows
links within the site, saves a full copy of every page, and downloads linked
documents (PDF, Word, Excel and similar, up to 50 MB each). It respects the
site's `robots.txt`. If your own site blocks crawlers and you have
permission, add `--ignore-robots`. Other options: `--max-pages 5000`,
`--delay 2` (seconds between pages).

Nothing on the old site is changed.

### Step 2. Import as drafts

```
sudo countyctl app migrate site import
```

Each old page becomes an **unpublished** draft page, documents are attached,
and a redirect is created from each old address to its new one, so old
links, bookmarks and search results keep working after cutover.

### Step 3. Review in the staff console

**Content > Pages waiting for review** lists the imported pages. For each one,
staff from the owning office:

- fix outdated information
- fix problems the import flagged: images without descriptions, headings out
  of order, links that say "click here", tables used for layout
- move service information into **Services**, where it's more useful to
  residents, and delete the draft
- publish what should stay

**Content > Redirects** shows every old address and where it goes. Change a
redirect if you moved content elsewhere.

## Check

- The clerk has signed off every records batch (**System > Imports**).
- Bills total matches the billing system.
- Spot-check 20 old addresses: `https://new-address/old/page.html` should land
  on the right new page.

Next: [Connect a payment processor](payments.md).
