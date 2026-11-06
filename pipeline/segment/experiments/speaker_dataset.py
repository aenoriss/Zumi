"""The speaker dataset (user, 2026-10-27): every bubble of the given episodes with its box image, the character cards
(numbered outlines), the bubble's outline and tail, and the current rules' proposal (speakers.assign), written for the
labelling page (speaker_label.html), served by `serve` on localhost with a save endpoint. Labels are the user's:
labels.json, {"<pid>#<bubble>": {"speakers": [card index], "kind": "card|off_panel|nobody|missing", "skip": bool,
"comment": the user's note, when written}} ("nobody": a caption or a sound effect, no character says it).

    uv run python experiments/speaker_dataset.py build <out root> <episode.zumi>...   (writes <out root>/speakers/)
    uv run python experiments/speaker_dataset.py tails <out root>                     (the page's tail view)
    uv run python experiments/speaker_dataset.py agent <out root>                     (images and tasks for agents)
    uv run python experiments/speaker_dataset.py merge <out root>                     (their answers, for review)
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


AGENT_CHUNK = 30  # boxes per labelling agent: one box image is ~1.5k tokens, and a run of boxes keeps the conversation


def agent(root: Path) -> None:
    """The agent labelling job (user, 2026-11-03: agents label, the user reviews): per box speakers/agent/<pid>.png,
    the art with every card outlined and numbered C1.. and every balloon outlined and numbered B<id>, and per run of
    AGENT_CHUNK boxes in reading order speakers/agent/task-<n>.json, the boxes' balloon texts. Without the rules'
    answers, so the agent's labels are a second opinion and not a copy of the rules."""
    out = root / "speakers" / "agent"
    out.mkdir(parents=True, exist_ok=True)
    boxes = json.loads((root / "speakers" / "dataset.json").read_text())["boxes"]
    for b in boxes:
        im = cv2.imread(str(root / "speakers" / b["img"]))
        lab = []
        for c in b["cards"]:
            col = tuple(int(v) for v in cv2.cvtColor(np.uint8([[[(c["i"] * 67 // 2) % 180, 230, 255]]]), cv2.COLOR_HSV2BGR)[0, 0])
            for ring in c["outline"]:
                cv2.polylines(im, [np.int32(ring)], True, (0, 0, 0), 5)
                cv2.polylines(im, [np.int32(ring)], True, col, 2)
            pts = np.int32([p for ring in c["outline"] for p in ring])
            if len(pts):
                lab.append((f"C{c['i'] + 1}", (int(pts[:, 0].mean()), int(pts[:, 1].min()) + 18), col))
        for x in b["bubbles"]:
            for ring in x["outline"]:
                cv2.polylines(im, [np.int32(ring)], True, (0, 0, 0), 4)
                cv2.polylines(im, [np.int32(ring)], True, (0, 216, 255), 2)
            pts = np.int32([p for ring in x["outline"] for p in ring])
            if len(pts):
                lab.append((f"B{x['id']}", (int(pts[:, 0].min()) + 14, int(pts[:, 1].min()) + 12), (0, 216, 255)))
        for t, (cx, cy), col in lab:  # labels last, over every outline
            (tw, th), _ = cv2.getTextSize(t, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(im, (cx - tw // 2 - 4, cy - th - 4), (cx + tw // 2 + 4, cy + 5), (0, 0, 0), -1)
            cv2.putText(im, t, (cx - tw // 2, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2, cv2.LINE_AA)
        cv2.imwrite(str(out / f"{b['pid']}.png"), im)
    n = 0
    for ep in dict.fromkeys(b["episode"] for b in boxes):
        eb = [b for b in boxes if b["episode"] == ep]
        for s in range(0, len(eb), AGENT_CHUNK):
            task = [{"pid": b["pid"], "image": str((out / f"{b['pid']}.png").resolve()), "cards": len(b["cards"]),
                     "balloons": [{"id": x["id"], "text": x["text"]} for x in b["bubbles"]]} for b in eb[s:s + AGENT_CHUNK]]
            (out / f"task-{n}.json").write_text(json.dumps({"episode": ep, "boxes": task}, indent=1))
            n += 1
    print(f"{len(boxes)} box images, {n} tasks -> {out}")


SPOT_CHECK = 40  # agreements the user checks at random: their error rate is what the agreed labels hide


def merge(root: Path) -> None:
    """The agents' answers (speakers/agent/answer-<n>.json, {"<pid>#<id>": {"speakers": [C number], "kind", "why"}})
    into labels.json, each marked "by": "agent" where it disagrees with the rules and "agree" where it agrees, and
    review.json for the page: every disagreement with both answers, then SPOT_CHECK agreements at random. The page
    drops "by" when the user saves, so a label without it is reviewed. The user's own labels are never replaced."""
    import random
    out = root / "speakers"
    boxes = json.loads((out / "dataset.json").read_text())["boxes"]
    labels = json.loads((out / "labels.json").read_text())
    ans = {k: v for f in sorted((out / "agent").glob("answer-*.json")) for k, v in json.loads(f.read_text()).items()}
    say = lambda sp, kind: "card " + "+".join(str(s + 1) for s in sorted(sp)) if sp else kind
    review, agreed, missing = {}, [], 0
    for b in boxes:
        for x in b["bubbles"]:
            k = f"{b['pid']}#{x['id']}"
            if k in labels and not labels[k].get("by"):
                continue
            a = ans.get(k)
            if a is None:
                missing += 1
                continue
            sp = sorted(s - 1 for s in a.get("speakers", []) if 1 <= s <= len(b["cards"]))
            kind = "card" if sp else a.get("kind", "off_panel")
            p = x["proposal"]
            same = (sp == sorted(p["speakers"])) if sp or p["speakers"] else kind == p["speaker_kind"]
            labels[k] = {"speakers": sp, "kind": kind, "skip": False, "by": "agree" if same else "agent"}
            if same:
                agreed.append(k)
            else:
                review[k] = (f"Agent: {say(sp, kind)} ({a.get('why', '')}) · rules: {say(p['speakers'], p['speaker_kind'])}"
                             f" ({p['rule']})")
    for k in random.Random(0).sample(agreed, min(SPOT_CHECK, len(agreed))):
        review[k] = f"Spot check: the agent and the rules agree ({say(labels[k]['speakers'], labels[k]['kind'])})"
    (out / "labels.json").write_text(json.dumps(labels, indent=1))
    (out / "review.json").write_text(json.dumps(review, indent=1))
    print(f"{len(agreed)} agree, {len(review) - min(SPOT_CHECK, len(agreed))} disagree, {missing} unanswered; "
          f"review.json: {len(review)} bubbles")


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
    elif cmd == "agent":
        agent(root)
    elif cmd == "merge":
        merge(root)
    else:
        serve(root, int(sys.argv[3]) if len(sys.argv) > 3 else 8766)
