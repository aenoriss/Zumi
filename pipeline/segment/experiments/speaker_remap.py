"""The user's speaker labels carried from one segmentation of an episode to another (a reprocessing renumbers every
bubble and card): each old bubble goes to the new bubble its mask overlaps most (IoU at least MIN_IOU, one to one),
each labelled old card to the new cards mostly inside it (a card cut into one piece per frame maps to its piece in the
bubble's frame, or to every piece when none is there), or else to the new card it lies mostly inside (cards merged
into a group). Boxes run across processes (workers.pmap).
Labels that do not carry cleanly are listed in review.json for the labelling page.

    uv run python experiments/speaker_remap.py <old root> <new root> <episode>...
    uv run python experiments/speaker_remap.py compare <old root> <new root> <episode>...   (the page's old view)

Each root holds dataset/<episode>/ (the episode's out dir), speakers/ (dataset.json, labels.json) and chapters/. Run
speaker_dataset.py build on the new root first; writes the new root's speakers/labels.json (merged) and review.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import speakers as SP  # noqa: E402
from boxstore import Box  # noqa: E402
from workers import pmap  # noqa: E402

MIN_IOU = 0.5    # an old and a new bubble are one when their masks overlap this much
CARD_IN = 0.6    # a new card belongs to an old one when this share of it lies inside the old card


def iou(a: np.ndarray, b: np.ndarray) -> float:
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 0.0


def remap_box(job: tuple) -> tuple[dict, dict]:
    """One box (old root, new root, episode, pid, the old labels): (labels carried, {key: why not}). A worker of
    main's pmap."""
    old_root, new_root, ep, pid, old_labels = job
    carried, review = {}, {}
    old = SP.load_box(Box(old_root / "dataset" / ep, pid))
    new = SP.load_box(Box(new_root / "dataset" / ep, pid))
    if new is None:
        return carried, review
    ncards, nbubbles = new[0], new[1]
    if old is None:
        for b in nbubbles:
            review[f"{pid}#{b.id}"] = "new box: no old layers to carry a label from"
        return carried, review
    ocards, obubbles = old[0], old[1]
    # bubbles, one to one, best overlap first
    pairs = sorted(((iou(o.mask, n.mask), oi, ni) for oi, o in enumerate(obubbles) for ni, n in enumerate(nbubbles)),
                   reverse=True)
    taken_o, taken_n, match = set(), set(), {}
    for v, oi, ni in pairs:
        if v < MIN_IOU:
            break
        if oi not in taken_o and ni not in taken_n:
            taken_o.add(oi), taken_n.add(ni)
            match[ni] = (oi, v)
    # each old card -> the new cards mostly inside it (a card cut into pieces), or else the new card it lies mostly
    # inside (cards merged into one: a group, review_loop's "group")
    pieces = {oc: [nc for nc, n in enumerate(ncards) if n.mask.sum() and (n.mask & o.mask).sum() >= CARD_IN * n.mask.sum()]
              or [nc for nc, n in enumerate(ncards) if o.mask.sum() and (n.mask & o.mask).sum() >= CARD_IN * o.mask.sum()]
              for oc, o in enumerate(ocards)}
    for ni, n in enumerate(nbubbles):
        key = f"{pid}#{n.id}"
        if ni not in match:
            review[key] = "new bubble: no old bubble overlaps it by half"
            continue
        oi, v = match[ni]
        lab = old_labels.get(f"{pid}#{obubbles[oi].id}")
        if lab is None:
            review[key] = f"its old bubble (#{obubbles[oi].id}) was never labelled"
            continue
        if lab["kind"] != "card":
            carried[key] = dict(lab)
            continue
        # a card the new frames cut into pieces speaks from its piece in the bubble's frame (all pieces if none is)
        speakers = set()
        for s in lab["speakers"]:
            ps = pieces.get(s, [])
            speakers |= set([p for p in ps if ncards[p].frame == n.frame] or ps)
        speakers = sorted(speakers)
        lost = [s + 1 for s in lab["speakers"] if not pieces.get(s)]
        if not speakers or lost:
            review[key] = f"old label card {[s + 1 for s in lab['speakers']]}: card(s) {lost} have no new card"
            continue
        carried[key] = {"speakers": speakers, "kind": "card", "skip": lab.get("skip", False)}
    return carried, review


