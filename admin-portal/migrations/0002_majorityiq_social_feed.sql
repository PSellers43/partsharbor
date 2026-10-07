-- Latest MajorityIQ X digest (single row; operator refresh via scripts/push-social-feed.sh)
CREATE TABLE IF NOT EXISTS majorityiq_social_feed (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  as_of TEXT NOT NULL,
  payload TEXT NOT NULL,
  updated_at INTEGER NOT NULL,
  byte_size INTEGER NOT NULL
);
