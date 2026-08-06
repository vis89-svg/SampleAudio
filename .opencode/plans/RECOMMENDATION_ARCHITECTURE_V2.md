# SampleAudio Recommendation System v2 — Frozen Architecture

> **Status: APPROVED — Implementation Ready**
> **Date: 2026-08-06**
> **Version: v2.0 (Final)**

---

## Four-Layer Architecture

```
Layer 1: Raw Events
─────────────────────
Play | Skip | Like | Follow
            │
            ▼
Layer 2: Taste Engine
─────────────────────
Sessions → Transitions → Profiles → Clusters
            │
            ▼
Layer 3: Recommendation Engine
──────────────────────────────
Daily Mix | Discovery | Albums | Because You Liked | New Artists
            │
            ▼
Layer 4: Feedback Loop
──────────────────────
Track recommendation performance → Improve future mixes
```

---

## Database Schema

### New Tables

```sql
CREATE TABLE listening_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    songs_count INTEGER DEFAULT 0,
    fingerprint_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE session_songs (
    session_id INTEGER NOT NULL REFERENCES listening_sessions(id) ON DELETE CASCADE,
    song_id TEXT NOT NULL,
    video_id TEXT NOT NULL,
    artist_id TEXT,
    album_id TEXT,
    play_order INTEGER NOT NULL,
    completed BOOLEAN DEFAULT 0,
    duration_played INTEGER DEFAULT 0,
    PRIMARY KEY (session_id, video_id)
);

CREATE TABLE song_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    from_video_id TEXT NOT NULL,
    to_video_id TEXT NOT NULL,
    from_artist_id TEXT,
    to_artist_id TEXT,
    transition_count INTEGER DEFAULT 1,
    completed_count INTEGER DEFAULT 0,
    skipped_count INTEGER DEFAULT 0,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, from_video_id, to_video_id)
);

CREATE TABLE taste_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    short_term_json TEXT NOT NULL DEFAULT '{}',
    long_term_json TEXT NOT NULL DEFAULT '{}',
    profile_version TEXT DEFAULT 'v2.0',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE recommendation_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mix_type TEXT NOT NULL,
    mix_index INTEGER DEFAULT 0,
    video_id TEXT NOT NULL,
    position INTEGER DEFAULT 0,
    engine_version TEXT DEFAULT 'v2.0',
    shown_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    played BOOLEAN DEFAULT 0,
    completed BOOLEAN DEFAULT 0,
    liked BOOLEAN DEFAULT 0,
    skipped BOOLEAN DEFAULT 0
);
```

### Modified Tables

```sql
ALTER TABLE listening_history ADD COLUMN skipped BOOLEAN DEFAULT 0;
ALTER TABLE listening_history ADD COLUMN skip_position INTEGER DEFAULT 0;
ALTER TABLE listening_history ADD COLUMN session_id INTEGER REFERENCES listening_sessions(id);
ALTER TABLE listening_history ADD COLUMN source TEXT DEFAULT 'search';
```

---

## Key Design Decisions

### Session Fingerprint Shape

```json
{
    "artist_ids": ["UC...", "UC..."],
    "sequence": ["UC...", "UC..."],
    "decades": ["1980s", "2020s"],
    "languages": ["english"],
    "completion_rate": 0.89,
    "skip_rate": 0.07,
    "avg_song_length": 234
}
```

- **No genres** — derivable from artist metadata
- **IDs not names** — names change, IDs don't
- **Sequence capped at 10** — lightweight; detailed history in `session_songs`

### Session Similarity Weights

| Signal | Weight |
|--------|--------|
| Artist overlap | 45% |
| Transition overlap | 30% |
| Era/decade similarity | 15% |
| Time-of-day | 10% |

> Related artists used for **expansion** (after clustering), not cluster formation.

### Taste Profile (Split)

| Profile | Window | Purpose |
|---------|--------|---------|
| `short_term` | Last 7 days | Current mood, recent obsessions |
| `long_term` | Lifetime | Stable identity, persistent taste |

### Effective Song Score

```
score = plays + completed×1.5 + likes×3 + followed_artist×2 + recency_bonus - skip_penalty
```

### Discovery Mix (Confidence-Ordered)

| Source | % |
|--------|---|
| Familiar (top-scored songs) | 40% |
| Similar session songs | 25% |
| Related artists | 20% |
| Taste-trending | 10% |
| Wildcards | 5% |

### Recompute Triggers

| Trigger | Action |
|---------|--------|
| 30 new plays since last recompute | Recluster + regenerate mixes |
| 20% taste profile drift | Short-term diverges from long-term |
| User opens profile & cache >12h stale | Refresh on read |

### Event Bus Architecture

```
Play Logged
      │
      ▼
Publish PlayEvent
      │
 ┌────┼────┬────┬────┐
 ▼    ▼    ▼    ▼    ▼
Session Score Profile Transition Recompute
```

Each module is **idempotent** — only knows "A play happened", nothing about other modules.

---

## Implementation Milestones

| Milestone | Deliverables | Status |
|-----------|--------------|--------|
| 1 | Database + Sessions + Transitions + Fingerprint | 🔲 TODO |
| 2 | Taste Profile + Scoring | 🔲 TODO |
| 3 | Clustering | 🔲 TODO |
| 4 | Daily Mix | 🔲 TODO |
| 5 | Discovery + Albums + Because You Liked | 🔲 TODO |
| 6 | Feedback collection | 🔲 TODO |
| 7 | LLM naming | 🔲 TODO |

---

## File Structure

```
api/
├── taste_engine/
│   ├── __init__.py       # Public API
│   ├── scoring.py        # Effective song score
│   ├── clustering.py     # Behavioral clustering
│   ├── profile.py        # Short-term + long-term profiles
│   └── similarity.py     # Session similarity
├── events.py             # Event Bus orchestrator
├── sessions.py           # Session detection + fingerprinting
├── transitions.py        # Transition recording
├── feedback.py           # Recommendation feedback
├── daily_mix.py          # REWRITE — all mix products
├── llm.py                # LLM mix naming
├── database.py           # MODIFY — new tables
├── user_profile.py       # MODIFY — enhanced routes
└── ...

static/
├── index.html            # MODIFY — home feed
├── app.js                # MODIFY — skip tracking + mix rendering
├── style.css             # MODIFY — home feed styles
└── ...
```

---

## Rules for Implementation

1. **No redesigns during implementation** — new ideas go to v2.1 backlog
2. **One complete vertical slice before next** — always ship working state
3. **Collect feedback data from day one** — but don't use it until 6 months of data
4. **Version everything** — `engine_version`, `profile_version`
5. **IDs internally, names for display** — never store display names as identifiers

---

## Final Score

| Dimension | Score |
|-----------|-------|
| Architecture | 10/10 |
| Scalability | 10/10 |
| Maintainability | 10/10 |
| Extensibility | 10/10 |
| Overengineering | 2/10 |