def compare_box(job: tuple) -> tuple[str, dict | None, dict]:
    """One box (old root, new root, episode, pid, the old labels): (pid, the old cards and frames as outlines, {new
    key: the old bubble it matches, its outline and its label}). A worker of compare's pmap."""
    from speaker_dataset import outline
    old_root, new_root, ep, pid, old_labels = job
    old = SP.load_box(Box(old_root / "dataset" / ep, pid))
    new = SP.load_box(Box(new_root / "dataset" / ep, pid))
    if old is None or new is None:
        return pid, None, {}
    ocards, obubbles, oframes = old[0], old[1], old[2]
    box = {"cards": [{"i": k, "outline": outline(c.mask)} for k, c in enumerate(ocards)],
           "frames": [outline(f) for f in oframes]}
    bubbles = {}
    for n in new[1]:
        v, o = max(((iou(o.mask, n.mask), o) for o in obubbles), default=(0.0, None), key=lambda x: x[0])
        if o is not None and v >= MIN_IOU:
            bubbles[f"{pid}#{n.id}"] = {"old": o.id, "iou": round(v, 2), "outline": outline(o.mask),
                                        "label": old_labels.get(f"{pid}#{o.id}")}
    return pid, box, bubbles


def compare(old_root: Path, new_root: Path, eps: list[str]) -> None:
    """speakers/compare.json in the new root, for the labelling page's old-segmentation view: per box the old cards
    and frames, per new bubble the old one it matches and the label given there."""
    old_labels = json.loads((old_root / "speakers" / "labels.json").read_text())
    new_sp = new_root / "speakers"
    boxes = [b for b in json.loads((new_sp / "dataset.json").read_text())["boxes"] if b["episode"] in eps]
    jobs = [(old_root, new_root, b["episode"], b["pid"],
             {k: v for k, v in old_labels.items() if k.startswith(b["pid"] + "#")}) for b in boxes]
    out = {"boxes": {}, "bubbles": {}}
    for pid, box, bubbles in pmap(compare_box, jobs):  # boxes across processes
        if box is not None:
            out["boxes"][pid] = box
        out["bubbles"] |= bubbles
    (new_sp / "compare.json").write_text(json.dumps(out))
    print(f"compare: {len(out['bubbles'])} bubbles matched in {len(out['boxes'])} boxes -> {new_sp / 'compare.json'}")


def main():
    if sys.argv[1] == "compare":
        return compare(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4:])
    old_root, new_root, eps = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    old_labels = json.loads((old_root / "speakers" / "labels.json").read_text())
    new_sp = new_root / "speakers"
    new_labels = json.loads((new_sp / "labels.json").read_text()) if (new_sp / "labels.json").exists() else {}
    boxes = [b for b in json.loads((new_sp / "dataset.json").read_text())["boxes"] if b["episode"] in eps]
    jobs = [(old_root, new_root, b["episode"], b["pid"],
             {k: v for k, v in old_labels.items() if k.startswith(b["pid"] + "#")}) for b in boxes]
    carried, review = 0, {}
    for c, r in pmap(remap_box, jobs):  # boxes across processes
        new_labels |= c
        review |= r
        carried += len(c)
    (new_sp / "labels.json").write_text(json.dumps(new_labels, indent=1))
    (new_sp / "review.json").write_text(json.dumps(review, indent=1))
    print(f"{', '.join(eps)}: {carried} labels carried, {len(review)} bubbles to label by hand (review.json)")


if __name__ == "__main__":
    main()
