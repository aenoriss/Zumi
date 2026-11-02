"""The speaker dataset (user, 2026-10-27): every bubble of the given episodes with its box image, the character cards
(numbered outlines), the bubble's outline and tail, and the current rules' proposal (speakers.assign), written for the
labelling page (speaker_label.html), served by `serve` on localhost with a save endpoint. Labels are the user's:
labels.json, {"<pid>#<bubble>": {"speakers": [card index], "kind": "card|off_panel|nobody|missing", "skip": bool,
"comment": the user's note, when written}} ("nobody": a caption or a sound effect, no character says it).

    uv run python experiments/speaker_dataset.py build <out root> <episode.zumi>...   (writes <out root>/speakers/)
    uv run python experiments/speaker_dataset.py tails <out root>                     (the page's tail view)
    uv run python experiments/speaker_dataset.py serve <out root> [port]              (default 8766)
"""
from __future__ import annotations

import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np
from scipy.ndimage import distance_transform_edt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import speakers as SP  # noqa: E402
from boxstore import Box  # noqa: E402
from chapter import Chapter  # noqa: E402
from workers import pmap  # noqa: E402

HERE = Path(__file__).resolve().parent


def outline(m: np.ndarray, eps: float = 1.5) -> list:
    cs, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [cv2.approxPolyDP(c, eps, True)[:, 0, :].tolist() for c in cs if cv2.contourArea(c) > 30]


def build_box(job: tuple) -> dict | None:
    """One box (root, episode .zumi, box index) of the dataset: its image saved, its record returned (None without
    layers or bubbles). A worker of build's pmap."""
    root, zp, i = job
    ch = Chapter(zp)
    pid = ch.pid(i)
    got = SP.load_box(Box(root / "dataset" / ch.stem, pid))
    if got is None:
        return None
    cards, bubbles, frames, (w, h) = got
    if not bubbles:
        return None
    ch.image(i).save(root / "speakers" / "boxes" / f"{pid}.jpg", quality=90)
    recs = []
    for b, a in sorted(zip(bubbles, SP.assign_all(cards, bubbles)), key=lambda ba: ba[0].order):
        recs.append({"id": b.id, "order": b.order, "kind": b.kind, "text": b.text, "frame": b.frame,
                     "outline": outline(b.mask), "tail_tip": b.tail_tip, "tail_dir": b.tail_dir,
                     "proposal": a})
    return {"pid": pid, "episode": zp.stem, "w": w, "h": h, "img": f"boxes/{pid}.jpg",
            "cards": [{"i": k, "key": c.key, "frame": c.frame, "outline": outline(c.mask)} for k, c in enumerate(cards)],
            "frames": [outline(f) for f in frames], "bubbles": recs}


def build(root: Path, zumis: list[Path]) -> None:
    out = root / "speakers"
    (out / "boxes").mkdir(parents=True, exist_ok=True)
    jobs = [(root, zp, i) for zp in zumis for i in range(len(Chapter(zp)))]
    boxes = [b for b in pmap(build_box, jobs) if b is not None]  # boxes across processes
    for b in boxes:
        print(f"{b['pid']}: {len(b['cards'])} cards, {len(b['bubbles'])} bubbles")
    (out / "dataset.json").write_text(json.dumps({"boxes": boxes}))
    (out / "index.html").write_text((HERE / "speaker_label.html").read_text(encoding="utf-8"), encoding="utf-8")
    if not (out / "labels.json").exists():
        (out / "labels.json").write_text("{}")
    print(f"{sum(len(b['bubbles']) for b in boxes)} bubbles in {len(boxes)} boxes -> {out}")


def tails_box(job: tuple) -> dict:
    """The tail view of one box (root, its dataset record): {"<pid>#<bubble>": view}. A worker of tails' pmap."""
    root, box = job
    got = SP.load_box(Box(root / "dataset" / box["episode"], box["pid"]))
    if got is None:
        return {}
    cards, bubbles, frames, _ = got
    dist = [distance_transform_edt(~c.mask) for c in cards]
    res = {}
    for b in bubbles:
        t = SP.tail_parts(b.mask)
        if t is None:
            continue
        shift = lambda rings: [[[x + t["x0"], y + t["y0"]] for x, y in ring] for ring in rings]
        aims = {f["card"]: round(f["aim"], 2) for f in SP.features(b, cards, dist) if f.get("aim", -1) > 0.85}
        res[f"{box['pid']}#{b.id}"] = {
            "r": t["r"], "body": shift(outline(t["body"])),
            "parts": [{"outline": shift(outline(p["mask"], 0.5)), "px": p["px"], "reach": round(p["reach"]),
                       "kept": p["kept"]} for p in t["parts"]],
            "aims": aims}
    return res


def tails(root: Path) -> None:
    """speakers/tails.json, the page's tail view: per bubble what speakers.tail saw (the opening radius, the body,
    each stripped part, kept or not) and the cards its tail aims at past the tail rule's 0.85."""
    out = root / "speakers"
    boxes = json.loads((out / "dataset.json").read_text())["boxes"]
    res = {k: v for r in pmap(tails_box, [(root, b) for b in boxes]) for k, v in r.items()}  # boxes across processes
    (out / "tails.json").write_text(json.dumps(res))
    print(f"tails: {len(res)} bubbles -> {out / 'tails.json'}")


def serve(root: Path, port: int) -> None:
    out = root / "speakers"

    class H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(out), **k)

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_POST(self):
            if self.path != "/save":
                self.send_error(404)
                return
            body = self.rfile.read(int(self.headers["Content-Length"]))
            labels = json.loads(body)
            (out / "labels.json").write_text(json.dumps(labels, indent=1))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

    print(f"labelling page: http://127.0.0.1:{port}/")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


if __name__ == "__main__":
    cmd, root = sys.argv[1], Path(sys.argv[2])
    if cmd == "build":
        build(root, [Path(p) for p in sys.argv[3:]])
    elif cmd == "tails":
        tails(root)
    else:
        serve(root, int(sys.argv[3]) if len(sys.argv) > 3 else 8766)
