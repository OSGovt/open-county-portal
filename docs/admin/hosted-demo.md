# Demonstration site: Utopia County, Nirvana

A public demonstration of Open County Portal: a fictional county with 200,000
generated recorded documents, bills, meetings and notices. Nirvana's laws,
fees and citations are invented too (state pack `zn`), so the demo never
presents real law, and every page image says SAMPLE.

- **Part 1** runs it on your own computer to look around. Nothing is public.
- **Part 2** puts it on the internet at `https://utopia.osgovt.com` on
  Cloudflare, using the Workers Paid plan you already have. There's no server
  to maintain, and nothing runs on your computer once it's deployed.

## Part 1: On your own computer

You need Docker and access to hub.docker.com (the first start pulls the
`postgres:16-alpine` image; on a network that blocks Docker Hub, start on a
different network or ask your IT group for a registry mirror).

- **Linux**: install Docker Engine (`sudo apt-get install -y docker.io` on
  Ubuntu, then `sudo usermod -aG docker $USER` and sign in again), then skip to
  step 4.
- **Mac**: install Docker Desktop from docker.com, open it once, then skip to
  step 4.
- **Windows**: you need WSL (Ubuntu) and Docker Desktop; steps 1 to 3 set
  those up.

### 1. Check what's installed

In a Windows Terminal (PowerShell) window:

```
wsl -l -v; docker version --format "{{.Server.Version}}"
```

- If Ubuntu is listed and a Docker version number prints, skip to step 4.
- If `wsl` isn't found or Ubuntu isn't listed, do step 2.
- If Docker isn't found, do step 3.

### 2. Install Ubuntu on WSL

In PowerShell **opened as Administrator**:

```
wsl --install -d Ubuntu-24.04
```

Restart when asked. Ubuntu opens and asks for a username and password; choose
any.

### 3. Install Docker Desktop

Download and install Docker Desktop for Windows from docker.com. Open it, go
to **Settings > Resources > WSL integration**, turn on **Ubuntu-24.04**, and
choose **Apply & restart**.

### 4. Get the portal

On Windows, open **Ubuntu** from the Start menu; on Linux or Mac, open a
terminal. Then:

```
sudo apt-get update && sudo apt-get install -y git && git clone https://github.com/OSGovt/open-county-portal.git ~/open-county-portal && cd ~/open-county-portal && ls
```

(On a Mac, `git` is already there; skip the `apt-get` part.)

You should see `README.md`, `deploy`, `docs` and other folders.

### 5. Start it

```
cd ~/open-county-portal && ./deploy/local/start.sh
```

The first run builds the portal (5 to 10 minutes) and then generates Utopia
County (about a minute). At the end it prints:

```
Open County Portal is running: http://localhost:8080
Staff console:                 http://localhost:8080/staff
  Email:              admin@example.com
  Temporary password: Abcde-Fghij-Klmno-Pqrst
```

### 6. Look around

Open `http://localhost:8080` in your browser. Try a records search for `smith`,
open a document, view its pages and download the PDF, look up a property tax
bill, and open the Open data page and `http://localhost:8080/api/v1/instruments?name=garcia`.

Sign in to `http://localhost:8080/staff` with the email and temporary
password. You'll set up a phone code and your own password.

### 7. Stop or erase it

Stop (keeps everything):

```
cd ~/open-county-portal && docker compose -f deploy/local/docker-compose.yml stop
```

Erase everything:

```
cd ~/open-county-portal && docker compose -f deploy/local/docker-compose.yml down -v && rm deploy/local/.env
```

## Part 2: On the internet with Cloudflare

### How it works

Cloudflare Containers runs the whole demonstration in one container: the
portal and its own small database, with Utopia County already loaded. A
Cloudflare Worker in front sends every visitor to that one container.

- **When nobody visits for 20 minutes, the container goes to sleep.** It
  costs nothing while asleep. The next visitor wakes it in seconds (the first
  visit after a deploy can take a minute or two).
- **Every wake-up is a fresh copy.** Anything visitors changed (test payments,
  form submissions, staff edits) is gone, so the demo always looks right and
  nobody can vandalize it for long.
- **Visitors can try the staff console.** The sign-in page shows a shared
  demonstration account and its six-digit code. That account can do
  everything except administration (no user, theme or settings changes).
- **The container can't reach the internet.** Nothing in it can send email or
  contact any other site.

**Cost.** The Workers Paid plan includes 25 GiB-hours of container memory, 375
vCPU-minutes and 200 GB-hours of disk each month (Cloudflare's pricing page,
October 2026). The demo uses the `standard-1` size (half a CPU, 4 GiB memory),
so about the first 6 awake hours each month are included; after that it's
roughly 4 cents an hour while awake. If it's awake 2 hours a day, expect about
$2 a month on top of the $5 plan. The `basic` size (a quarter CPU, 1 GiB) costs
a quarter as much; it should fit but I haven't tested it, so it isn't the
default.

There are two ways to send it to Cloudflare. **GitHub** builds and deploys it
on GitHub's computers every time the code changes, so nothing runs on yours.
**Your own computer** works too, but needs Docker installed.

### 1. Add the domain to Cloudflare

