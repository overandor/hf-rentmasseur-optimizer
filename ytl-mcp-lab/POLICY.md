# YTL-MCP Research Lab — Policy

## Compliance Boundary

### Allowed
- Automate your production workflow
- Analyze lawfully available data (public metadata, permitted transcripts)
- Upload your own authorized content (private/unlisted by default)
- Optimize metadata and run experiments
- Sync your own channel analytics via OAuth

### Prohibited
- Fake views, likes, subscribers, comments
- Mass commenting, mass liking, mass subscribing
- Credential scraping or sharing
- Captcha bypass
- Account farming
- Copyrighted video downloading for reupload
- Automated harassment or deception
- Hidden engagement manipulation
- Bypassing YouTube API quota or terms

## Tool Capability Tiers

| Tier | Description | Confirmation Required |
|------|-------------|----------------------|
| 0 | Read-only (status, list, receipts) | No |
| 1 | Local generation (scripts, metadata, scores) | No |
| 2 | Local execution (FFmpeg, packaging) | No |
| 3 | Authorized external API (analytics sync) | No (OAuth required) |
| 4 | Publish-affecting (upload, update, publish) | YES — explicit human approval |

## Data Handling

- Public data: may be ingested for research
- Private data: only via OAuth for your own channel
- Credentials: .env only, never committed
- Receipts: append-only, immutable, hashed
- Transcripts: only from permitted sources or local files

## YouTube API Compliance

- Respect default quota allocation
- Follow API Services Policies
- Use OAuth for authorized operations only
- Separate read-only credentials from upload credentials
- Track quota cost in receipts
- Handle quota errors gracefully
