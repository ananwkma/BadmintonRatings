CREATE TABLE settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE players (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE COLLATE NOCASE,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE groups (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  last_season TEXT
);

CREATE TABLE group_players (
  group_id INTEGER NOT NULL REFERENCES groups (id) ON DELETE CASCADE,
  player_id INTEGER NOT NULL REFERENCES players (id) ON DELETE CASCADE,
  singles_rating REAL NOT NULL DEFAULT 1500,
  doubles_rating REAL NOT NULL DEFAULT 1500,
  singles_wins INTEGER NOT NULL DEFAULT 0,
  singles_losses INTEGER NOT NULL DEFAULT 0,
  doubles_wins INTEGER NOT NULL DEFAULT 0,
  doubles_losses INTEGER NOT NULL DEFAULT 0,
  career_singles_wins INTEGER NOT NULL DEFAULT 0,
  career_singles_losses INTEGER NOT NULL DEFAULT 0,
  career_doubles_wins INTEGER NOT NULL DEFAULT 0,
  career_doubles_losses INTEGER NOT NULL DEFAULT 0,
  career_singles_peak REAL NOT NULL DEFAULT 1500,
  career_doubles_peak REAL NOT NULL DEFAULT 1500,
  PRIMARY KEY (group_id, player_id)
);

CREATE TABLE matches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  group_id INTEGER NOT NULL REFERENCES groups (id),
  match_type TEXT NOT NULL CHECK (match_type IN ('singles', 'doubles')),
  played_at TEXT NOT NULL,
  scores TEXT NOT NULL,
  winner_side TEXT NOT NULL CHECK (winner_side IN ('A', 'B')),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT
);

CREATE TABLE match_players (
  match_id INTEGER NOT NULL REFERENCES matches (id) ON DELETE CASCADE,
  player_id INTEGER NOT NULL REFERENCES players (id),
  side TEXT NOT NULL CHECK (side IN ('A', 'B')),
  position INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (match_id, player_id)
);

CREATE TABLE rating_changes (
  match_id INTEGER NOT NULL REFERENCES matches (id) ON DELETE CASCADE,
  player_id INTEGER NOT NULL REFERENCES players (id),
  rating_before REAL NOT NULL,
  rating_after REAL NOT NULL,
  PRIMARY KEY (match_id, player_id)
);

CREATE INDEX idx_matches_order ON matches (played_at, id);
CREATE INDEX idx_matches_group ON matches (group_id);
CREATE INDEX idx_match_players_player ON match_players (player_id);
