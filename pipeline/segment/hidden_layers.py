"""Steps 4-5 per box, lettering first: masks -> ONE FLUX Erase call -> a lettering-free base image -> depth, point
cloud and mesh from that base (parallax.build) -> the hidden layer behind the characters.

Lettering is data, never art (it is redrawn from data), so it is removed BEFORE depth: run on the original box it got
its own depth and stood in the point cloud and the mesh as flat cards. The base image is the box with its lettering
replaced by erased pixels. Where a bubble overlaps a character the full plate shows background there, not the
character, so such boxes send a second copy in the same call with only the lettering erased, and take their base from
it. Copies of one box share its call, side by side; different boxes never share a call (a neighbour's colours bled into
the fills, ToG 228 p9), calls run in parallel.

    python hidden_layers.py <box id> <box.png> <characters npz> <lettering npz> <out dir>
episode.py runs prepare() -> erase_boxes() -> finish() over all boxes.
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation

from flux_erase import erase_packed, erase_panel, spent_today
from hidden_layer_export import export_layers
from masks import load_masks
from occlusion_mask import GROW, VIEWER, read_cloud2

MAX_ERASE = 1.0   # no limit (user, 2026-10-26): at 0.60 (a bigger erase leaves the model little to go on) 14 of
                  # Pepper&Carrot 39's 29 boxes with characters kept them painted on the backdrop, behind their own
                  # cards. Was: above it only the lettering is erased
                  # (it must go: it is redrawn from data); if the lettering alone is above it, nothing is
OVERLAP_PX = 200  # lettering pixels on a character before the box needs a lettering-only copy for its base image
PACK_MP = 2.0     # size of a call carrying two copies
WORKERS = 4       # erase calls in flight at once
SEAM_GROW = 24    # px a character or object fill reaches past its edge, feathered (finish)
# depth-found objects and bands (occlusion_mask.py) are not erased: depth alone could not tell objects from background
# (a table 6% nearer than the floor, a chair 0.8%, misread page pieces 8-39%; test set r1, 2026-10-25)


@dataclass
class Box:
    pid: str
    out: Path
    img: np.ndarray     # the original box
    chars: np.ndarray   # characters, fringe included
    letters: np.ndarray
    gutter: np.ndarray
    lettering: np.ndarray  # letters grown GROW px, gutter out: what the base image replaces
    full: np.ndarray       # the hidden layer's erase: characters + lettering (or lettering only, past MAX_ERASE)
    kinds: list            # per copy sent: "letters" (lettering only), "full", "all" (full + objects)
    page: np.ndarray       # what is sent: the art's bounding box, gutter painted white
    crop: tuple            # y0, y1, x0, x1 of the art in the box
    fringe: np.ndarray     # the part of `chars` claimed from outside the masks (parallax.claim_fringe)
    every: np.ndarray | None = None  # full + chosen objects (the deepest layer), when objects were given
    objects: np.ndarray | None = None  # the chosen objects' own masks (SAM), gutter out

    @property
    def masks(self):
        y0, y1, x0, x1 = self.crop
        pick = {"letters": self.lettering, "full": self.full, "all": self.every}
        return [pick[k][y0:y1, x0:x1] for k in self.kinds]


def prepare(pid, img, chars, letters, out, log=print, objects=None):
    """Erase masks for one box, from its image and masks alone (no depth needed). None: nothing to erase.
    objects: the big objects chosen for erasing (experiments/object_masks.py). Every mask goes into the box's ONE call:
    with objects, the copies are "full" (lettering + characters: what is right behind a character, the table he sits
    at) and "all" (+ the objects: the floor and wall behind them)."""
    import parallax as PX
    out.mkdir(parents=True, exist_ok=True)
    img = np.asarray(img.convert("RGB")) if isinstance(img, Image.Image) else img
    g = PX.gutter(Image.fromarray(img), letters)
    fringe = PX.claim_fringe(Image.fromarray(img), chars, g)  # the fringe is the character's
    chars = chars | fringe
    lettering = binary_dilation(letters, iterations=GROW) & ~g
    full = binary_dilation(chars | letters, iterations=GROW) & ~g
    art = max(1, int((~g).sum()))
    if full.sum() > MAX_ERASE * art:
        if lettering.sum() > MAX_ERASE * art:
            log(f"{pid}: erase would cover {full.sum() / art * 100:.0f}% of the art, lettering alone "
                f"{lettering.sum() / art * 100:.0f}%: nothing erased")
            return None
        log(f"{pid}: erase would cover {full.sum() / art * 100:.0f}% of the art: lettering only "
            f"({lettering.sum() / art * 100:.0f}%), characters stay without a hidden layer")
        full = lettering
    if not full.any():
        log(f"{pid}: nothing to erase")
        return None
    overlap = int((lettering & binary_dilation(chars, iterations=2)).sum())
    kinds = ["letters", "full"] if lettering.any() and overlap > OVERLAP_PX and full is not lettering else ["full"]
    every = None
    if objects is not None and objects.any():
        # 16 px around objects: at 8 the erase model kept a ghost of the desk (a top corner and a leg, ToG 228 p6)
        every = (full | binary_dilation(objects, iterations=16)) & ~g
        if every.sum() <= MAX_ERASE * art:
            kinds = [k for k in kinds if k != "letters"] + ["all"]  # the lettering base then comes from "full"
        else:
            log(f"{pid}: with the objects the erase would cover {every.sum() / art * 100:.0f}% of the art: objects skipped")
            every = None
    # only the art goes to the model: wide white gutters around small art came back as white fill (ToG 228 p7)
    ys, xs = np.nonzero(~g)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    page = img.copy()
    page[g] = 255
    log(f"{pid}: erase {full.sum() / art * 100:.1f}% of the art, lettering {lettering.sum() / art * 100:.1f}% "
        f"(on characters {overlap} px) -> {len(kinds)} cop{'ies' if len(kinds) > 1 else 'y'} {kinds}")
    return Box(pid, out, img, chars, letters, g, lettering, full, kinds, page[y0:y1, x0:x1], (y0, y1, x0, x1), fringe,
               every, objects & ~g if every is not None else None)


def erase_boxes(boxes, mp=PACK_MP, workers=WORKERS, log=print):
    """{pid: [erased crop per copy]}. One call per box, its copies side by side; a single copy is padded with its own
    mirrored edges instead (erase_panel). Paid results are kept: each box's crops are saved as soon as they come back
    (erased-<kind>.png) and a rerun reuses them, so a crash never pays twice. Stops at the daily budget."""
    result, todo = {}, []
    for b in boxes:
        got = []
        for k, m in zip(b.kinds, b.masks):
            f, fm = b.out / f"erased-{k}.png", b.out / f"mask-{k}.png"
            # reused only for the very mask it was made with: a changed mask (the bubble rule in parallax.gutter) with
            # the same crop size was taken as a hit before
            if f.exists() and fm.exists() and np.array_equal(np.asarray(Image.open(fm)) > 0, m):
                a = np.asarray(Image.open(f).convert("RGB"))
                if a.shape[:2] == m.shape:
                    got.append(a.copy())
        if len(got) == len(b.kinds):
            result[b.pid] = got
        else:
            todo.append(b)
    if len(todo) < len(boxes):
        log(f"{len(boxes) - len(todo)} boxes reuse saved erase results")

    def call(b):
        items = [(b.page, m) for m in b.masks]
        if len(items) == 1:
            plate, raw, line = erase_panel(*items[0])
            return [plate], [raw], line
        plates, line = erase_packed(items, 48, mp)
        return plates, erase_packed.last_raw, line

    with ThreadPoolExecutor(workers) as ex:
        for fut, b in [(ex.submit(call, b), b) for b in todo]:
            try:
                plates, raws, line = fut.result()
            except SystemExit as e:
                log(f"STOP erase: {e}")
                continue
            except Exception as e:  # one refused or failed box (BFL "Content Moderated" on a fight scene) skips only itself
                log(f"erase {b.pid.rsplit('-', 1)[-1]} failed, box kept without erasing: {str(e)[:160]}")
                continue
            for k, crop, raw, m in zip(b.kinds, plates, raws, b.masks):
                Image.fromarray(crop).save(b.out / f"erased-{k}.png")
                Image.fromarray(m.astype(np.uint8) * 255).save(b.out / f"mask-{k}.png")
                Image.fromarray(raw).save(b.out / f"raw-{k}.png")  # the model's whole output: its colour transform
            result[b.pid] = plates
            log(f"erase {b.pid.rsplit('-', 1)[-1]}: {line}")
    log(f"{len(todo)} erase calls for {len(boxes)} boxes; BFL spend today {spent_today():.2f} USD")
    return result


def colour_transform(raw, ref, same):
    """One global colour transform (3x3 + offset, least squares in RGB) taking the erase model's output to the
    original, fitted where both show the same scene (outside every mask: about half the box). The model shifts the tone
    of its whole image (fills came back up to 22 L brighter); a ring around each fill read the character's own shadow
    and outline and drew his silhouette (match_tone), a fit over half the box cannot. Returns a function on images."""
    X = np.c_[raw[same].reshape(-1, 3).astype(np.float64), np.ones(int(same.sum()))]
    Y = ref[same].reshape(-1, 3).astype(np.float64)
    sub = np.arange(len(X))[:: max(1, len(X) // 200000)]
    A, *_ = np.linalg.lstsq(X[sub], Y[sub], rcond=None)
    return lambda im: np.clip(np.c_[im.reshape(-1, 3).astype(np.float64), np.ones(im.shape[0] * im.shape[1])] @ A,
                              0, 255).reshape(im.shape).astype(np.uint8)


def match_tone(plate, ref, mask, ring=24, sigma=40):
    """The erase model returns its whole image a little shifted in tone (warmer or paler), so a fill did not match the
    scene around it (user, 2026-10-25). Per channel, a smooth gain map is measured in a ring just outside the mask,
    where plate and ref should agree, carried in under the mask, and applied to the plate's masked pixels only."""
    import cv2
    from depth import fill_under
    known = binary_dilation(mask, iterations=ring) & ~mask
    if known.sum() < 500:
        return plate
    a, b = ref.astype(np.float32), plate.astype(np.float32)
    out = b.copy()
    wk = cv2.GaussianBlur(known.astype(np.float32), (0, 0), sigma)
    ok = wk > 0.02
    for c in range(3):
        sa = cv2.GaussianBlur(np.where(known, a[..., c], 0), (0, 0), sigma)
        sb = cv2.GaussianBlur(np.where(known, b[..., c], 0), (0, 0), sigma)
        gain = np.where(ok, (sa + 1) / (sb + 1), 1.0).astype(np.float32)
        gain = fill_under(gain, ~ok)
        out[..., c] = np.where(mask, b[..., c] * np.clip(gain, 0.75, 1.33), b[..., c])
    return np.clip(out, 0, 255).astype(np.uint8)


