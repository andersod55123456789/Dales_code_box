PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS program_state (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    cycle            INTEGER NOT NULL DEFAULT 1,
    week             INTEGER NOT NULL DEFAULT 1,
    week_repeat      INTEGER NOT NULL DEFAULT 0,
    ohp_cycle_offset INTEGER NOT NULL DEFAULT 0,
    reassess_banner  TEXT,
    started_on       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS day_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    log_date     TEXT    NOT NULL UNIQUE,
    weekday      TEXT    NOT NULL,
    cycle        INTEGER NOT NULL,
    week         INTEGER NOT NULL,
    week_repeat  INTEGER NOT NULL DEFAULT 0,
    week_type    TEXT    NOT NULL CHECK (week_type IN ('A','B')),
    day_complete INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT,
    notes        TEXT,
    created_at   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_day_log_date ON day_log (log_date);
CREATE INDEX IF NOT EXISTS idx_day_log_cycle_week ON day_log (cycle, week);

CREATE TABLE IF NOT EXISTS set_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    day_log_id    INTEGER NOT NULL REFERENCES day_log(id) ON DELETE CASCADE,
    exercise_id   TEXT    NOT NULL,
    exercise_name TEXT    NOT NULL,
    set_index     INTEGER NOT NULL,
    is_backoff    INTEGER NOT NULL DEFAULT 0,
    target_reps   INTEGER,
    actual_reps   INTEGER,
    target_load   REAL,
    actual_load   REAL,
    completed     INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL,
    UNIQUE (day_log_id, exercise_id, set_index, is_backoff)
);
CREATE INDEX IF NOT EXISTS idx_set_log_day ON set_log (day_log_id);
CREATE INDEX IF NOT EXISTS idx_set_log_exercise ON set_log (exercise_id);

CREATE TABLE IF NOT EXISTS anchor_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    day_log_id   INTEGER NOT NULL REFERENCES day_log(id) ON DELETE CASCADE,
    item_key     TEXT    NOT NULL,
    field_key    TEXT    NOT NULL,
    target_value TEXT,
    actual_value TEXT,
    completed    INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL,
    UNIQUE (day_log_id, item_key, field_key)
);
CREATE INDEX IF NOT EXISTS idx_anchor_log_day ON anchor_log (day_log_id);

CREATE TABLE IF NOT EXISTS metric_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    day_log_id  INTEGER NOT NULL REFERENCES day_log(id) ON DELETE CASCADE,
    exercise_id TEXT    NOT NULL,
    field_key   TEXT    NOT NULL,
    value_num   REAL,
    value_text  TEXT,
    created_at  TEXT    NOT NULL,
    UNIQUE (day_log_id, exercise_id, field_key)
);
CREATE INDEX IF NOT EXISTS idx_metric_log_day ON metric_log (day_log_id);

CREATE TABLE IF NOT EXISTS checkin (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    checkin_date    TEXT    NOT NULL UNIQUE,
    sleep_hours     REAL,
    sleep_quality   INTEGER CHECK (sleep_quality   BETWEEN 1 AND 5),
    energy          INTEGER CHECK (energy          BETWEEN 1 AND 5),
    soreness        INTEGER CHECK (soreness        BETWEEN 1 AND 5),
    mood            INTEGER CHECK (mood            BETWEEN 1 AND 5),
    resting_hr      INTEGER,
    pec_status      TEXT CHECK (pec_status      IN ('ok','niggle','pain')),
    knee_status     TEXT CHECK (knee_status     IN ('ok','niggle','pain')),
    shoulder_status TEXT CHECK (shoulder_status IN ('ok','niggle','pain')),
    notes           TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_checkin_date ON checkin (checkin_date);

CREATE TABLE IF NOT EXISTS week_completion (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle        INTEGER NOT NULL,
    week         INTEGER NOT NULL,
    repeat_index INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT    NOT NULL,
    UNIQUE (cycle, week, repeat_index)
);

CREATE TABLE IF NOT EXISTS test_battery (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    test_date  TEXT    NOT NULL,
    cycle      INTEGER NOT NULL,
    week       INTEGER NOT NULL,
    metric_key TEXT    NOT NULL,
    value_num  REAL,
    value_text TEXT,
    created_at TEXT    NOT NULL,
    UNIQUE (test_date, metric_key)
);
CREATE INDEX IF NOT EXISTS idx_test_battery_metric ON test_battery (metric_key);

CREATE TABLE IF NOT EXISTS adjustment (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_date   TEXT    NOT NULL,
    rule_key     TEXT    NOT NULL,
    message      TEXT    NOT NULL,
    suggestion   TEXT    NOT NULL,
    status       TEXT    NOT NULL CHECK (status IN ('pending','applied','ignored')),
    payload_json TEXT,
    created_at   TEXT    NOT NULL,
    resolved_at  TEXT,
    UNIQUE (scope_date, rule_key)
);
CREATE INDEX IF NOT EXISTS idx_adjustment_date ON adjustment (scope_date);

CREATE TABLE IF NOT EXISTS exercise_state (
    exercise_id          TEXT PRIMARY KEY,
    current_load         REAL,             
    added_weight_lb       REAL NOT NULL DEFAULT 0,  
    rep_range_lo          INTEGER NOT NULL,
    rep_range_hi          INTEGER NOT NULL,
    target_sets           INTEGER NOT NULL,
    load_step             REAL,             
    rir_target_lo          INTEGER NOT NULL DEFAULT 2,
    rir_target_hi          INTEGER NOT NULL DEFAULT 3,
    progression_mode      TEXT NOT NULL DEFAULT 'standard'
                           CHECK (progression_mode IN
                                  ('standard','reps_only','ramp_governed','excluded')),
    last_action           TEXT CHECK (last_action IN
                                  ('INCREASE_LOAD','DECREASE_LOAD','HOLD_LOAD')),
    sessions_in_mesocycle  INTEGER NOT NULL DEFAULT 0,  
    recent_sessions_json   TEXT,             
    last_recommendation_json TEXT,           
    updated_at             TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exercise_feedback (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    day_log_id   INTEGER NOT NULL REFERENCES day_log(id) ON DELETE CASCADE,
    exercise_id  TEXT    NOT NULL,
    rir_feedback TEXT    NOT NULL CHECK (rir_feedback IN
                          ('EASY','TARGET','HARD','FAILURE')),
    created_at   TEXT    NOT NULL,
    UNIQUE (day_log_id, exercise_id)
);
CREATE INDEX IF NOT EXISTS idx_exercise_feedback_ex ON exercise_feedback (exercise_id);

CREATE TABLE IF NOT EXISTS muscle_group_state (
    muscle_group          TEXT PRIMARY KEY,
    current_weekly_sets    INTEGER NOT NULL DEFAULT 0,
    last_increase_date     TEXT,
    cooldown_sessions_left INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS progression_event (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    day_log_id   INTEGER REFERENCES day_log(id) ON DELETE CASCADE,
    exercise_id  TEXT NOT NULL,
    event_type   TEXT NOT NULL CHECK (event_type IN
                  ('INCREASE_LOAD','DECREASE_LOAD','VOLUME_INCREASE',
                   'MESOCYCLE_PHASE_ADVANCE','MESOCYCLE_DELOAD')),
    detail_json  TEXT,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_progression_event_ex ON progression_event (exercise_id);
CREATE INDEX IF NOT EXISTS idx_progression_event_date ON progression_event (created_at);