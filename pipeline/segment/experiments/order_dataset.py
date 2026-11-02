"""The reading-order dataset (user, 2026-11-02): every box with two or more lettering cards from the given speaker
datasets (speaker_dataset.py's <root>/speakers/dataset.json, its outlines and box images), combined into one, with
the order the rules read them in today (speakers.order_bubbles, via answers_of), written for the labelling page
(order_label.html), served by `serve` on localhost with a save endpoint. Labels are the user's:
order_labels.json, {"<pid>": {"order": [bubble id, ...], "discard": [bubble id, ...], "comment": the user's note}}
(discard and comment when given): the bubbles in the order they are read; a bubble left out is not read in sequence
(background sound effects); a discarded one is no dialogue at all (a segmentation error), out of the scoring.

    uv run python experiments/order_dataset.py build <out root> <speaker root>...   (writes <out root>/)
    uv run python experiments/order_dataset.py serve <out root> [port]              (default 8771)
"""
from __future__ import annotations

import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import speakers as SP  # noqa: E402
from boxstore import Box  # noqa: E402
from workers import pmap  # noqa: E402

HERE = Path(__file__).resolve().parent


def rules_order(job: tuple) -> dict[str, int] | None:
    """{bubble id: its place in the rules' reading order} for one box (root, episode, pid). A worker of build's pmap."""
    root, ep, pid = job
    g = SP.answers_of(Box(root / "dataset" / ep, pid))
    return None if g is None else {str(b["id"]): b["order"] for b in g["bubbles"]}


def build(out: Path, roots: list[Path]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    picked = []  # (source name, box record)
    for root in roots:
        for b in json.loads((root / "speakers/dataset.json").read_text())["boxes"]:
            if len(b["bubbles"]) >= 2:
                picked.append((root, b))
    orders = pmap(rules_order, [(root, b["episode"], b["pid"]) for root, b in picked])  # boxes across processes
    boxes = []
    for (root, b), order in zip(picked, orders):
        if order is None:
            continue
        bubbles = [{"id": str(x["id"]), "kind": x["kind"], "text": x["text"], "outline": x["outline"],
                    "rules": order.get(str(x["id"]))} for x in b["bubbles"]]
        boxes.append({"pid": b["pid"], "episode": b["episode"], "src": root.name, "w": b["w"], "h": b["h"],
                      "img": f"{root.name}/{b['img']}", "frames": b["frames"],
                      "bubbles": sorted(bubbles, key=lambda x: (x["rules"] is None, x["rules"]))})
    (out / "dataset.json").write_text(json.dumps({"boxes": boxes}))
    (out / "roots.json").write_text(json.dumps({r.name: str(r / "speakers") for r in roots}, indent=1))
    (out / "index.html").write_text((HERE / "order_label.html").read_text(encoding="utf-8"), encoding="utf-8")
    if not (out / "order_labels.json").exists():
        (out / "order_labels.json").write_text("{}")
    print(f"{len(boxes)} boxes, {sum(len(b['bubbles']) for b in boxes)} bubbles -> {out}")


def serve(out: Path, port: int) -> None:
    roots = {k: Path(v) for k, v in json.loads((out / "roots.json").read_text()).items()}

    class H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(out), **k)

        def translate_path(self, path):
            head, _, rest = path.lstrip("/").partition("/")
            if head in roots:  # a source dataset's box image
                return str(roots[head] / rest.split("?")[0])
            return super().translate_path(path)

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_POST(self):
            if self.path != "/save":
                self.send_error(404)
                return
            labels = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            (out / "order_labels.json").write_text(json.dumps(labels, indent=1))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

    print(f"ordering page: http://127.0.0.1:{port}/")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


if __name__ == "__main__":
    cmd, out = sys.argv[1], Path(sys.argv[2])
    if cmd == "build":
        build(out, [Path(p) for p in sys.argv[3:]])
    else:
        serve(out, int(sys.argv[3]) if len(sys.argv) > 3 else 8771)