def match_seam(plate, ref, mask, band=12, sigma=8, exclude=None):
    """Colour continuity across a fill's border: per channel, the offset between the scene just outside the mask and
    the fill just inside it (smoothed along the border), carried into the whole fill by normalised convolution (as
    depth.fill_under), so the fill meets its surroundings with no step and keeps its own texture (the idea of Poisson
    blending). match_tone could not see the fill's cast: the saved plate equals the original outside the mask."""
    import cv2
    from depth import fill_under
    inner = mask & ~binary_dilation(~mask, iterations=band)
    edge_in = mask & ~inner
    edge_out = binary_dilation(mask, iterations=band) & ~mask
    if exclude is not None:  # the ring reads scene only: not the gutter (the black caption box is still there) or figures
        edge_out &= ~exclude
    if edge_in.sum() < 100 or edge_out.sum() < 100:
        return plate
    a, b = ref.astype(np.float32), plate.astype(np.float32)
    off = np.zeros_like(b)
    for c in range(3):
        mo = cv2.GaussianBlur(np.where(edge_out, a[..., c], 0), (0, 0), sigma)
        wo = cv2.GaussianBlur(edge_out.astype(np.float32), (0, 0), sigma)
        mi = cv2.GaussianBlur(np.where(edge_in, b[..., c], 0), (0, 0), sigma)
        wi = cv2.GaussianBlur(edge_in.astype(np.float32), (0, 0), sigma)
        known = (wo > 0.05) & (wi > 0.05) & edge_in
        d = np.where(known, mo / np.maximum(wo, 1e-6) - mi / np.maximum(wi, 1e-6), 0).astype(np.float32)
        off[..., c] = fill_under(d, ~known)
    return np.clip(np.where(mask[..., None], b + off, b), 0, 255).astype(np.uint8)


