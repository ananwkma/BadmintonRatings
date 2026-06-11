CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE COLLATE NOCASE,
  display_name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  singles_rating REAL NOT NULL DEFAULT 1500,
  doubles_rating REAL NOT NULL DEFAULT 1500,
  singles_wins INTEGER NOT NULL DEFAULT 0,
  singles_losses INTEGER NOT NULL DEFAULT 0,
  doubles_wins INTEGER NOT NULL DEFAULT 0,
  doubles_losses INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE matches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_type TEXT NOT NULL CHECK (match_type IN ('singles', 'doubles')),
  played_at TEXT NOT NULL,
  scores TEXT NOT NULL,
  winner_side TEXT NOT NULL CHECK (winner_side IN ('A', 'B')),
  created_by INTEGER NOT NULL REFERENCES users (id),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT
);

CREATE TABLE match_players (
  match_id INTEGER NOT NULL REFERENCES matches (id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users (id),
  side TEXT NOT NULL CHECK (side IN ('A', 'B')),
  position INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (match_id, user_id)
);

CREATE TABLE rating_changes (
  match_id INTEGER NOT NULL REFERENCES matches (id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users (id),
  rating_before REAL NOT NULL,
  rating_after REAL NOT NULL,
  PRIMARY KEY (match_id, user_id)
);

CREATE INDEX idx_matches_order ON matches (played_at, id);
CREATE INDEX idx_match_players_user ON match_players (user_id);
