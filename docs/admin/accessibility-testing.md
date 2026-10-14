# Accessibility testing

## Why this matters

The Department of Justice's ADA Title II rule requires state and local
government websites to meet WCAG 2.1 Level AA. Under the April 2026 interim
final rule (91 Fed. Reg. 20902) the compliance dates are:

| Your government | Compliance date |
|---|---|
| Population 50,000 or more | April 26, 2027 |
| Population under 50,000, and **every special district** | April 26, 2028 |

Rules can change; check ADA.gov for the current dates. The staff console
dashboard shows your date once you've entered your population in **Settings >
Site identity**.

The portal is built to meet WCAG 2.1 AA, and every release is checked
automatically. But your site also contains your content (pages, notices,
uploaded documents) and your colors and logo. This guide is how you check the
whole thing before go-live and after big changes.

It has two parts: the automated check, which takes minutes, and a manual
review, which takes about half a day and catches what machines can't.

## Part 1: Automated check

Run it from a computer that can reach the portal: a workstation or a spare
Linux machine is best, so the browser it uses isn't installed on the live
server. These steps are for Ubuntu (on Windows, use WSL with Ubuntu).

1. Install the tools and get a copy of the project (use the same release as
   your portal):

```
sudo apt-get install -y git python3-venv nodejs npm
```

```
git clone --branch v1.0.0 https://github.com/OWNER/open-county-portal.git && cd open-county-portal/conformance
```

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```
sudo .venv/bin/playwright install-deps chromium && .venv/bin/playwright install chromium && npm ci
```

2. Run the checks (from the `conformance` folder):

```
.venv/bin/python run.py --url https://portal.example-county.gov
```

It checks every public page it can find at desktop width and at a 320-pixel
phone width, the first keyboard stop on each page, every public form's error
handling, the open API and the data catalog. The report it names (in
`conformance/reports/`) lists failures first, each with a link explaining the
problem.

**Fix every FAIL before go-live.** Most failures in a new installation come
from content: an image added to a page without a description, a heading
skipped, a link that says "click here". Fix them in **Content**.

Automated tools find only part of real problems. That's why Part 2 exists.

## Part 2: Manual review

Pick two people: someone from IT and someone from an office that serves the
public. Do each task below in each way listed, and write down anything that's
confusing, slow or impossible. Use sample data
(`sudo countyctl app demo`) so nothing real is affected.

### The tasks

1. Find the County Clerk's office hours and phone number.
2. Search property records for a name, open a document, view its pages, and
   download the free copy.
3. Order a certified copy of a document, through payment.
4. Look up a property tax bill by account number and pay part of it.
5. Find the next commissioners court meeting and open its agenda.
6. Submit a public information request.
7. Fill in a form (a permit, a marriage license application), submit it
   empty first to see the errors, then correctly.
8. Find out how to report an accessibility barrier, starting from the footer.

### The ways

**Keyboard only.** Unplug the mouse or don't touch the trackpad. Use Tab,
Shift+Tab, Enter, Space and the arrow keys.

- [ ] The first Tab on every page shows a "Skip to main content" link
- [ ] You can always see where you are: there's a clear outline around the
      focused item
- [ ] You can reach and use everything, including the payment page and the
      cart
- [ ] Focus never gets stuck, and it moves in a sensible order
- [ ] After a form error, focus moves to the list of problems, and each item
      jumps to its field

**Screen reader.** Use one free option:

- Windows: NVDA (nvaccess.org) with Firefox or Chrome
- Mac: VoiceOver (Command+F5) with Safari
- iPhone: VoiceOver (Settings > Accessibility); Android: TalkBack

Learn five commands first: start/stop reading, next heading, next link, next
form field, activate. Then:

- [ ] Each page's title says where you are
- [ ] Headings make sense as an outline of the page
- [ ] Every form field announces its label, and whether it's required
- [ ] Errors are announced when they appear
- [ ] Images that carry meaning (the seal, document pages) have descriptions;
      decorative ones are silent
- [ ] Tables (fees, search results) announce their column headers

**Zoom and phone.**

- [ ] At 200% browser zoom, nothing overlaps or gets cut off
- [ ] At 400% zoom on a laptop, pages read top to bottom without scrolling
      sideways
- [ ] On a phone, every task works, and buttons are easy to tap

**Color and contrast.**

- [ ] The theme's contrast check showed all pairs passing (it won't publish
      otherwise)
- [ ] Nothing is shown by color alone: errors also say what's wrong in text

**Time.**

- [ ] Staff get a warning before being signed out and can stay signed in with
      one action
- [ ] Nothing on the public site times out while a resident is filling in a
      form

**Documents.**

- [ ] PDFs uploaded to pages (agendas, budgets, forms) are tagged, readable
      PDFs, not scans of paper. Ask whoever makes them to export from Word
      with "Create PDF/UA" or "Best for electronic distribution and
      accessibility" turned on.
- [ ] Old documents imported from the previous website were reviewed (the
      import flags them)
- [ ] Recorded document images are scans and can't be made fully accessible;
      the site offers machine-read text and an accessible-version request on
      every document page. Make sure records staff know how to respond to
      those requests.

## Record what you found

Keep a dated list of problems, who will fix each, and when. Fix, then check
again. This list is also your evidence of good-faith effort if anyone asks.

When the review is done and the problems are fixed, check "Someone tested the
main tasks with only a keyboard and with a screen reader" on the go-live
checklist (**System > Go-live checklist**).

## After go-live

- Run the automated check monthly and after every update (it can run on a
  schedule; it exits with an error when anything fails).
- Repeat the manual review once a year, and after any big content change.
- Read every barrier report residents send from the Accessibility page, and
  answer within the time your accessibility statement promises.

Next: [Register with Data.gov](data-gov.md).