def plates_for(box, crops):
    """The erased crops as whole-box plates ({kind: rgb}, tone-matched, fills feathered in) and the lettering-free
    base image (the box with only its lettering replaced). Saved as plate-<kind>.png and base.png."""
    y0, y1, x0, x1 = box.crop
    plates = {}
    for k, c in zip(box.kinds, crops):
        f = box.out / f"raw-{k}.png"
        if f.exists():  # the model's pixels in the plate brought to the original's tone (colour_transform)
            raw = np.asarray(Image.open(f).convert("RGB"))
            mk = {"letters": box.lettering, "full": box.full, "all": box.every}[k][y0:y1, x0:x1]
            same = ~binary_dilation(mk, iterations=8) & ~box.gutter[y0:y1, x0:x1]
            T = colour_transform(raw, box.img[y0:y1, x0:x1], same)
            model = np.any(c != box.page, axis=-1)  # where the plate took the model's pixels
            c = np.where(model[..., None], T(c), c)
            if k != "letters":
                # the fill grown SEAM_GROW px past its edge and feathered over that band: a hard edge at the mask
                # left a visible seam around each patch (user, 2026-10-25); further out the model's (tone-matched)
                # pixels and the original show the same floor, so the blend has nothing to hide
                import cv2
                # the mask only: outside it the layer keeps the original's cast shadows (the model's shadow removal
                # there made the revealed floor lighter than the visible floor next to it, a jagged step in 3D)
                core = mk
                grown = binary_dilation(core, iterations=SEAM_GROW) & ~box.gutter[y0:y1, x0:x1]
                dist = cv2.distanceTransform((~core).astype(np.uint8), cv2.DIST_L2, 5)
                a = np.where(core, 1.0, np.where(grown, np.clip(1 - dist / SEAM_GROW, 0, 1), 0.0))[..., None]
                c = (T(raw).astype(np.float32) * a + c.astype(np.float32) * (1 - a)).astype(np.uint8)
        p = box.img.copy()
        p[y0:y1, x0:x1] = c
        # no border-continuity correction on character and object fills: match_seam spread the erased figure's cast
        # shadow into the fill as dark blotches (ToG 228 p6); it is used on lettering fills only, where the ring is
        # clean scene
        p[box.gutter] = box.img[box.gutter]  # the model's shadow cleanup may have reached into the page
        # not tone-matched: match_tone (below) measured its gain next to the character's own shadow and outline and laid
        # a dark ghost of his silhouette over the fill (ToG 228 p6, 2026-10-25)
        plates[k] = p
        Image.fromarray(p).save(box.out / f"plate-{k}.png")
    base = box.img.copy()
    src = plates.get("letters", plates["full"])
    # the lettering fill matched to the scene around it: the erase model filled the caption box a little brighter,
    # a pale rectangle on the floor in every view (pin 261025-192620). Around a caption box the ring is clean scene,
    # so the match works there (around a character it drew his silhouette, see match_tone)
    src = match_seam(src, box.img, box.lettering, exclude=box.gutter | binary_dilation(box.chars, iterations=4))
    base[box.lettering] = src[box.lettering]
    Image.fromarray(base).save(box.out / "base.png")
    return plates, base


