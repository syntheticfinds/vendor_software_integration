"""
Seed realistic onboarding signal events for Polaris / Snowflake Computing.

Simulates ~6 weeks of onboarding activity including:
- Vendor email threads with initial ambiguity and follow-ups
- Jira tickets for onboarding tasks with progress and issues
- Gradual resolution of early problems
- A mix of positive, negative, and neutral signals
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.database import engine

COMPANY_ID = "b6234cefbe1a4838bdbffcba977fb00f"
SOFTWARE_ID = "9c5a81d0141a4733ad6c8b8a7f586c55"

# Base date: software was registered 2026-02-14, so events start a few days before
# (initial vendor outreach) and progress through onboarding
BASE = datetime(2026, 1, 5, tzinfo=timezone.utc)


def _id():
    return uuid.uuid4().hex


def dt(day_offset: float, hour: int = 10):
    """Helper: BASE + day_offset days, at given hour."""
    return BASE + timedelta(days=day_offset, hours=hour - 10)


EVENTS = [
    # ─────────────────────────────────────────────────────────
    # WEEK 1: Initial vendor outreach & account setup
    # ─────────────────────────────────────────────────────────

    # Day 0 — First vendor email (ambiguous pricing)
    {
        "source_type": "email",
        "event_type": "vendor_email",
        "severity": "low",
        "title": "Re: Snowflake Enterprise Trial — Pricing & Editions",
        "body": (
            "Hi Maya,\n\n"
            "Thanks for your interest in Snowflake. We offer several editions "
            "(Standard, Enterprise, Business Critical) but the right choice depends "
            "on your workload profile. Could you share more about your expected "
            "data volumes and concurrent user count? We'd also need to understand "
            "your compliance requirements before recommending an edition.\n\n"
            "Happy to schedule a call to walk through options.\n\n"
            "Best,\nJordan Park — Snowflake Account Executive"
        ),
        "occurred_at": dt(0, 9),
    },

    # Day 1 — Polaris replies with details
    {
        "source_type": "email",
        "event_type": "vendor_email",
        "severity": "low",
        "title": "Re: Snowflake Enterprise Trial — Pricing & Editions",
        "body": (
            "Hi Jordan,\n\n"
            "We're looking at roughly 2-5 TB of daily ingestion from our product "
            "analytics pipeline. About 40 analysts will query the warehouse, with "
            "peak usage during Monday morning reporting. We're SOC 2 Type II "
            "compliant and need the same from our vendors.\n\n"
            "Can you confirm whether Enterprise edition covers this, or do we need "
            "Business Critical? Also unclear from your docs whether we need to pay "
            "separately for the Snowpipe streaming feature.\n\n"
            "Thanks,\nMaya Chen — Head of Data, Polaris"
        ),
        "occurred_at": dt(1, 11),
    },

    # Day 3 — Vendor clarifies, sends trial info
    {
        "source_type": "email",
        "event_type": "vendor_email",
        "severity": "low",
        "title": "Re: Snowflake Enterprise Trial — Pricing & Editions",
        "body": (
            "Hi Maya,\n\n"
            "Enterprise edition is the right fit. It includes SOC 2 compliance, "
            "multi-cluster warehouses for your Monday peak, and Snowpipe is included "
            "at no extra licensing cost (you pay for compute credits used during "
            "streaming). I've provisioned a 30-day Enterprise trial in AWS us-east-1. "
            "Your org admin account details are below.\n\n"
            "Org URL: https://polaris-trial.snowflakecomputing.com\n"
            "Admin: maya.chen@polaris.io\n"
            "Temp password sent separately via secure link.\n\n"
            "I'd recommend starting with a single XS warehouse and scaling from there.\n\n"
            "Best,\nJordan"
        ),
        "occurred_at": dt(3, 14),
    },

    # Day 3 — Jira: Set up Snowflake trial account
    {
        "source_type": "jira",
        "event_type": "ticket_created",
        "severity": "medium",
        "title": "[DATA-101] Set up Snowflake trial account and configure SSO",
        "body": (
            "Description: Received Enterprise trial credentials from Snowflake rep. "
            "Need to:\n"
            "1. Log in and change admin password\n"
            "2. Configure Okta SSO integration\n"
            "3. Set up initial warehouse (XS) for data team\n"
            "4. Create roles: ANALYST, ENGINEER, ADMIN\n\n"
            "Assignee: Derek Tan\n"
            "Priority: High\n"
            "Sprint: Data Platform Sprint 12"
        ),
        "occurred_at": dt(3, 16),
    },

    # Day 4 — Jira: SSO config issue
    {
        "source_type": "jira",
        "event_type": "ticket_created",
        "severity": "high",
        "title": "[DATA-102] SSO integration failing — SAML assertion error",
        "body": (
            "Trying to configure Okta SSO with Snowflake per their docs but getting "
            "'Invalid SAML assertion: audience mismatch' error. Our Okta app is "
            "configured with the org URL as audience but Snowflake seems to expect "
            "a different format.\n\n"
            "Blocked on this — can't onboard the rest of the team until SSO works.\n\n"
            "Assignee: Derek Tan\n"
            "Priority: High"
        ),
        "occurred_at": dt(4, 10),
    },

    # Day 4 — Jira: Comment on SSO issue
    {
        "source_type": "jira",
        "event_type": "comment_added",
        "severity": "high",
        "title": "[DATA-102] SSO integration failing — SAML assertion error",
        "body": (
            "Derek Tan: Contacted Snowflake support. They said the audience URI must "
            "be in the format 'https://<account>.snowflakecomputing.com' NOT the org "
            "URL. Our org URL uses a different format (polaris-trial). Trying the fix now."
        ),
        "occurred_at": dt(4, 15),
    },

    # Day 5 — Jira: SSO resolved
    {
        "source_type": "jira",
        "event_type": "ticket_resolved",
        "severity": "high",
        "title": "[DATA-102] SSO integration failing — SAML assertion error",
        "body": (
            "Derek Tan: Fixed. The audience URI needed to be the account locator URL, "
            "not the org URL. Updated Okta config and SSO is working. All team members "
            "can now log in via Okta. Snowflake docs were ambiguous about this — filed "
            "feedback with their support team."
        ),
        "occurred_at": dt(5, 11),
    },

    # Day 5 — Jira: Setup ticket updated with progress
    {
        "source_type": "jira",
        "event_type": "ticket_updated",
        "severity": "medium",
        "title": "[DATA-101] Set up Snowflake trial account and configure SSO",
        "body": (
            "Derek Tan: Updated status — SSO is now working (see DATA-102). Roles "
            "created: ANALYST, ENGINEER, ADMIN. XS warehouse 'ANALYTICS_WH' is live. "
            "Remaining: need to set up network policies and IP whitelisting per "
            "security team requirements."
        ),
        "occurred_at": dt(5, 14),
    },

    # ─────────────────────────────────────────────────────────
    # WEEK 2: Data loading & initial pipeline setup
    # ─────────────────────────────────────────────────────────

    # Day 7 — Jira: Data loading task
    {
        "source_type": "jira",
        "event_type": "ticket_created",
        "severity": "medium",
        "title": "[DATA-103] Configure Snowpipe for real-time product analytics ingestion",
        "body": (
            "Description: Set up Snowpipe to stream product analytics events from "
            "our S3 bucket into Snowflake. Expected volume: ~2TB/day of JSON events.\n\n"
            "Steps:\n"
            "1. Create stage pointing to s3://polaris-analytics-prod/events/\n"
            "2. Define file format (JSON, strip outer array)\n"
            "3. Create target table with VARIANT column\n"
            "4. Configure Snowpipe with SQS notification\n"
            "5. Test with sample data\n\n"
            "Assignee: Priya Sharma\n"
            "Priority: High"
        ),
        "occurred_at": dt(7, 10),
    },

    # Day 8 — Jira: Snowpipe issue
    {
        "source_type": "jira",
        "event_type": "comment_added",
        "severity": "high",
        "title": "[DATA-103] Configure Snowpipe for real-time product analytics ingestion",
        "body": (
            "Priya Sharma: Snowpipe is set up and receiving notifications, but files "
            "aren't loading. Getting error: 'Insufficient privileges to operate on "
            "schema ANALYTICS'. The SYSADMIN role doesn't have the right grants. "
            "Need to figure out the correct privilege chain — their RBAC model is "
            "more complex than expected."
        ),
        "occurred_at": dt(8, 11),
    },

    # Day 9 — Jira: Snowpipe fixed
    {
        "source_type": "jira",
        "event_type": "comment_added",
        "severity": "medium",
        "title": "[DATA-103] Configure Snowpipe for real-time product analytics ingestion",
        "body": (
            "Priya Sharma: Resolved the permissions issue. Needed to GRANT USAGE ON "
            "DATABASE and SCHEMA separately, plus CREATE PIPE privilege. Snowpipe is "
            "now ingesting successfully — verified with 500MB test batch. Latency is "
            "about 2-3 minutes from S3 drop to queryable, which is acceptable."
        ),
        "occurred_at": dt(9, 10),
    },

    # Day 10 — Vendor email: onboarding check-in
    {
        "source_type": "email",
        "event_type": "vendor_email",
        "severity": "low",
        "title": "Snowflake Onboarding Check-in — Week 1 Recap",
        "body": (
            "Hi Maya,\n\n"
            "Wanted to check in on your first week with the trial. I see your org "
            "has 12 active users and a warehouse running. A few things to consider "
            "as you ramp up:\n\n"
            "- Auto-suspend your warehouse after 5 min of inactivity to save credits\n"
            "- Consider using TRANSIENT tables for staging data (saves storage costs)\n"
            "- Our Snowflake University has free on-demand courses for your analysts\n\n"
            "Any blockers or questions? Happy to loop in our Solutions Architect if "
            "you need help with data modeling.\n\n"
            "Best,\nJordan"
        ),
        "occurred_at": dt(10, 9),
    },

    # Day 10 — Polaris reply mentioning SSO confusion
    {
        "source_type": "email",
        "event_type": "vendor_email",
        "severity": "low",
        "title": "Re: Snowflake Onboarding Check-in — Week 1 Recap",
        "body": (
            "Hi Jordan,\n\n"
            "Things are going reasonably well. We did hit a snag with SSO setup — "
            "your docs aren't clear about the difference between org URL and account "
            "locator URL for SAML configuration. Cost us about a day. Would be great "
            "if that could be clarified in the docs.\n\n"
            "We're now loading data via Snowpipe and it's working. Two questions:\n"
            "1. Is there a way to monitor Snowpipe lag in real-time?\n"
            "2. Our Monday morning query spike is already noticeable — should we "
            "pre-warm the warehouse or use multi-cluster?\n\n"
            "Thanks,\nMaya"
        ),
        "occurred_at": dt(10, 14),
    },

    # Day 11 — Jira: Snowpipe loading complete
    {
        "source_type": "jira",
        "event_type": "ticket_resolved",
        "severity": "medium",
        "title": "[DATA-103] Configure Snowpipe for real-time product analytics ingestion",
        "body": (
            "Priya Sharma: Snowpipe pipeline fully operational. Running for 48 hours "
            "with no failures. Auto-ingest latency averages 90 seconds. Ingesting "
            "~1.8TB/day currently. Created monitoring dashboard in Snowsight to track "
            "pipe status and credit consumption."
        ),
        "occurred_at": dt(11, 16),
    },

    # Day 12 — Jira: Account setup completed
    {
        "source_type": "jira",
        "event_type": "ticket_resolved",
        "severity": "medium",
        "title": "[DATA-101] Set up Snowflake trial account and configure SSO",
        "body": (
            "Derek Tan: All items complete:\n"
            "- SSO working via Okta ✓\n"
            "- Roles created and assigned ✓\n"
            "- XS warehouse configured with 5-min auto-suspend ✓\n"
            "- Network policy with IP whitelist applied ✓\n"
            "- 18 team members onboarded ✓\n\n"
            "Closing ticket."
        ),
        "occurred_at": dt(12, 10),
    },

    # ─────────────────────────────────────────────────────────
    # WEEK 3: Query performance issues & integration work
    # ─────────────────────────────────────────────────────────

    # Day 14 — Jira: Slow queries
    {
        "source_type": "jira",
        "event_type": "ticket_created",
        "severity": "high",
        "title": "[DATA-104] Analyst queries timing out on large event tables",
        "body": (
            "Multiple analysts reporting that queries on the raw_events table are "
            "taking 10+ minutes or timing out entirely. Table has ~400M rows and "
            "no clustering keys defined. Typical query pattern is filtering by "
            "event_date and user_id.\n\n"
            "This is blocking the Monday reporting workflow — analysts can't generate "
            "weekly product metrics on time.\n\n"
            "Assignee: Priya Sharma\n"
            "Priority: Critical"
        ),
        "occurred_at": dt(14, 9),
    },

    # Day 14 — Jira: Comment — investigating
    {
        "source_type": "jira",
        "event_type": "comment_added",
        "severity": "high",
        "title": "[DATA-104] Analyst queries timing out on large event tables",
        "body": (
            "Priya Sharma: Looking at query history — the problem is full table scans. "
            "Without clustering keys, Snowflake has to scan all micro-partitions. "
            "Going to add clustering on (event_date, user_id) and scale up the "
            "warehouse temporarily to MEDIUM while the reclustering runs."
        ),
        "occurred_at": dt(14, 11),
    },

    # Day 15 — Jira: Performance fix
    {
        "source_type": "jira",
        "event_type": "comment_added",
        "severity": "high",
        "title": "[DATA-104] Analyst queries timing out on large event tables",
        "body": (
            "Priya Sharma: Added clustering keys (event_date, user_id) to raw_events. "
            "Reclustering completed after ~4 hours on MEDIUM warehouse. Test queries "
            "now complete in 8-15 seconds instead of 10+ minutes. Scaled warehouse "
            "back to SMALL. Monitoring credit usage impact."
        ),
        "occurred_at": dt(15, 14),
    },

    # Day 16 — Jira: Performance issue resolved
    {
        "source_type": "jira",
        "event_type": "ticket_resolved",
        "severity": "high",
        "title": "[DATA-104] Analyst queries timing out on large event tables",
        "body": (
            "Priya Sharma: Confirmed — all analyst queries running under 30 seconds. "
            "Set up automatic reclustering and will monitor costs. Added a runbook "
            "for future tables: always define clustering keys for tables >100M rows."
        ),
        "occurred_at": dt(16, 10),
    },

    # Day 16 — Jira: dbt integration task
    {
        "source_type": "jira",
        "event_type": "ticket_created",
        "severity": "medium",
        "title": "[DATA-105] Set up dbt project for Snowflake transformations",
        "body": (
            "Description: Configure dbt Cloud to connect to Snowflake for our ELT "
            "pipeline. Need to:\n"
            "1. Create service account with appropriate roles\n"
            "2. Set up dbt Cloud project with Snowflake connection\n"
            "3. Migrate existing 12 dbt models from Redshift syntax to Snowflake\n"
            "4. Test incremental models with Snowflake's MERGE syntax\n\n"
            "Assignee: Ravi Patel\n"
            "Priority: Medium"
        ),
        "occurred_at": dt(16, 14),
    },

    # Day 18 — Jira: dbt migration issues
    {
        "source_type": "jira",
        "event_type": "comment_added",
        "severity": "medium",
        "title": "[DATA-105] Set up dbt project for Snowflake transformations",
        "body": (
            "Ravi Patel: Hit a few SQL syntax differences between Redshift and "
            "Snowflake. Main issues:\n"
            "- GETDATE() → CURRENT_TIMESTAMP()\n"
            "- DISTKEY/SORTKEY don't exist in Snowflake (use clustering instead)\n"
            "- LISTAGG syntax slightly different\n"
            "- UNLOAD command replaced with COPY INTO\n\n"
            "Migrated 8/12 models so far. The remaining 4 use Redshift-specific UDFs "
            "that need rewriting."
        ),
        "occurred_at": dt(18, 15),
    },

    # ─────────────────────────────────────────────────────────
    # WEEK 4: Feature requests & stabilization
    # ─────────────────────────────────────────────────────────

    # Day 21 — Email: Feature request about data sharing
    {
        "source_type": "email",
        "event_type": "feature_request",
        "severity": "medium",
        "title": "Question about Snowflake Secure Data Sharing with partners",
        "body": (
            "Hi Jordan,\n\n"
            "Our product team wants to share aggregated analytics with 3 enterprise "
            "customers via Snowflake's Secure Data Sharing feature. We looked at the "
            "docs but have some concerns:\n\n"
            "1. Can we restrict sharing to specific views only (not underlying tables)?\n"
            "2. Is there row-level security for shared data?\n"
            "3. Do our customers need their own Snowflake account or can they use "
            "a Reader account?\n\n"
            "This is a major selling point for us — it could replace the custom "
            "dashboards we're building today.\n\n"
            "Thanks,\nMaya"
        ),
        "occurred_at": dt(21, 10),
    },

    # Day 22 — Vendor reply on data sharing
    {
        "source_type": "email",
        "event_type": "vendor_email",
        "severity": "low",
        "title": "Re: Question about Snowflake Secure Data Sharing with partners",
        "body": (
            "Hi Maya,\n\n"
            "Great use case! To answer your questions:\n\n"
            "1. Yes — you share specific views, so underlying tables are never exposed\n"
            "2. You can use Secure Views + row-level policies to restrict data per customer\n"
            "3. Reader Accounts are available but limited. For enterprise customers, "
            "we'd recommend they get their own account for better governance\n\n"
            "I'd like to bring in Sarah Lin, our Solutions Architect, to do a design "
            "session on your data sharing architecture. Would next Thursday work?\n\n"
            "Best,\nJordan"
        ),
        "occurred_at": dt(22, 11),
    },

    # Day 22 — Jira: dbt migration complete
    {
        "source_type": "jira",
        "event_type": "ticket_resolved",
        "severity": "medium",
        "title": "[DATA-105] Set up dbt project for Snowflake transformations",
        "body": (
            "Ravi Patel: All 12 models migrated and passing tests in dbt Cloud. "
            "Incremental models using MERGE work correctly. Scheduled daily runs "
            "at 6 AM UTC. Closing ticket.\n\n"
            "Note: Performance is actually better than Redshift — our full dbt run "
            "went from 45 min to 12 min on Snowflake."
        ),
        "occurred_at": dt(22, 16),
    },

    # Day 24 — Jira: Intermittent warehouse suspension issue
    {
        "source_type": "jira",
        "event_type": "ticket_created",
        "severity": "medium",
        "title": "[DATA-106] Warehouse auto-suspends during long-running reports",
        "body": (
            "Analysts report that their multi-step reporting notebooks disconnect "
            "midway because the warehouse auto-suspends between query executions. "
            "The 5-minute auto-suspend is too aggressive for interactive work.\n\n"
            "Need to either increase suspend time or create a separate warehouse for "
            "interactive/notebook use.\n\n"
            "Assignee: Derek Tan\n"
            "Priority: Medium"
        ),
        "occurred_at": dt(24, 9),
    },

    # Day 25 — Jira: Warehouse issue resolved
    {
        "source_type": "jira",
        "event_type": "ticket_resolved",
        "severity": "medium",
        "title": "[DATA-106] Warehouse auto-suspends during long-running reports",
        "body": (
            "Derek Tan: Created a second warehouse 'INTERACTIVE_WH' (SMALL, 15-min "
            "auto-suspend) for analyst notebook sessions. Left ANALYTICS_WH at 5-min "
            "suspend for scheduled batch jobs. Updated team wiki with guidance on "
            "which warehouse to use when."
        ),
        "occurred_at": dt(25, 14),
    },

    # ─────────────────────────────────────────────────────────
    # WEEK 5: Rate limits & cost concerns
    # ─────────────────────────────────────────────────────────

    # Day 28 — Jira: Credit usage spike
    {
        "source_type": "jira",
        "event_type": "ticket_created",
        "severity": "high",
        "title": "[DATA-107] Snowflake credit consumption 3x higher than projected",
        "body": (
            "Finance flagged that our trial credit burn rate is tracking to exhaust "
            "all trial credits 2 weeks early. Main culprits:\n"
            "- Reclustering jobs consuming ~40% of credits\n"
            "- Two analysts running expensive ad-hoc queries without warehouse size "
            "limits\n"
            "- Snowpipe compute credits higher than expected at our volume\n\n"
            "Need to implement cost controls immediately.\n\n"
            "Assignee: Maya Chen\n"
            "Priority: High"
        ),
        "occurred_at": dt(28, 10),
    },

    # Day 28 — Email: Asking vendor about cost optimization
    {
        "source_type": "email",
        "event_type": "vendor_email",
        "severity": "medium",
        "title": "Snowflake Credit Usage — Need Cost Optimization Guidance",
        "body": (
            "Hi Jordan,\n\n"
            "Our trial credit burn rate is much higher than we expected. We're on "
            "track to run out 2 weeks early. A few questions:\n\n"
            "1. Can we set per-user or per-warehouse credit limits?\n"
            "2. Is there a way to limit max warehouse size for specific roles?\n"
            "3. Any best practices for reducing Snowpipe costs at 2TB/day volume?\n\n"
            "This is a concern for our procurement team — we need to understand "
            "steady-state costs before committing to a contract.\n\n"
            "Thanks,\nMaya"
        ),
        "occurred_at": dt(28, 14),
    },

    # Day 30 — Vendor reply with cost guidance
    {
        "source_type": "email",
        "event_type": "vendor_email",
        "severity": "low",
        "title": "Re: Snowflake Credit Usage — Need Cost Optimization Guidance",
        "body": (
            "Hi Maya,\n\n"
            "Totally normal to see higher usage during onboarding — reclustering is "
            "a one-time cost that drops off. Here's what I recommend:\n\n"
            "1. Resource Monitors: You can set credit quotas per warehouse with "
            "actions (notify, suspend) when thresholds are hit\n"
            "2. Use 'STATEMENT_QUEUED_TIMEOUT_IN_SECONDS' and 'STATEMENT_TIMEOUT_IN_SECONDS' "
            "to kill runaway queries\n"
            "3. For Snowpipe: batch files into larger chunks (aim for 100-250MB files "
            "instead of many small ones) — reduces per-file overhead\n\n"
            "I've also added 5,000 bonus trial credits to your account to account for "
            "the onboarding ramp. Let me know if you'd like to discuss steady-state "
            "pricing — happy to model it out.\n\n"
            "Best,\nJordan"
        ),
        "occurred_at": dt(30, 10),
    },

    # Day 30 — Jira: Cost controls implemented
    {
        "source_type": "jira",
        "event_type": "comment_added",
        "severity": "high",
        "title": "[DATA-107] Snowflake credit consumption 3x higher than projected",
        "body": (
            "Maya Chen: Implemented Resource Monitors on all warehouses:\n"
            "- ANALYTICS_WH: 500 credits/month, suspend at 90%\n"
            "- INTERACTIVE_WH: 300 credits/month, notify at 75%, suspend at 100%\n"
            "- Set query timeout to 15 minutes for ANALYST role\n"
            "- Optimized S3 file batching — reduced Snowpipe overhead by ~30%\n\n"
            "Vendor also added 5K bonus credits. Monitoring burn rate this week."
        ),
        "occurred_at": dt(30, 16),
    },

    # Day 33 — Jira: Cost issue resolved
    {
        "source_type": "jira",
        "event_type": "ticket_resolved",
        "severity": "high",
        "title": "[DATA-107] Snowflake credit consumption 3x higher than projected",
        "body": (
            "Maya Chen: After implementing resource monitors and file batching "
            "optimizations, daily credit usage dropped from ~85 to ~35 credits. "
            "Projected monthly cost is now within budget. Reclustering has also "
            "completed so that one-time cost is behind us. Closing."
        ),
        "occurred_at": dt(33, 11),
    },

    # ─────────────────────────────────────────────────────────
    # WEEK 6: Stabilization & going productive
    # ─────────────────────────────────────────────────────────

    # Day 35 — Jira: Data quality validation
    {
        "source_type": "jira",
        "event_type": "ticket_created",
        "severity": "medium",
        "title": "[DATA-108] Validate data accuracy: Snowflake vs legacy Redshift",
        "body": (
            "Before we cut over from Redshift, need to validate that Snowflake "
            "data matches. Run parallel queries on both systems for key metrics:\n"
            "- Daily active users\n"
            "- Revenue aggregations\n"
            "- Funnel conversion rates\n\n"
            "Any discrepancies >0.1% need investigation.\n\n"
            "Assignee: Ravi Patel\n"
            "Priority: High"
        ),
        "occurred_at": dt(35, 10),
    },

    # Day 36 — Jira: Minor discrepancy found
    {
        "source_type": "jira",
        "event_type": "comment_added",
        "severity": "medium",
        "title": "[DATA-108] Validate data accuracy: Snowflake vs legacy Redshift",
        "body": (
            "Ravi Patel: Found a 0.3% discrepancy in revenue aggregations. Root cause: "
            "Snowflake handles FLOAT precision differently than Redshift. Changed our "
            "revenue columns to NUMBER(38,2) in Snowflake and the numbers now match "
            "exactly. DAU and funnel metrics match within 0.01%."
        ),
        "occurred_at": dt(36, 15),
    },

    # Day 38 — Jira: Validation complete
    {
        "source_type": "jira",
        "event_type": "ticket_resolved",
        "severity": "medium",
        "title": "[DATA-108] Validate data accuracy: Snowflake vs legacy Redshift",
        "body": (
            "Ravi Patel: All 15 key metrics validated. Snowflake and Redshift numbers "
            "match within acceptable tolerance. Green light for cutover. "
            "Recommending we decommission Redshift by end of month."
        ),
        "occurred_at": dt(38, 10),
    },

    # Day 38 — Email: Positive vendor interaction — contract discussion
    {
        "source_type": "email",
        "event_type": "vendor_email",
        "severity": "low",
        "title": "Re: Snowflake Contract Proposal — Enterprise Annual",
        "body": (
            "Hi Maya,\n\n"
            "Thanks for the positive feedback on the trial. Based on your usage "
            "patterns, I'm proposing an Enterprise annual contract at $36/credit "
            "(12% discount from on-demand) with a 120,000 credit annual commitment. "
            "This includes:\n\n"
            "- Priority support (4-hour response SLA)\n"
            "- Dedicated Solutions Architect for first 90 days\n"
            "- Unused credits roll over for 1 year\n\n"
            "Let me know if you'd like to discuss or adjust the commitment level.\n\n"
            "Best,\nJordan"
        ),
        "occurred_at": dt(38, 14),
    },

    # Day 40 — Email: Feature request — Snowpark
    {
        "source_type": "email",
        "event_type": "feature_request",
        "severity": "low",
        "title": "Snowpark for Python — ML pipeline feasibility",
        "body": (
            "Hi Jordan,\n\n"
            "Our ML team is interested in Snowpark for Python to run model training "
            "directly in Snowflake. A few questions:\n\n"
            "1. Is Snowpark included in Enterprise or does it require Business Critical?\n"
            "2. Can we use custom Python packages (scikit-learn, xgboost) in UDFs?\n"
            "3. What's the max memory available for a Snowpark session?\n\n"
            "If this works, we could eliminate our separate ML infrastructure entirely.\n\n"
            "Thanks,\nMaya"
        ),
        "occurred_at": dt(40, 11),
    },

    # Day 42 — Jira: Production cutover
    {
        "source_type": "jira",
        "event_type": "ticket_created",
        "severity": "critical",
        "title": "[DATA-109] Production cutover: Migrate all dashboards from Redshift to Snowflake",
        "body": (
            "All validations passed. Proceeding with production cutover:\n\n"
            "1. Update Looker connection to point to Snowflake\n"
            "2. Redirect all scheduled reports to Snowflake warehouse\n"
            "3. Switch dbt production environment to Snowflake\n"
            "4. Verify all 23 Looker dashboards render correctly\n"
            "5. Keep Redshift running in read-only for 2-week fallback period\n\n"
            "Cutover window: Saturday 2 AM - 6 AM UTC\n\n"
            "Assignee: Priya Sharma\n"
            "Priority: Critical"
        ),
        "occurred_at": dt(42, 10),
    },

    # Day 44 (Saturday) — Jira: Cutover completed
    {
        "source_type": "jira",
        "event_type": "ticket_resolved",
        "severity": "critical",
        "title": "[DATA-109] Production cutover: Migrate all dashboards from Redshift to Snowflake",
        "body": (
            "Priya Sharma: Cutover completed successfully.\n\n"
            "- Looker connected to Snowflake ✓\n"
            "- All 23 dashboards rendering correctly ✓\n"
            "- dbt production jobs running on Snowflake ✓\n"
            "- Scheduled reports verified ✓\n"
            "- Redshift kept in read-only mode as fallback ✓\n\n"
            "Total downtime: 47 minutes (within 4-hour window). No data loss. "
            "Snowflake is now our primary data warehouse."
        ),
        "occurred_at": dt(44, 6),
    },
]


async def seed():
    async with engine.begin() as conn:
        for ev in EVENTS:
            eid = _id()
            await conn.execute(
                text("""
                    INSERT INTO signal_events
                        (id, company_id, software_id, source_type, source_id,
                         event_type, severity, title, body, event_metadata, occurred_at)
                    VALUES
                        (:id, :cid, :sid, :source_type, :source_id,
                         :event_type, :severity, :title, :body, :meta, :occurred_at)
                """),
                {
                    "id": eid,
                    "cid": COMPANY_ID,
                    "sid": SOFTWARE_ID,
                    "source_type": ev["source_type"],
                    "source_id": f"seed-{eid[:12]}",
                    "event_type": ev["event_type"],
                    "severity": ev["severity"],
                    "title": ev["title"],
                    "body": ev["body"],
                    "meta": "{}",
                    "occurred_at": ev["occurred_at"],
                },
            )
        print(f"Inserted {len(EVENTS)} signal events for Polaris / Snowflake Computing")


if __name__ == "__main__":
    asyncio.run(seed())
