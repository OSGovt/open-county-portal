# Writing a state pack

A state pack teaches the portal one state's rules: which offices a county
has, what services residents expect, which fees state law sets, which notices
must be posted online and how often, what the public information law is
called, which personal information can be hidden from online records, and
which state websites residents should be sent to.

The portal works without a pack (it starts blank and staff add everything by
hand), but a good pack saves every county in the state days of setup and
catches legal requirements a new administrator wouldn't know.

A pack is one file: `portal/statepacks/<two-letter code>/pack.yaml`. No
programming is needed.

The examples on this page use Ohio as a running example. **Their statute
numbers, amounts and wording are placeholders to show the shape, not checked
Ohio law.** The Texas pack (`portal/statepacks/tx/pack.yaml`) is a
complete worked example of every section.

## Rules

1. **Every rule cites its source:** the statute, administrative rule, or
   official guidance, with a link when one exists.
2. **Fee amounts are templates.** Counties confirm each fee against their own
   adopted order before go-live; the portal enforces that.
3. **Status stays `draft`** until someone with expertise in that state's
   county law (a county attorney, a state association of counties lawyer, a
   clerk's association) reviews it and is named in `reviewed_by`. Say so
   plainly in the pack's documentation page until then.
4. **Plain language** in everything residents see: titles, summaries, form
   labels.

## Start

1. Copy the template:

```
cp -r portal/statepacks/_template portal/statepacks/oh
```

2. Set the top of `pack.yaml`:

```yaml
pack: oh
name: Ohio
version: "2026.11"      # year.month of this edition
status: draft
reviewed_by: null
```

3. Validate as you go:

```
python -m portal.cli pack validate portal/statepacks/oh
```

## The sections

### `sources`

The statutes and guidance the pack relies on, listed once:

```yaml
sources:
  - title: Revised Code 317.32 (county recorder fees)
    url: https://codes.ohio.gov/ohio-revised-code/section-317.32
```

### `offices`

The offices a typical county has. `slug` is a short name used everywhere
else in the pack.

```yaml
offices:
  - slug: county-recorder
    name: County Recorder
    description: Records deeds, mortgages and other documents about land.
```

### `services`

What residents come to do. Each belongs to an office.

```yaml
services:
  - slug: property-records
    office: county-recorder
    title: Search property records
    summary: Deeds, mortgages and plats, free to search and download.
    category: Records              # groups services on the Services page
    featured: true                 # shown on the home page
    online_label: Search records   # button text
    online_target: /records        # where the button goes
    keywords: deed mortgage plat grantor grantee
```

### `fees`

Fees set by state law. Each needs `code`, `office`, `label`, `amount` and
`statute`. Optional: `unit` (what one fee covers, such as `page` or
`document`) and `fund` (for finance reports).

```yaml
fees:
  - code: rec_first
    office: county-recorder
    label: Recording, first two pages
    amount: 34.00
    unit: document
    statute: Revised Code 317.32(A)
    fund: General Fund
```

Fees that vary by county, or that a county sets by its own order, belong in
the pack only if the statute sets a default or a maximum; say which in the
label or a comment.

### `postings`

Notices state law requires on the website. The dashboard warns when one is
missing or late.

```yaml
postings:
  - code: meeting-notice-agenda
    title: Meeting notice and agenda
    authority: Revised Code 121.22(F)
    cadence: per_meeting       # per_meeting, annual, per_election, ongoing
    office: commissioners
    max_age_days: 400          # optional: warn when the latest posting is older
    note: What must be posted, when, and where, in one or two sentences.
```

`per_meeting` checks that meetings in the next 72 hours are posted. Other
cadences check that something has been posted under this code (and, with
`max_age_days`, recently enough). Use `automatic: true` for a requirement the
portal itself satisfies, such as posting how to submit public information
requests.

### `records`

```yaml
records:
  online_notice: "Text state law requires on an online records database, if any."
  online_notice_source: "The statute"
  copy_fees_reach_free_downloads: undecided   # yes, no, or undecided: does the copy fee statute apply to free online viewing?
  redaction:
    law: The statute allowing people to hide information from online records
    fields: [social security number, residence address]
    categories: [Peace officer, Judge]        # who may ask
    form_note: Which form to use, if the state prescribes one.
```

### `public_information`

```yaml
public_information:
  law_name: Ohio Public Records Act
  intro: One or two plain sentences residents see on the request page.
  response_rule: How quickly the government must respond, in plain words.
  business_days: null        # a number if the law sets a deadline in business days
```

### `payments`

```yaml
payments:
  card_fee_law: The statute allowing a card processing fee, and its limits
  dishonored_card_law: The statute on returned or declined payments
```

### `handoffs`

State websites residents should be sent to rather than served locally
(vehicle registration, e-filing, voter information):

```yaml
handoffs:
  - code: vehicle-renewal
    title: Ohio BMV online services
    url: https://bmv.ohio.gov/
```

### `forms`

Forms residents submit online. Each has a title, an office, an optional fee,
and fields.

```yaml
forms:
  vital-record:
    title: Request a birth or death certificate
    office: health-department
    fee_code: birth_cert
    fields:
      - {name: applicant, label: Your full name, type: text, required: true, autocomplete: name}
      - {name: record_type, label: "Which certificate?", type: radio, required: true, options: [Birth certificate, Death certificate]}
      - {name: id_photo, label: Photo of your government-issued ID, type: file, required: true, accept: "image/*,application/pdf", sensitive: true, hint: On a phone, this opens your camera.}
```

Field types: `text`, `email`, `tel`, `date`, `textarea`, `select`, `radio`,
`checkbox`, `file`, `number`. `select` and `radio` need `options`. Mark ID
uploads `sensitive: true` so they're deleted after the retention period.
Ask only for what the law or the office truly needs.

### `district_profile`

Special districts and school districts are much simpler than counties. This
section replaces offices, services, postings, fees and forms for them:

```yaml
district_profile:
  offices: [...]
  services: [...]
  postings: [...]
  fees: []
  forms: {}
```

## Test it

1. Validate:

```
python -m portal.cli pack validate portal/statepacks/oh
```

2. Run the project's tests (see the [contributors guide](../contributors/README.md));
   one test validates every pack.

3. Install it on a test server for a county and a district, and look at every
   service, office and form page:

```
sudo countyctl app setup --name "Test County" --type county --state oh
```

## Submit it

Open a pull request with the pack and a documentation page
`docs/state-packs/oh.md` modeled on [texas.md](texas.md): what the pack
covers, its sources, what's not covered, and its review status. Reviews from
people who practice county law in that state are especially welcome.

## Keep it current

Laws change every legislative session. Each pack's documentation page names
who maintains it. When a law changes: update the rule and its source, bump
`version`, and note the change in `CHANGELOG.md`. Counties get it with their
next update; fee changes still need each county's confirmation.
