# Style the site

You can make the portal look like your county without writing any code, and
without being able to break its accessibility. Every color combination is
checked before it can be published, and every published version can be
restored.

All of this is in the staff console, for staff with the `admin` role.

## 1. Site identity

**Settings > Site identity.** Fill in:

| Field | Shown |
|---|---|
| Name | header, page titles, receipts |
| Tagline | under the name in the header (optional) |
| Main address, phone, email | footer |
| How to report an accessibility barrier | the Accessibility page. Required: a name, phone and email |
| Appraisal district website | property tax pages |
| Population | sets your federal accessibility deadline on the dashboard |
| Census Bureau government ID, FIPS code | the national directory and open data |
| Time zone | dates and meeting times, such as `America/Chicago` |

## 2. Start from your old site's colors (optional)

**Settings > Theme > Start from the old site.** Enter your current website's
address and choose **Import colors as a preview**. The portal reads the old
site's style sheets (it doesn't change anything there) and suggests colors.
They go into a preview, not the live site.

## 3. Choose colors, type and logo

**Settings > Theme.**

- **Colors:** each color has a label saying where it's used. Type a hex code
  such as `#0B5563`.
- **Font:** a system font (fast, nothing to download) or a custom one. For a
  custom font, give its name and an `https://` stylesheet address, for
  example from Google Fonts.
- **Base text size:** 16 to 22 pixels. Larger helps older residents; 18 is a
  good choice.
- **Corner rounding:** 0 (square) to 16 pixels.
- **Logo or seal:** PNG, SVG, JPG or WEBP. Write a description for screen
  readers, such as "Example County seal". Choose whether to show the county
  name next to the logo.

## 4. Preview

Choose **Preview changes**. The Theme page comes back with your changes saved
as a preview (not live), a **Contrast check** table beside the form listing
every text-and-background pair with its contrast ratio, and a link to open a
sample of the site in the new style.

If a color doesn't have enough contrast to meet WCAG 2.1 AA (4.5 to 1 for
text), the portal moves it lighter or darker, keeping the same hue, until it
passes, and lists exactly what it changed. You'll see lines such as:

> Links on the page background: changed link from #3A8FB7 to #2B6E8D so it reaches 4.5:1 contrast.

If you don't like an adjustment, pick a different color and preview again.
A theme that fails can't be published.

**Discard preview** throws the preview away. The live site never changed.

## 5. Publish

**Publish to the live site.** Residents see it on their next page load.

## Undo

**Settings > Theme > Earlier versions** lists every published theme with who
published it and when. **Restore** puts that version back on the live site
immediately.

## The alert banner

**Settings > Site identity > Alert banner** shows a message at the top of
every page: office closures, weather, a burn ban. Check **Show the alert
banner**, write a title and message, and optionally a link. Uncheck it to
remove the banner.

## What you can't change, and why

The layout, spacing, focus outlines, text sizes relative to the base size,
and the order of things on the page are fixed. They were built and tested to
work with screen readers, keyboard-only use, 400% zoom and phones down to 320
pixels wide. Changing them through custom CSS would mean retesting all of
that, so the theme engine doesn't offer it. If your county needs a layout
change, propose it to the project so every county benefits from the testing.

## Check

After publishing, look at the home page on a phone and a computer. Then run
the conformance suite's accessibility checks
([Accessibility testing](accessibility-testing.md)).

Next: [Move your records](migration.md).
