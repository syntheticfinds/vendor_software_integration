# Local Testing Guide

## Prerequisites

- Python 3.12+
- Node.js 18+
- Docker (for PostgreSQL) or SQLite (default, no setup needed)
- An Anthropic API key
- Google Cloud OAuth credentials (for Gmail integration)
- ngrok (for Jira webhook testing)

## 1. Install dependencies

```bash
make install
```

Or individually:

```bash
cd backend && pip install -r requirements.txt
cd frontend && npm install
```

## 2. Configure environment

### a. Start ngrok

```bash
ngrok http 8000
```

```bash
cp .env.example backend/.env
```

Edit `backend/.env`:

```
DATABASE_URL=sqlite+aiosqlite:///./vendor_intel.db
JWT_SECRET_KEY=change-me-in-production-use-a-long-random-string
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
ANTHROPIC_API_KEY=<your-anthropic-api-key>
K_ANONYMITY_THRESHOLD=1

# Google OAuth
GOOGLE_CLIENT_ID=<your-google-client-id>
GOOGLE_CLIENT_SECRET=<your-google-client-secret>

# Jira webhook (use the ngrok URL from above)
WEBHOOK_BASE_URL=
```

## 3. Run database migrations

```bash
make migrate
```

## 4. Start the servers

In two separate terminals:

```bash
# Terminal 1 — backend (http://localhost:8000)
make api

# Terminal 2 — frontend (http://localhost:5173)
make ui
```

## 5. Register a company and log in

Open http://localhost:5173 and create an account:

| Field         | Value                        |
|---------------|------------------------------|
| Company name  | Anything you like            |
| Email         | `vendorintel0@gmail.com`     |
| Password      | At least 8 characters        |

After registration you'll be logged in automatically.

## 6. Connect Gmail

1. Go to **Settings** (gear icon in the sidebar).
2. Click **Connect Gmail**.
3. Sign in with the Google account that owns `vendorintel0@gmail.com` (password: vendorintel123) and grant permissions.
4. You should see "Gmail: connected" on the Settings page.

## 7. Register software

Sign up for some vendor software using `vendorintel0@gmail.com`.
After about 1 minute, detected software will appear on the **Monitoring** page.

1. Click the **check icon** on a pending detection to open the inline
   registration form.
2. Fill in the optional fields and click **Confirm & Register**.

Optional fields:

- **Enable Jira integration** — check this to get a webhook URL. If other
  software already has a Jira webhook, you can reuse that URL instead of
  creating a new one (see next step).
- **Support email** — if you set this to a vendor's support address
  (e.g. `support@vendor.com`), inbound/outbound emails matching that address
  will automatically create signals for this software. Multiple software can
  share the same support email — the system will intelligently route each
  email to the correct one.

Registered software appears on the **Software Integrations** page where you can
edit fields, change the Jira webhook URL, or archive it.

## 8. Test Jira webhook integration

### a. Set up the webhook

When registering or editing software, check **Jira integration**. You'll be
given a webhook URL to add to your Jira project.

If you already have a webhook URL for another software, you can **reuse it**
by selecting an existing URL from the dropdown instead of creating a new one.
Multiple software can share the same webhook URL — the backend will
intelligently route each event to the correct software.

You can also change the webhook URL later from the **Software Integrations**
page by clicking **Change URL** on the Jira webhook card.

### b. Trigger an event

Create or update an issue in the Jira project. The webhook fires immediately.

### c. Verify

- **Software Integrations page** — You'll see the number of events and last event received timestamp for each software.
- **Signals page** — a new signal should appear for the matched software.

## 9. Test email-based signal detection

Send an email **from** a vendor support address (the one you registered in step 7)
**to** `vendorintel0@gmail.com`, or send an email **from** `vendorintel0@gmail.com`
**to** that support address.

Within 60 seconds the sync loop will:

1. Fetch the new email.
2. Match it against registered support emails.
3. Create a signal (visible on the Signals page).

## 10. Using the app

### Signals tab

The Signals tab is where you view and manage raw operational signals collected
from your integrations (Jira, email).

- **Select software** from the dropdown to filter signals for a specific product
- **Filter by severity** (Critical, High, Medium, Low) to focus on what matters.

At the top of the page, the **Health Score** card shows the latest score
(0-100) for the selected software, along with a confidence tier (preliminary,
developing, or solid) and a breakdown by category (reliability, support
quality, performance, etc.). Scores are color-coded: green (80+), yellow
(60-79), red (below 60).

### Dashboard tab

The Dashboard gives you a bird's-eye view of your entire software portfolio.

- **Stat cards** at the top show totals: software count, active integrations,
  total signals, average health score, pending reviews, and critical signals.
- **Health Score Trends** — a line chart showing how each software's health
  score has changed over the last 30 days.
- **Signal Severity Distribution** — a pie chart breaking down signals by
  severity.
- **Signals by Source** — a bar chart showing how many signals came from each
  integration (Jira, email).
- **Software Health Table** — lists each registered software with its latest
  score, signal count, and critical signal count.

Click software name chips to filter all charts and tables to specific products.

### Reviews tab

The Reviews tab shows AI-generated review drafts for registered software.

Each review card shows:

- **Status** — pending, edited, approved, declined, or sent.
- **Confidence tier** — how much signal data backs the review (preliminary,
  developing, solid).
- **Draft body** — expand a card to read the full AI-generated review text.

Actions you can take on a review:

- **Edit** — rewrite or tweak the draft text (status changes to "edited").
- **Approve** — mark the draft as ready to send.
- **Decline** — reject the draft if it's not useful.
- **Send Review** — for approved drafts, publishes the review to power the intelligence index.

Use the status filter buttons to focus on pending reviews that need your
attention.

### Intelligence tab

The Intelligence tab provides cross-company aggregated insights about software
products.

**Index view** — shows a grid of software cards, each displaying:

- Software name and vendor.
- Average health score across all companies using it.
- Auto-detected category (e.g. "CI/CD Tools", "Monitoring").
- Number of companies using this software.

Use the search bar to find specific products, or filter by category via the
dropdown.

**Detail view** — click any software card to see:

- Industry and company-size distribution charts showing who uses this product.
- A **Critical User Journey (CUJ)** chart visualizing the typical stages of
  adopting and using the software (setup, configuration, deployment,
  optimization), with average duration and satisfaction rates per stage.
