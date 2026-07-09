# YouTube API Compliance

## API Services Policies

This lab follows YouTube API Services Policies:
- Access and use YouTube API Services in compliance with applicable terms
- Do not access or use YouTube API Services in ways that violate YouTube's terms
- Respect quota allocations and audit requirements

## Quota Management

- Default daily quota: 10,000 units
- Each API call has a quota cost (e.g., videos.insert = 1600 units)
- Lab tracks quota cost in receipts
- Lab handles quota exceeded errors gracefully
- Lab does not attempt to bypass quota limits

## OAuth Scopes

### Read-only analytics
- `https://www.googleapis.com/auth/yt-analytics.readonly`

### Channel management
- `https://www.googleapis.com/auth/youtube.readonly` (for ingestion)
- `https://www.googleapis.com/auth/youtube.upload` (for upload, separate credential)

### Separation of concerns
- Analytics credentials: read-only, no upload capability
- Upload credentials: separate OAuth flow, requires explicit user action
- Upload credentials stored separately from analytics credentials

## Upload Safety

- Default privacy: private
- No public upload without explicit human confirmation
- No automated publishing
- Upload receipt includes: video ID, timestamp, privacy status, quota cost

## Data Retention

- Raw API responses: stored locally, not re-uploaded
- Analytics snapshots: stored in SQLite, timestamped
- Receipts: append-only JSONL, immutable
- Transcripts: stored locally with source attribution
