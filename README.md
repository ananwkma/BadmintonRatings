# Badminton Ratings 🏸

A web app for recording badminton matches (singles and doubles) with an
Elo-based rating system, public match feed, player search, leaderboards and
doubles partner analysis.

## Features

- **Accounts** — sign up with a username and password; display names are shown
  on matches and are searchable.
- **Record matches** — singles or doubles, with per-game scores (best of 3).
  The winner is derived from the game scores. You must be one of the players
  to record a match.
- **Ratings** — separate Elo ratings for singles and doubles (start 1500,
  K = 32). Doubles uses the team's average rating; both partners receive the
  full rating change.
- **Editable history** — any participant can edit or delete a match. Ratings
  are always recomputed by replaying every match in chronological order, so
  edits to old matches correctly ripple through everyone's current rating.
- **Public & searchable** — the match feed, player profiles and leaderboards
  are viewable without an account, and players are searchable by name.
- **Leaderboards** — separate singles and doubles rankings.
- **Partner analysis** — each profile breaks down doubles results by partner
  (matches, win %, net rating change together) and highlights your best
  partner (minimum 2 matches together).

## Running locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Then open http://127.0.0.1:5000. The SQLite database is created automatically
in `instance/badminton.sqlite` on first run.

For production, set a real secret key and use a WSGI server:

```bash
SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex())') \
  gunicorn 'app:create_app()'
```

## Tests

```bash
pip install pytest
pytest
```

## How ratings work

Ratings are *derived data*. Every create/edit/delete triggers a full replay of
all matches ordered by date played: everyone starts at 1500 and each match
applies a standard Elo update (`K * (result − expected)`); for doubles the
expected score is computed from the two teams' average ratings. Per-match
rating changes are stored in `rating_changes` and shown on match pages and
profiles.
