# RentMasseur Visitor Telemetry

This pipeline keeps an evidence-based history of profiles shown on the authenticated **Who Saw Me** page and performs bounded reciprocal visits.

It records first and latest appearance, visible visit time, observed appearance count, platform-reported visit count when available, reciprocal visit count, profile-stated location, New York membership, visible contact and message controls, prior mailbox contact, current online state, last-online hint, inferred session length, and common New York online hours.

It does not store message bodies, phone numbers, email addresses, hidden location, or inferred identity.

`observed_visitor_runs` counts scans where a profile appeared; it is not claimed as the true number of visits. `reported_visit_count` stays empty unless RentMasseur supplies a count. Online duration comes from repeated observations and is not invented when no online signal is exposed.

The scanner stops on CAPTCHA or access challenges and does not bypass them. Messaging is never automatic. `can_message` means a visible message control, an API permission, or an existing mailbox thread was found.

## Local use

Set `RM_TOKEN`, or set `RENTMASSEUR_USERNAME` and `RENTMASSEUR_PASSWORD`.

Run a scan:

```bash
python3 -m rm_traffic.visitor_telemetry scan --area new-york
open output/rm_visitor_dashboard.html
```

Serve the dashboard:

```bash
python3 -m rm_traffic.visitor_telemetry serve --port 8787
```

Dashboard: `http://127.0.0.1:8787`

## Always-on Mac

Create `~/.config/rm-visitor-telemetry.env`, add only the required variables, then:

```bash
chmod 600 ~/.config/rm-visitor-telemetry.env
zsh scripts/install_rm_visitor_telemetry_launchd.sh
```

The collector runs every 15 minutes. Reciprocal browser visits remain limited by the default 24-hour per-profile cooldown.

## GitHub Actions

`.github/workflows/rm-visitor-telemetry.yml` runs every 30 minutes, restores the latest private artifact, updates the SQLite history, and uploads the database, dashboard, and JSON export.

Default database: `data/rm_visitor_telemetry.sqlite3`

Tables: `profiles`, `observations`, `online_sessions`, and `scan_runs`.

Use this only for the authenticated account and information RentMasseur makes visible to that account. Do not use it to harass users, bypass controls, collect hidden personal information, or send unsolicited messages.