def finish(box, crops, mono, metric, root=VIEWER, log=print, objects=None):
    """LEGACY (legacy_mesh.py). Base image without lettering -> depth, cloud and mesh (parallax.build) -> hidden layer
    from the full plate."""
    import parallax as PX
    plates, base = plates_for(box, crops)
    info = PX.build(box.pid, Image.fromarray(base), box.chars, np.zeros_like(box.letters), mono, metric, root,
                    g=box.gutter, fringe_in=box.fringe, objects=objects)
    log(f"  {box.pid} depth on the lettering-free base: {info}")
    if box.full is box.lettering:
        return  # only the lettering was erased: no hidden layer behind the characters
    cinfo, img, P, C, L, D = read_cloud2(box.pid, root)
    layers = [(plates["full"], box.full)] + ([(plates["all"], box.every)] if "all" in plates else [])
    for line in export_layers(box.pid, cinfo, P, C, L, D, box.chars, np.zeros_like(box.letters), layers, mono, root,
                              objects=box.objects, layered=bool(info.get("layered"))):
        log(f"  {box.pid} {line}")
    import ldi_mesh  # scene + hidden layers as one surface, joined where their depths agree
    log(f"  {box.pid} layered mesh: {ldi_mesh.build(box.pid, root)}")


def build_plain(pid, img, chars, letters, mono, metric, root=VIEWER, log=print, objects=None):
    """A box with nothing erased: depth on the original image."""
    import parallax as PX
    log(f"  {pid} depth (nothing erased): {PX.build(pid, img, chars, letters, mono, metric, root, objects=objects)}")


def run_box(pid, img, chars, letters, out, mono=None, metric=None, root=VIEWER, log=print, objects=None):
    """One box end to end on its own call; the depth models load while the call runs."""
    import depth as DP
    t0 = time.perf_counter()
    box = prepare(pid, img, chars, letters, out, log, objects)
    with ThreadPoolExecutor(1) as pool:
        job = pool.submit(erase_boxes, [box], PACK_MP, 1, log) if box else None
        mono = mono or DP.load()
        metric = metric or DP.load(DP.METRIC_ID)
        crops = job.result() if job else {}
    if box and pid in crops:
        finish(box, crops[pid], mono, metric, root, log)
    elif box is None:
        build_plain(pid, img, chars, letters, mono, metric, root, log)
    log(f"{time.perf_counter() - t0:5.1f} s {pid} done")
    return mono, metric


def main():
    pid, ipath, cpath, lpath, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5])
    img = Image.open(ipath).convert("RGB")
    union = lambda ms: np.logical_or.reduce([m.mask for m in ms]) if ms else np.zeros((img.height, img.width), bool)
    run_box(pid, img, union(load_masks(cpath)), union(load_masks(lpath)), out)


if __name__ == "__main__":
    main()
