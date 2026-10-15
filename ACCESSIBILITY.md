# Accessibility

Open County Portal's goal is that every resident can use their government's
website, whatever their abilities, device or connection.

## The standard

Every release targets **WCAG 2.1 Level AA**, the standard the Department of
Justice's ADA Title II rule requires of state and local government websites,
and follows WCAG 2.2 AA practices where practical.

## How it's checked

- **Every pull request** runs the conformance suite in CI: axe-core WCAG 2.1
  A/AA checks on every public page at desktop and 320-pixel phone widths,
  keyboard skip-link and visible-focus checks, and error handling on every
  public form.
- **Every new interaction** is tested by hand with a keyboard and a screen
  reader before release.
- **Every installation** can run the same suite against itself
  ([conformance/README.md](conformance/README.md)) and follow the manual review
  in [docs/admin/accessibility-testing.md](docs/admin/accessibility-testing.md).

## How it's built

- Server-rendered HTML that works without JavaScript
- Semantic headings, landmarks and labels; a skip link on every page
- Error summaries that receive focus and link to each field
- 44-pixel touch targets; layouts that reflow to 320 pixels
- A theme engine that repairs or refuses colors below contrast minimums
- A staff session timeout warning with a one-step extension
- Machine-read text for scanned records, and an accessible-version request
  on every document; text for redacted pages is read from the redacted image
- No CAPTCHAs

## Known limits

- Scanned historical records are images. Machine-read text helps but isn't
  perfect; the accessible-version request is the remedy.
- Documents a county uploads (agendas, budgets) are only as accessible as
  they're made. The guides explain how to make accessible PDFs.
- Automated testing finds only part of real-world problems; the manual review
  matters.

## Reporting a barrier

- **On a county's website:** use that site's Accessibility page; the county
  responds.
- **In the software itself:** open an issue labeled `accessibility`
  describing the page, what you were doing, your browser and assistive
  technology, and what happened. Accessibility bugs are treated as release
  blockers. If you'd rather not use GitHub, email accessibility@osgovt.com.
