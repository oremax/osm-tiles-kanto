#!/usr/bin/env python3
"""Create schema-only tile files for every grid cell in the staging extent
that has no tile file yet. The reader's get_node_coordinatesZ connects to
every tile in the query bbox without an existence check, so missing files
inside the covered rectangle would raise 'no such table' mid-query."""
import os
import sqlite3

WORK = os.path.expanduser("~/workspace/osm-tiles")
STAGING = os.path.join(WORK, "staging.sqlite")
OUTDIR = os.path.join(WORK, "tiles")
GRID = 0.18

conn = sqlite3.connect(STAGING)
minlat, maxlat, minlon, maxlon = conn.execute(
    "SELECT MIN(lat), MAX(lat), MIN(lon), MAX(lon) FROM nodes"
).fetchone()
conn.close()
print(f"extent lat {minlat}..{maxlat} lon {minlon}..{maxlon}")

import math

tx0, tx1 = math.floor(minlon / GRID), math.floor(maxlon / GRID)
ty0, ty1 = math.floor(minlat / GRID), math.floor(maxlat / GRID)
created = 0
for ty in range(ty0, ty1 + 1):
    for tx in range(tx0, tx1 + 1):
        path = os.path.join(OUTDIR, f"tile_{ty}_{tx}.sqlite")
        if os.path.exists(path):
            continue
        t = sqlite3.connect(path)
        t.executescript(
            """
            CREATE TABLE ways(id INTEGER PRIMARY KEY, name TEXT, highway TEXT, maxspeed TEXT);
            CREATE TABLE way_nodes(way_id INTEGER, node_id INTEGER);
            CREATE TABLE nodes(id INTEGER PRIMARY KEY, lat REAL, lon REAL);
            CREATE INDEX idx_wn_way ON way_nodes(way_id);
            CREATE INDEX idx_nodes_latlon ON nodes(lat, lon);
            """
        )
        t.commit()
        t.close()
        created += 1
print(f"created {created} empty tiles; grid {tx1-tx0+1}x{ty1-ty0+1}")