Register the domain (for example `osgovt.com`) and add it to your Cloudflare
account with its nameservers pointed at Cloudflare. Wait until Cloudflare shows
it as **Active**. The demo lives at `utopia.osgovt.com`; the rest of the domain
(the bare domain, email records) stays yours to use. **Keep the nameservers at
Cloudflare:** if they point elsewhere, Cloudflare can't connect the demo's
address. Email hosted somewhere else only needs its MX, SPF and DKIM records
added in Cloudflare's DNS.

### 2. Deploy with GitHub (recommended)

**a. Create a Cloudflare API token.** Cloudflare dashboard > your profile icon
(top right) > **Profile** > **API Tokens** > **Create Token** > **Edit
Cloudflare Workers** > **Use template**. Under **Account Resources** pick your
account; under **Zone Resources** pick **Specific zone** and your domain.
Choose **Continue to summary** > **Create Token**, and copy the token. It's
shown only once.

**b. Find your account ID.** It's the long string of letters and numbers
right after `dash.cloudflare.com/` in the address bar when you're signed in to
the dashboard.

**c. Store both in GitHub.** In your copy of the repository on GitHub:
**Settings** > **Secrets and variables** > **Actions** > **New repository
secret**, twice:

| Name | Value |
|---|---|
| `CLOUDFLARE_API_TOKEN` | the token from step a |
| `CLOUDFLARE_ACCOUNT_ID` | the account ID from step b |

**d. Deploy.** **Actions** > **Deploy demo** > **Run workflow**. After that it
runs on its own every time CI passes on `main`. The first run takes about 15
minutes: it builds the portal and Utopia County's 200,000 records, uploads
them, connects the address, and waits until the demo answers. A green check
means it's live.

The workflow only runs in the `OSGovt` organization's repository. To use it in
your own, change `github.repository_owner == 'OSGovt'` in
`.github/workflows/deploy-demo.yml`, and the address in
`deploy/cloudflare/wrangler.jsonc`.

### 3. Or deploy from your own computer

You need Docker Desktop and Ubuntu from Part 1.

Install Node.js 22 (Ubuntu's own is older):

```
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt-get install -y nodejs && node --version
```

Install the deploy tool:

```
cd ~/open-county-portal/deploy/cloudflare && npm ci
```

Sign in to Cloudflare. A browser window asks you to allow access; choose
**Allow**:

```
cd ~/open-county-portal/deploy/cloudflare && npx wrangler login
```

With Docker Desktop running, deploy (5 to 10 minutes the first time):

```
cd ~/open-county-portal/deploy/cloudflare && npx wrangler deploy
```

If it says the address can't be used, the domain isn't active in this
Cloudflare account yet (step 1).

### 4. Open it

Go to `https://utopia.osgovt.com`. The first visit wakes the container: you may
see "Utopia County is starting" for a minute, and the page retries on its own.

Try a records search, a document's pages and its free PDF, a property tax bill
and the test payment (card `4242 4242 4242 4242`), the open data page and
`https://utopia.osgovt.com/api/v1/instruments?name=garcia`, and the staff
console at `https://utopia.osgovt.com/staff`.

### 5. Check it

From the `conformance` folder of your copy (setup in
[Accessibility testing](accessibility-testing.md#part-1-automated-check)):

```
.venv/bin/python run.py --url https://utopia.osgovt.com
```

## Automatic checks

After every deploy, and once a night, GitHub runs the **Live demo check**
(`.github/workflows/live-check.yml`) against the demo:

- a walk-through of whole tasks in a real browser
  (`conformance/demo_journey.py`): records search, a document's page image
  and PDF, the open API, a test payment from bill lookup to receipt, and the
  demo staff sign-in with its six-digit code;
- the [conformance suite](../../conformance/README.md): accessibility, the
  API, bulk files and the Data.gov catalogs.

If anything fails, it opens a GitHub issue labeled `live-check` with what
broke and a link to the full reports; the next passing run closes it. Start
it by hand from **Actions** > **Live demo check** > **Run workflow**.

## Running it afterward

- **Change something and redeploy:** push to `main` (GitHub deploys after CI
  passes), or run the deploy command again. Visitors see the new version from
  their next visit.
- **Watch it:** Cloudflare dashboard > **Workers & Pages** > `utopia-county`
  shows requests and logs; **Containers** shows when it's awake.
- **Take it down:** `npx wrangler delete` in `deploy/cloudflare` removes the
  Worker; delete the container image under **Containers** in the dashboard.
- **A different address:** change `SITE_URL` and the `routes` pattern in
  `deploy/cloudflare/wrangler.jsonc`, then redeploy.
- **A smaller, cheaper size:** change `INSTANCE_TYPE` to `basic` in the same
  file and redeploy. If pages get slow or the site restarts under load, change
  it back.

## Other ways to host it

- **Render** (`render.yaml` in the project): fully managed, always on, with a
  separate managed database; about $46 a month in October 2026. Suits a real
  government's installation more than a demo.
- **Any Ubuntu server** with the regular [installer](install.md), then
  `sudo countyctl app demo --scale 200000`.

## Using these pieces for a real government

The Cloudflare setup above is for demonstrations only: its database lives
inside the container and is thrown away when the container sleeps. A real
installation needs a permanent database and storage: use the
[installer](install.md) on a server, or Render with a disk added (see the
comment in `render.yaml`), and follow the [administrator guide](README.md).
