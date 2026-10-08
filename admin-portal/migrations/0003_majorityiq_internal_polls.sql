-- Private internal horse-race polls (aggregate toplines only; session-authenticated intake).
CREATE TABLE IF NOT EXISTS majorityiq_internal_polls (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  district_id TEXT NOT NULL CHECK (district_id IN ('ad-7', 'ad-27', 'ad-36', 'ad-47', 'ad-58', 'ad-74')),
  pollster TEXT NOT NULL,
  sponsor TEXT,
  sponsor_type TEXT NOT NULL CHECK (sponsor_type IN ('independent', 'campaign', 'party', 'ie')),
  sponsor_party TEXT CHECK (sponsor_party IN ('R', 'D') OR sponsor_party IS NULL),
  field_start TEXT NOT NULL,
  field_end TEXT NOT NULL,
  sample_n INTEGER,
  population TEXT,
  mode TEXT,
  moe_pct REAL,
  toplines_json TEXT NOT NULL,
  undecided_pct REAL,
  crosstabs_json TEXT,
  source_label TEXT,
  source_url TEXT,
  notes TEXT,
  visibility TEXT NOT NULL DEFAULT 'private' CHECK (visibility = 'private'),
  verified_by TEXT,
  created_by_admin_id INTEGER,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS majorityiq_internal_polls_district_idx
  ON majorityiq_internal_polls (district_id, field_end DESC);
