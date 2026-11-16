#!/usr/bin/env python3
"""Generate Ichiro-fork OSM local-mode tiles (Kanto test build).

Reader contract (from openpilot/system/hardware/fan_controller.py, cit02mm):
  TILE_DIR = /data/osm_data/tiles
  file name: tile_{ty}_{tx}.sqlite   tx = floor(lon / 0.18), ty = floor(lat / 0.18)
  tables: ways(id, name, highway, maxspeed)
          way_nodes(way_id, node_id)   -- rowid order = node sequence
          nodes(id, lat, lon)
  A tile contains every highway way that has >= 1 node inside the tile,
  with the way's FULL geometry (all way_nodes + all nodes).
  Missing name/maxspeed tags are stored as "" (osm_fetch handles "" explicitly;
  NULL would break it).
"""
import math
import os
import sqlite3
import sys

import osmium

GRID = 0.18
SRC = os.path.expanduser("~/workspace/osm-tiles/src/kanto-latest.osm.pbf")
WORK = os.path.expanduser("~/workspace/osm-tiles")
STAGING = os.path.join(WORK, "staging.sqlite")
OUTDIR = os.path.join(WORK, "tiles")


def tile_xy(lat, lon):
    return (math.floor(lon / GRID), math.floor(lat / GRID))


class Collector(osmium.SimpleHandler):
    def __init__(self, conn):
        super().__init__()
        self.conn = conn
        self.cur = conn.cursor()
        self.n_ways = 0
        self.n_nodes = 0

    def way(self, w):
        tags = w.tags
        if "highway" not in tags:
            return
        name = tags.get("name", "")
        maxspeed = tags.get("maxspeed", "")
        self.cur.execute(
            "INSERT OR REPLACE INTO ways(id, name, highway, maxspeed) VALUES (?,?,?,?)",
            (w.id, name, tags["highway"], maxspeed),
        )
        rows = []
        for n in w.nodes:
            loc = n.location
            rows.append((w.id, n.ref))
            self.cur.execute(
                "INSERT OR IGNORE INTO nodes(id, lat, lon) VALUES (?,?,?)",
                (n.ref, loc.lat, loc.lon),
            )
        self.cur.executemany("INSERT INTO way_nodes(way_id, node_id) VALUES (?,?)", rows)
        self.n_ways += 1
        self.n_nodes += len(rows)
        if self.n_ways % 50000 == 0:
            self.conn.commit()
            print(f"  ways={self.n_ways} node_refs={self.n_nodes}", flush=True)


def phase_a():
    if os.path.exists(STAGING):
        os.remove(STAGING)
    conn = sqlite3.connect(STAGING)
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.executescript(
        """
        CREATE TABLE ways(id INTEGER PRIMARY KEY, name TEXT, highway TEXT, maxspeed TEXT);
        CREATE TABLE way_nodes(way_id INTEGER, node_id INTEGER);
        CREATE TABLE nodes(id INTEGER PRIMARY KEY, lat REAL, lon REAL);
        """
    )
    h = Collector(conn)
    h.apply_file(SRC, locations=True)
    conn.commit()
    nw = conn.execute("SELECT COUNT(*) FROM ways").fetchone()[0]
    nn = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    print(f"phase A done: ways={nw} nodes={nn}", flush=True)
    conn.close()


def phase_b():
    os.makedirs(OUTDIR, exist_ok=True)
    conn = sqlite3.connect(STAGING)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wn_way ON way_nodes(way_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wn_node ON way_nodes(node_id)")
    conn.commit()
    tiles = conn.execute(
        "SELECT DISTINCT CAST(lon/0.18 AS INT), CAST(lat/0.18 AS INT) FROM nodes"
    ).fetchall()
    print(f"tiles to build: {len(tiles)}", flush=True)
    total_bytes = 0
    skipped = 0
    for i, (tx, ty) in enumerate(tiles):
        path = os.path.join(OUTDIR, f"tile_{ty}_{tx}.sqlite")
        # ways touching this tile (any node inside the tile bbox)
        lat0, lat1 = ty * GRID, (ty + 1) * GRID
        lon0, lon1 = tx * GRID, (tx + 1) * GRID
        way_ids = [
            r[0]
            for r in conn.execute(
                """SELECT DISTINCT wn.way_id FROM way_nodes wn
                   JOIN nodes n ON n.id = wn.node_id
                   WHERE n.lat >= ? AND n.lat < ? AND n.lon >= ? AND n.lon < ?""",
                (lat0, lat1, lon0, lon1),
            ).fetchall()
        ]
        if not way_ids:
            continue
        # resumable: skip tiles that already exist complete
        # (integrity ok AND way count matches the staging expectation)
        if os.path.exists(path):
            try:
                chk = sqlite3.connect(path)
                ok = chk.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                cnt = (
                    chk.execute("SELECT COUNT(*) FROM ways").fetchone()[0]
                    if ok
                    else -1
                )
                chk.close()
                if ok and cnt == len(way_ids):
                    skipped += 1
                    total_bytes += os.path.getsize(path)
                    continue
            except Exception:
                pass
            os.remove(path)
        t = sqlite3.connect(path)
        t.execute("PRAGMA journal_mode=OFF")
        t.execute("PRAGMA synchronous=OFF")
        t.executescript(
            """
            CREATE TABLE ways(id INTEGER PRIMARY KEY, name TEXT, highway TEXT, maxspeed TEXT);
            CREATE TABLE way_nodes(way_id INTEGER, node_id INTEGER);
            CREATE TABLE nodes(id INTEGER PRIMARY KEY, lat REAL, lon REAL);
            """
        )
        for chunk_start in range(0, len(way_ids), 400):
            chunk = way_ids[chunk_start : chunk_start + 400]
            ph = ",".join("?" for _ in chunk)
            t.executemany(
                "INSERT OR IGNORE INTO ways(id, name, highway, maxspeed) VALUES (?,?,?,?)",
                conn.execute(
                    f"SELECT id, name, highway, maxspeed FROM ways WHERE id IN ({ph})", chunk
                ).fetchall(),
            )
            t.executemany(
                "INSERT INTO way_nodes(way_id, node_id) VALUES (?,?)",
                conn.execute(
                    f"SELECT way_id, node_id FROM way_nodes WHERE way_id IN ({ph}) ORDER BY rowid",
                    chunk,
                ).fetchall(),
            )
            t.executemany(
                "INSERT OR IGNORE INTO nodes(id, lat, lon) VALUES (?,?,?)",
                conn.execute(
                    f"""SELECT DISTINCT n.id, n.lat, n.lon FROM nodes n
                        JOIN way_nodes wn ON wn.node_id = n.id
                        WHERE wn.way_id IN ({ph})""",
                    chunk,
                ).fetchall(),
            )
        t.execute("CREATE INDEX idx_wn_way ON way_nodes(way_id)")
        t.execute("CREATE INDEX idx_nodes_latlon ON nodes(lat, lon)")
        t.commit()
        t.close()
        total_bytes += os.path.getsize(path)
        if (i + 1) % 10 == 0:
            print(f"  tiles {i+1}/{len(tiles)} total={total_bytes/1e6:.0f} MB", flush=True)
    print(f"phase B done: total tile size = {total_bytes/1e6:.1f} MB (skipped {skipped} complete tiles)", flush=True)
    conn.close()


if __name__ == "__main__":
    if not os.path.exists(STAGING) or "--redo-a" in sys.argv:
        print("phase A: parsing PBF...", flush=True)
        phase_a()
    print("phase B: building tiles...", flush=True)
    phase_b()
    print("ALL DONE", flush=True)
