#!/usr/bin/env sh
# tune-intake fixture run: intake + sheets + stats for the five fixture episodes.
# Usage (from pipeline/): sh run_fixtures.sh [extra intake flags]
set -e
W=.data/webtoons
O=.data/out
mkdir -p "$O"
run() {
  slug=$1; folder=$2; shift 2
  echo "== $slug"
  uv run zumi intake "$folder" --out "$O/$slug.zumi" --report "$O/$slug-cuts.png" "$@" | grep -v '^report'
  uv run python -m zumi.sheets "$O/$slug-cuts.png" "$O/$slug.zumi" | grep -v sheet
}
run u395 "$W/unordinary/Episode_395" "$@"
run tog235 "$W/tower-of-god/_Season_3__Ep._235__Season_3_Finale" "$@"
run lo9 "$W/lore-olympus/Episode_9" "$@"
run sh14 "$W/sweet-home/Ep._14" "$@"
run cpc1 "$W/cursed-princess-club/Ep._1_-_The_King_Returns" "$@"
