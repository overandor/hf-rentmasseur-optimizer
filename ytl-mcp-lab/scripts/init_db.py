#!/usr/bin/env python3
"""Initialize the YTL-MCP SQLite database."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "ytl_lab.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
    channel_id TEXT PRIMARY KEY,
    title TEXT,
    owner_status TEXT DEFAULT 'unknown',
    auth_status TEXT DEFAULT 'none',
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    channel_id TEXT,
    title TEXT,
    description_hash TEXT,
    duration INTEGER DEFAULT 0,
    publish_date TEXT,
    privacy_status TEXT DEFAULT 'unknown',
    source TEXT DEFAULT 'manual',
    ingested_at TEXT,
    FOREIGN KEY (channel_id) REFERENCES channels(channel_id)
);

CREATE TABLE IF NOT EXISTS transcripts (
    video_id TEXT PRIMARY KEY,
    transcript_source TEXT,
    language TEXT DEFAULT 'en',
    text_hash TEXT,
    segment_count INTEGER DEFAULT 0,
    word_count INTEGER DEFAULT 0,
    completeness_score REAL DEFAULT 0.0,
    ingested_at TEXT,
    FOREIGN KEY (video_id) REFERENCES videos(video_id)
);

CREATE TABLE IF NOT EXISTS scores (
    video_id TEXT PRIMARY KEY,
    hook_score INTEGER DEFAULT 0,
    retention_score INTEGER DEFAULT 0,
    novelty_score INTEGER DEFAULT 0,
    compression_score INTEGER DEFAULT 0,
    entity_density REAL DEFAULT 0.0,
    payoff_timing INTEGER DEFAULT 0,
    overall REAL DEFAULT 0.0,
    scored_at TEXT,
    FOREIGN KEY (video_id) REFERENCES videos(video_id)
);

CREATE TABLE IF NOT EXISTS scripts (
    script_id TEXT PRIMARY KEY,
    hypothesis TEXT,
    source_hash TEXT,
    version INTEGER DEFAULT 1,
    status TEXT DEFAULT 'draft',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS assets (
    asset_id TEXT PRIMARY KEY,
    asset_type TEXT,
    file_path TEXT,
    file_hash TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS upload_packages (
    package_id TEXT PRIMARY KEY,
    video_path TEXT,
    thumbnail_path TEXT,
    metadata_path TEXT,
    readiness_status TEXT DEFAULT 'pending',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    hypothesis TEXT,
    variant TEXT,
    target_metric TEXT,
    baseline REAL,
    start_date TEXT,
    end_date TEXT,
    measurement_window_days INTEGER DEFAULT 7,
    video_ids TEXT DEFAULT '[]',
    status TEXT DEFAULT 'active',
    result TEXT
);

CREATE TABLE IF NOT EXISTS analytics_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT,
    snapshot_date TEXT,
    views INTEGER DEFAULT 0,
    impressions INTEGER DEFAULT 0,
    ctr REAL DEFAULT 0.0,
    watch_time_seconds INTEGER DEFAULT 0,
    avg_view_duration REAL DEFAULT 0.0,
    subscribers_gained INTEGER DEFAULT 0,
    revenue REAL DEFAULT 0.0,
    FOREIGN KEY (video_id) REFERENCES videos(video_id)
);

CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    event TEXT,
    tool TEXT,
    actor TEXT,
    input_hash TEXT,
    output_hash TEXT,
    status TEXT,
    error TEXT,
    quota_cost INTEGER DEFAULT 0,
    video_id TEXT,
    experiment_id TEXT,
    commit_hash TEXT
);

CREATE INDEX IF NOT EXISTS idx_videos_channel ON videos(channel_id);
CREATE INDEX IF NOT EXISTS idx_scores_video ON scores(video_id);
CREATE INDEX IF NOT EXISTS idx_receipts_timestamp ON receipts(timestamp);
CREATE INDEX IF NOT EXISTS idx_experiments_status ON experiments(status);
"""


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA)
    conn.commit()
    
    # Verify tables
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    print(f"Database initialized at {DB_PATH}")
    print(f"Tables created: {', '.join(t[0] for t in tables)}")
    conn.close()


if __name__ == "__main__":
    main()
