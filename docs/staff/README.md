# Staff guide

The staff console is at `https://your-portal-address/staff`. You see only the
parts your role needs. **Help** in the menu opens these guides.

If you haven't signed in before, see
[First sign-in](../admin/staff-accounts.md#first-sign-in-for-the-staff-member).
You'll be signed out after 60 minutes without activity; a message appears
five minutes before, with a button to stay signed in.

The **Dashboard** shows what's waiting for you: copies to prepare, requests to
answer, applications to review, online orders to collect.

## Content editors

**Content** has a list for each kind of item: Pages, Services, Offices,
Meetings, Notices and Redirects. Choose one to see everything of that kind,
then **New** or **Edit**.

- **Write plainly.** Short sentences, common words, the most important thing
  first. Say what the resident needs to bring, pay and do.
- **Headings** in order: the page title is the main heading; sections under
  it; sub-sections under those. Don't pick a heading for its size.
- **Links** say where they go: "Download the 2027 budget (PDF)", not "click
  here".
- **Images** need a short description of what they show, unless they're only
  decoration.
- **Documents:** upload tagged PDFs made from Word ("Save as PDF" with
  accessibility options on), not scans. Better still, put the information on
  the page itself.
- **Pages waiting for review** on the Content page lists pages brought over
  from the old website. Each one notes what to check. Fix, then publish, or
  delete it if it's out of date.

**Meetings:** create the meeting with its date and time, attach the agenda,
and set it to posted. The dashboard warns if a meeting in the next 72 hours
isn't posted. After the meeting, attach the minutes.

**Notices:** choose the legal requirement the notice satisfies from the list,
so the dashboard knows it's been posted.

**Redirects** send an old web address to its new page. Most were created
automatically when the old site was imported.

**The alert banner** (closures, emergencies) is under **Settings > Site
identity and alert**, for administrators.

## Records clerks

**Records:** find a document by instrument number or name.

On a document's page you can:

- **Correct the index** (type, names, legal description, property ID,
  remarks). Give a reason; it's kept in the audit log. The official page
  images are never changed.
- **Change who can see it:** public or restricted. Restricted documents
  disappear from the public site and the open data immediately.
- **Redact a page:** open the page, drag a box over the information to hide,
  and give the reason. **Scan this page** suggests boxes over anything that
  looks like a Social Security number; check each one. Redaction is applied
  whenever the page is shown to the public; the original image is kept for
  certified copies the law allows.
- **Re-read the text of every page** if the machine-read text is poor.

**Redaction requests** (from the dashboard or **Records**): each request shows
the documents naming the person. Decide, note why, and save. Approved
requests hide the listed information; rescinded ones remove the hiding.

**Copy orders:** certified copies residents paid for online. **Issue certified
PDF and email it** makes a PDF with a certification page and a verification
code anyone can check on the website. For paper copies, print, certify by
hand, and choose **Mark paper copy mailed or picked up**.

**Accessible version requests:** a resident who can't read a scanned page can
ask for an accessible version from the document's page. These arrive in
**Applications** as "accessible-version" requests, so records clerks who
handle them also need the `applications` role. Send a readable version (typed
text or a tagged PDF) by email, then mark the request completed.

## Cashiers

**Counter.**

1. **Open a drawer:** choose your drawer (or a new one for your office) and
   count the starting cash.
2. **Add items:** find a fee and set the quantity, or look up a bill by
   account, name or address and enter the amount (blank pays the full
   balance). **Saved online orders** has orders residents made online to pay
   in person.
3. **Take payment:** enter a reference (the instrument, case or customer
   name), the method, and cash given, check number or escrow account.
   **Complete sale.**
4. **Receipt:** print it with Ctrl+P.
5. **Close drawer** at the end of the shift: count the cash. The portal shows
   what it expected and any difference. Note the reason for any difference.

For card payments on a terminal that isn't connected to the portal, run the
card on the terminal, then record the sale as card.

Mistakes before completing a sale: **Remove** an item or **Clear sale**. After
completing: ask a supervisor to void it.

## Supervisors

- **Void a sale:** on the **Close drawer** page, enter the order number and a
  reason. Bill balances and escrow are restored. If the payment went through
  a connected processor, it's refunded to the card first; if the refund
  fails, nothing is voided and the message says why. For cash, return the
  money from the drawer.
- Review drawer close-outs and differences in **Finance**.

## Finance

**Finance** shows collections for any date range: by office and fund, by
payment type, and by drawer, plus voided sales.

- **Download ledger (CSV)** for the general ledger.
- **Download bill payments to post (CSV)** to load into the tax, court or
  utility system.
- **Escrow accounts:** add accounts for title companies and attorneys, record
  deposits, and see balances and history.

## Public information officer

**Public information** lists open requests. On each:

- Set the status: received, asked to clarify, sent a cost estimate, asked the
  Attorney General for a ruling (or your state's equivalent), released,
  closed. The requester is emailed when the status changes.
- **Response to the requester** is sent with the status.
- **Staff notes** are never published.

Check **Publish this request and response in the public archive** to show it
on the public archive page and in the open data.

## Applications reviewers

**Applications** lists submitted forms (permits, licenses, jury responses).
Open one to see the answers and files. Viewing an uploaded ID is recorded in
the audit log. Set the status (in review, approved, denied, completed) with an
optional message; the applicant is emailed. ID uploads are deleted
automatically after the retention period.

## If something looks wrong

Tell your administrator: what you were doing, the page address, and what you
saw. Nothing you do in your role can break the site, and almost everything
can be undone.
