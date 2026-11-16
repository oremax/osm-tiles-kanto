#!/usr/bin/env python3
"""Verify generated tiles using the READER's own functions, extracted from
fan_controller.py via AST (avoids the module's import-time side effects)."""
import ast
import math
import os
import sqlite3
import sys

SRC = os.path.expanduser(
    "~/workspace/gitwork/cit02mm/openpilot/system/hardware/fan_controller.py"
)
TILES = os.path.expanduser("~/workspace/osm-tiles/tiles")

WANT = {
    "tile_xy",
    "tile_path",
    "get_conn",
    "tiles_in_bbox",
    "latlon_to_meter_scale",
    "world_to_vehicle_local",
    "query_roads_in_bbox",
    "get_node_coordinatesZ",
    "get_node_coordinates",
}

tree = ast.parse(open(SRC).read())
ns = {
    "math": math,
    "os": os,
    "sqlite3": sqlite3,
    "GRID_SIZE": 0.18,
    "TILE_DIR": TILES,
    "osm_tiles": None,
}
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in WANT:
        code = compile(ast.Module(body=[node], type_ignores=[]), SRC, "exec")
        exec(code, ns)

query = ns["query_roads_in_bbox"]
get_coords = ns["get_node_coordinates"]


def test(label, lat, lon, bearing=0.0):
    d = 50 / 111111.0
    dlon = 50 / (111111.0 * math.cos(math.radians(lat)))
    try:
        data = query(lat - d, lon - dlon, lat + d, lon + dlon, bearing, 8.0)
    except Exception as e:
        print(f"[{label}] EXCEPTION: {e}")
        return
    els = data["elements"]
    named = [e for e in els if e["tags"].get("name")]
    print(f"[{label}] ways={len(els)} named={len(named)}")
    for e in named[:6]:
        coords = get_coords(e["nodes"])
        print(
            f"    - {e['tags']['name']}  highway={e['tags']['highway']} "
            f"maxspeed={e['tags']['maxspeed']!r} nodes={len(e['nodes'])} resolved={len(coords)}"
        )


# Adachi (home), Tokyo
test("adachi", 35.7750, 139.8040)
# Shinjuku
test("shinjuku", 35.6938, 139.7034)
# tile-border stress: pick a point near a grid line (lon multiple of 0.18)
test("border", 35.7750, 139.86)
# outside coverage: Mt. Fuji area (Shizuoka, not in Kanto extract)
test("fuji-outside", 35.3606, 138.7274)
print("verify done")
