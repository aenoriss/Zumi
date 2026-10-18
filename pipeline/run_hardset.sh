#!/usr/bin/env sh
# tune-intake round 2: the hard set (episodes that failed most on the retest, plus new ones in the same styles).
# Usage (from pipeline/): OUT=.data/out/r2-itN sh run_hardset.sh [extra intake flags]
W=.data/webtoons
O=${OUT:-.data/out/r2}
mkdir -p "$O"
run() {
  slug=$1; folder=$2; shift 2
  echo "== $slug"
  uv run zumi intake "$folder" --out "$O/$slug.zumi" --report "$O/$slug-cuts.png" "$@" | grep -v '^report'
  uv run python -m zumi.sheets "$O/$slug-cuts.png" "$O/$slug.zumi" | grep -v sheet
}
# failed on the retest
run hc169  "$W/canvas-housecat-philosophy/Episode_169" "$@"
run hc09   "$W/canvas-housecat-philosophy/Episode_09" "$@"
run uprol  "$W/unordinary/Prologue" "$@"
run tb7    "$W/true-beauty/Episode_7" "$@"
run orv0   "$W/omniscient-reader/Episode_0_-_Prologue" "$@"
run tog246 "$W/tower-of-god/_Season_2__Ep._246" "$@"
run tog0   "$W/tower-of-god/_Season_1__Ep._0" "$@"
run wc10   "$W/canvas-witch-and-her-corgi/Ep._10__Shedding" "$@"
# new, same styles, never seen
run hc01   "$W/canvas-housecat-philosophy/Episode_01" "$@"
run hc02   "$W/canvas-housecat-philosophy/Episode_02" "$@"
run u1     "$W/unordinary/Episode_1" "$@"
run tb4    "$W/true-beauty/Episode_4" "$@"
