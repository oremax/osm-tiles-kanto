# osm-tiles-kanto

openpilot（programanichiro フォーク、mici UI）のオフライン道路名表示用タイル。
関東分を Geofabrik の Kanto 抜粋（kanto-latest.osm.pbf、2026-11-15 取得）から生成。

## 形式（読み取り側 fan_controller.py の仕様に一致）

- ファイル名: `tiles/tile_{ty}_{tx}.sqlite`（tx = floor(lon / 0.18), ty = floor(lat / 0.18)、グリッド 0.18°）
- テーブル: `ways(id, name, highway, maxspeed)` / `way_nodes(way_id, node_id)`（rowid 順 = ノード順）/ `nodes(id, lat, lon)`
- 各タイルには、そのタイル内にノードを1つ以上持つ highway way の全ジオメトリ（全 way_nodes と全 nodes）を収録
- name / maxspeed が無い場合は NULL でなく空文字 "" を格納（読み取り側の前提）
- 道路のないグリッドセルにもスキーマのみの空タイルを配置（読み取り側は範囲内の全タイルへ接続を試みるため）

## 端末への入れ方

`tiles/` の中身を comma 端末の `/data/osm_data/tiles/` へコピーし、fan_controller を再起動（または端末を再起動）。
`/data/osm_data/tiles` が存在すると、起動時に自動でローカルモードになる。

## 再生成

```
./venv/bin/python gen_tiles.py        # staging.sqlite があれば Phase B のみ（完成済みタイルは検証してスキップ）
./venv/bin/python fill_empty_tiles.py # 空タイル補完
./venv/bin/python verify_tiles.py     # 読み取り側の関数そのもので検証
```

データ: © OpenStreetMap contributors（ODbL）
