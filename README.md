# RateMe

A web app for recording badminton matches (singles and doubles) with an
Elo-based rating system, public match feed, player search, leaderboards and
doubles partner analysis.

## Access model

- **Admin** — a single password, chosen on the first visit to `/admin` and
  stored hashed. Only the admin can add/remove player names, create
  password-locked groups, assign players to groups, reset group passwords
  and delete groups.
- **Groups** — each group has its own password. Anyone who unlocks a group
  on its page can record and edit that group's matches (between the group's
  members), but cannot add or remove names. The admin implicitly has access
  to every group.
- **Everyone else** — the match feed, player profiles, search and the
  leaderboards are fully public, no login needed.

## Features

- **Record matches** — singles or doubles, with per-game scores (best of 3).
  The winner is derived from the game scores. Players are picked from the
  group's member list.
- **Ratings** — separate Elo ratings for singles and doubles (start 1500,
  K = 32). Beating a higher-rated opponent earns more points (standard Elo),
  and the margin of victory scales the change: the winner's average point
  margin per game maps to a multiplier from 0.5× (narrowest wins) to 2×
  (blowouts), with a typical 6-point win at exactly 1×. In doubles each
  player's update is weighted by their own rating against the opposing
  pair's average, so a lower-rated partner gains more from a win than
  their higher-rated teammate.
- **Editable history** — anyone with the group password can edit or delete a
  match. Ratings are always recomputed by replaying every match in
  chronological order, so edits to old matches correctly ripple through
  everyone's current rating.
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

Then open http://127.0.0.1:5000, go to **Admin**, and set the admin password.
The SQLite database is created automatically in `instance/badminton.sqlite`.

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
applies a standard Elo update (`K * (result − expected)`); for doubles each
player's expected score is computed from their own rating against the
opposing pair's average rating. Per-match rating changes are stored in
`rating_changes` and shown on match pages and profiles.
