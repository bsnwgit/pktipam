-- Site catalog — subnets.site and vlans.site stay plain TEXT columns (no
-- FK migration of existing values), but the UI now picks from this
-- managed list via a dropdown instead of free-typing a site name.
CREATE TABLE IF NOT EXISTS sites (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
