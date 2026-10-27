"""Hidden background layers for the parallax viewer, front to back, each an erased plate (flux_erase.py) shown only
where its mask says the layer in front can open up:

  layer 1  characters and lettering erased: what is directly behind a character (the table, the chair) continues
  layer 2  characters, lettering and every nearer object erased (occlusion_mask.py): the floor behind the table

  depth   DA3MONO on each plate, scale and shift fitted to the panel's precise depth outside that plate's mask
          (depth.depth_like), then kept at least 2% behind whatever is in front of it there (the panel, the layers
          before it); lettering is an overlay, so the floor under a caption is not pushed behind the caption box
  cloud   cloud3/<id>.bin: every point of cloud2 + each layer's points inside its mask grown GROW px
  mesh    mesh/<id>.bg<k>.f32 + mesh/<id>.bg<k>.png per layer, at the foreground mesh's stride

    python hidden_layer_export.py <panel id> <characters npz> <lettering npz> \
        --layer <plate1.png> <mask1.png> [--layer <plate2.png> <mask2.png> ...]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation

from masks import load_masks
from occlusion_mask import VIEWER, read_cloud2
from parallax import BORDER_BAND, merge_floaters, settle_border

GROW = 24  # px past the mask: the layer reaches well under the outline of what covers it, no dark seam
DEEP_GROW = 90    # px past its mask for the deepest of several layers (occlusion_mask.MAX_PX)
PUSH_RADIUS = 15  # px: a layer is kept behind the deepest panel depth this close
GLOW_PX = 10      # px outside a character searched for its drawn glow (the erase mask's own growth)
GLOW_DROP = 8.0   # luma levels the art must be lighter than the erased background to count as glow
GLOW_OPACITY = 0.0  # share of the drawn glow kept on the figure: at full strength, and still at 0.35, it stood out as
                    # a white rim in 3D (user, 2026-10-25). At 0 the glow is gone (the floor under it is the erased
                    # background); the front view loses the drawn glow
BAND_FAR = 45     # px: the far side of an object edge is looked for this far (bands are at most 90 px wide)
BACKDROP_BANDS = False  # near-side bands in the backdrop (backdrop_bands): on ToG 228 p6 they smeared 156k px of
                        # floor colour over the table and the chair the plate had completed behind the man, and the
                        # cut backdrop covered the panel's holes without them (measured below the call)
INK_DROP = 30  # a line this much darker than its surroundings (0-255) is ink; the 10 px ring around the man is
               # a quarter below luma 71 because of his shadow, so a plain darkness threshold would take the shadow too


def sharpen_steps(D, where, win=9, rounds=2, min_range=0.03):
    """Ramps into steps inside the characters: the depth model blurs an arm in front of the body into a slope of small
    steps, each under the mesh's 3% cut, so the mesh kept them as long stretched triangles (pin 261025-185441: the
    sleeve over the robe; 1404 of 57132 figure triangles steeper than 0.5% per cell). A toggle filter (Kramer &
    Bruckner) moves each pixel to the nearer of its window's min and max where that window spans an edge (range over
    min_range), so the slope becomes one step the mesh cuts; flat areas are untouched."""
    import cv2
    out = D.astype(np.float32).copy()
    ker = np.ones((win, win), np.uint8)
    for _ in range(rounds):
        lo, hi = cv2.erode(out, ker), cv2.dilate(out, ker)
        edge = where & (hi / np.maximum(lo, 1e-6) > 1 + min_range)
        snap = np.where(out - lo < hi - out, lo, hi)
        out = np.where(edge, snap, out)
    return out


def silhouette_grid(D, chars, letters, G0, k, rim=3, tol=0.04):
    """The panel's mesh grid with clean silhouettes: (depth grid, segment grid).

    Outliers: the depth cleanup gives many of a character's rim pixels the depth of the floor beside it, so the mesh
    dragged the silhouette's edge vertices down to the floor and stretched triangles across it. Rim pixels (inside
    the character mask, within `rim` px of its edge) more than `tol` off the depth of the nearest interior pixel take
    that depth. Segments: 0 scene, 1 characters, 2 lettering; the viewer drops every triangle joining two segments,
    so a character never stretches into the floor (the hidden layers fill behind the cut)."""
    import cv2
    from scipy.ndimage import binary_erosion, distance_transform_edt
    Dc = D.copy()
    core = binary_erosion(chars, iterations=rim)
    if core.any():
        _, (iy, ix) = distance_transform_edt(~core, return_indices=True)
        inner = cv2.medianBlur(D, 5)[iy, ix]  # depth of the nearest interior pixel (smoothed)
        edge = chars & ~core
        off = edge & (np.abs(D - inner) / inner > tol)
        Dc[off] = inner[off]
    gh, gw = G0.shape
    G = np.where(G0 > 0, Dc[::k, ::k][:gh, :gw], 0).astype(np.float32)
    seg = np.where(chars, 1, np.where(letters, 2, 0)).astype(np.uint8)[::k, ::k][:gh, :gw]
    # figure surface: characters and lettering on their own grid, reaching one cell past the mask with the depth of
    # the nearest figure pixel, so the silhouette is drawn by the texture's alpha (the full-resolution mask), not by
    # the 2 px grid: cutting the panel mesh at the mask snapped the outline to grid steps and shaved its ink
    figs = chars | letters
    if not figs.any():  # nothing to draw separately
        return G, np.ascontiguousarray(seg), Dc, np.zeros_like(G)
    _, (fy, fx) = distance_transform_edt(~figs, return_indices=True)
    Dfig = np.where(figs, Dc, Dc[fy, fx])
    reach = binary_dilation(figs, iterations=3 * k)[::k, ::k][:gh, :gw]
    Gfig = np.where(reach & (G0 > 0), Dfig[::k, ::k][:gh, :gw], 0).astype(np.float32)
    return G, np.ascontiguousarray(seg), Dc, Gfig


def backdrop_bands(Dl, plate, region, T=0.05, far_radius=45):
    """The backdrop (last layer) is cut at its own depth jumps like every surface, so an object in it (a table) floats
    instead of being joined to the floor by stretched triangles. So the cut shows no hole, a band along the near side
    of each jump, as wide as head motion can reveal there (occlusion_mask.depth_bands), takes the far side's depth (the
    deepest value within far_radius px) and the colour of the nearest far-side pixel: the floor continues under the
    table's edge. Returns (depth, plate, band pixels)."""
    import cv2
    from scipy.ndimage import distance_transform_edt
    from occlusion_mask import depth_bands
    D = np.where(region, Dl, 0).astype(np.float32)
    band, _ = depth_bands(np.where(region, Dl, np.median(Dl[region])).astype(np.float32), region, T)
    band &= region
    if not band.any():
        return Dl, plate, 0
    k = 2 * far_radius + 1
    far = cv2.dilate(D, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))  # the deepest depth nearby: the far side
    src = region & ~band & (D >= far * 0.98)  # pixels that are themselves the far side
    out_d = np.where(band, far, Dl).astype(np.float32)
    out_c = plate.copy()
    if src.any():
        _, (iy, ix) = distance_transform_edt(~src, return_indices=True)
        out_c[band] = plate[iy[band], ix[band]]
    return out_d, out_c, int(band.sum())


def snap_to_mask(Dl, obj, region, band=6):
    """Depth steps exactly on an object's outline: inside the mask each pixel takes the depth of the nearest pixel well
    inside it, outside (within `band` px) the depth of the nearest pixel well outside it. The depth model's edge was a
    few px off the object in the texture, so the chair's colours sat at floor depth, painted on the background behind
    it (user, 2026-10-25); with the step on the outline, the cut follows the drawn edge."""
    from scipy.ndimage import binary_erosion, distance_transform_edt
    inner = binary_erosion(obj, iterations=band)
    outer = region & ~binary_dilation(obj, iterations=band)
    if not inner.any() or not outer.any():
        return Dl
    _, (iy, ix) = distance_transform_edt(~inner, return_indices=True)
    _, (oy, ox) = distance_transform_edt(~outer, return_indices=True)
    ring_in = obj & ~inner
    ring_out = binary_dilation(obj, iterations=band) & ~obj & region
    out = Dl.copy()
    out[ring_in] = Dl[iy[ring_in], ix[ring_in]]
    out[ring_out] = Dl[oy[ring_out], ox[ring_out]]
    return out


def export_layers(pid, info, P, C, L, D, chars, letters, layers, mono, root=VIEWER, objects=None, layered=False):
    """layers: [(plate rgb array, mask)], front to back; chars, letters: the raw masks. Reads the panel's mesh grid
    and writes cloud3 and the mesh layers under root (parallax.py's layout); returns log lines.
    layered: the box's depth is flat layers (parallax.layered_depth); each hidden layer then carries on the flat
    surface around what was erased. depth_like fitted DA3MONO to the flat scene and brought its ramp back into the
    hidden layers (room box: scene 0.44-0.52, mesh to 0.69)."""
    import depth as DP
    from occlusion_mask import GROW as LETTER_GROW
    from scipy.ndimage import distance_transform_edt
    h, w = D.shape

    def hidden_depth(plate, mask, keep):
        if layered:
            src = ~mask & (L != 2)
            if not src.any():
                return D.copy(), 0.0
            _, (iy, ix) = distance_transform_edt(~src, return_indices=True)
            return np.where(mask, D[iy, ix], D).astype(np.float32), 0.0
        return DP.depth_like(mono, Image.fromarray(plate), D, keep)
    n = h * w
    f = max(w, h) / (2 * np.tan(np.radians(55.0) / 2))
    v, u = np.mgrid[0:h, 0:w].astype(np.float32)
    assert np.allclose(P[..., 0], (u - w / 2) * D / f, atol=1e-4), "cloud2 back-projection differs from fov 55"
    # lettering is data, not art (it is redrawn from data): the panel surface shows the erased background where the
    # bubbles and captions were, at the background's depth. Kept as drawn, the boxes stood on the panel surface while
    # the hidden layer behind them was not pushed back, and rings of it floated in front of the floor (ToG 228 p6)
    depth_cache = {}
    lettering = np.zeros((h, w), bool)
    if layers and letters.any():
        plate1, mask1 = layers[0]
        Dl1, err1 = hidden_depth(plate1, mask1, ~binary_dilation(mask1, iterations=16) & (L != 2))
        depth_cache[0] = (Dl1, err1)
        lettering = binary_dilation(letters, iterations=LETTER_GROW) & mask1 & (L != 2)
        D = np.where(lettering, Dl1, D).astype(np.float32)
        C = np.where(lettering[..., None], plate1, C)
    figures = chars  # the only figures left on the panel surface
    front = D.copy()  # depth of the nearest surface so far, per pixel
    fg = C.copy()  # panel colours, with stray outline ink on background surfaces filled in (below)
    import cv2
    luma = C.astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    # ink = thin dark lines: darker than a 7 px closing of the image (black-hat); a broad shadow is not
    lines = cv2.morphologyEx(luma, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))) > INK_DROP
    ink = np.zeros((h, w), bool)
    allP, allC, allL = [P.reshape(-1, 3)], [], [L.ravel()]
    m = json.loads((root / "mesh" / f"{pid}.json").read_text())
    k = m["stride"]
    # where the viewer cuts the panel's own mesh (a cell whose corner depths differ by more than its jump ratio): the
    # panel surface opens there, so a hidden layer must exist behind every such cell, masked or not (only 2131 of
    # 8123 cut cells had one when the layers followed the erase masks alone: black outlines from an angle)
    G0 = np.fromfile(root / "mesh" / f"{pid}.f32", np.float32).reshape(m["gh"], m["gw"])
    # the panel's surface = where its mesh has depth. Not cloud2's label 2: 70% of those pixels sit on character and
    # lettering edges (42235 of 60576, ToG 228 p6), so excluding them left no hidden layer behind every silhouette
    panel = np.kron(G0 > 0, np.ones((k, k), bool))[:h, :w]
    panel = np.pad(panel, ((0, h - panel.shape[0]), (0, w - panel.shape[1])), mode="edge")
    # the character's glow: the art draws a light halo just outside the figure. Left on the scene surface it stayed on
    # the floor as a whitish outline when the head moved (user, 2026-10-25). Ring pixels clearly lighter than the
    # erased background (the first layer's plate) belong to the character: they join his figure surface and move with
    # him; the scene under the whole ring shows the background (below)
    glow_ring = binary_dilation(chars, iterations=GLOW_PX) & ~chars & (L != 2)
    glow = np.zeros_like(chars)
    if layers and chars.any():
        lum = lambda a: a.astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
        glow = glow_ring & (lum(C) - lum(layers[0][0]) > GLOW_DROP)
        glow = binary_dilation(glow, iterations=1) & glow_ring  # its soft outer edge too
    # the glow as light over the background: original = a * white + (1 - a) * background, so a = how far each pixel is
    # lifted from the background towards white. As soft alpha on the figure surface it composites back to the original
    # from the front and fades into whatever is behind from an angle (a full-opacity copy was a white rim)
    glow_a = np.zeros(chars.shape, np.float32)
    if glow.any():
        Pb = layers[0][0].astype(np.float32)
        lift = (C.astype(np.float32) - Pb) / np.maximum(255.0 - Pb, 8.0)
        glow_a = np.where(glow, np.clip(lift.mean(-1), 0, 1) * GLOW_OPACITY, 0).astype(np.float32)
    figure = chars | glow
    G, seg, Dc, Gfig = silhouette_grid(D, figure, np.zeros_like(letters), G0, k)
    # the ring of grid points step 4 put just outside the art (parallax.build) keeps its own depth: the gutter pixel
    # under it has none worth taking
    ring = (G0 > 0) & (L == 2)[::k, ::k][: G0.shape[0], : G0.shape[1]]
    G = np.where(ring, G0, G).astype(np.float32)
    Gfig.tofile(root / "mesh" / f"{pid}.fig.f32")
    # no back surface behind the figure's splits: it duplicated the texture; drawing the figure uncut instead joined
    # the hand to the table (2026-10-25). The figure is cut at its depth jumps like every surface
    for old in (root / "mesh").glob(f"{pid}.figback.*"):
        old.unlink()
    fig_rgb = np.asarray(Image.open(root / "mesh" / f"{pid}.png").convert("RGB")).copy()
    fig_rgb[glow & ~chars] = 255  # the glow's colour: white light; its strength is the alpha
    fig_alpha = np.where(chars, 1.0, glow_a)
    rgba = np.dstack([fig_rgb, (fig_alpha * 255).astype(np.uint8)])
    Image.fromarray(rgba, "RGBA").save(root / "mesh" / f"{pid}.fig.png")
    snapped = int((Dc != D).sum())
    allP[0] = np.stack([(u - w / 2) * Dc / f, -(v - h / 2) * Dc / f, -Dc], -1).reshape(-1, 3)  # the cloud too
    front = Dc.copy()
    # the scene surface is background under the characters: the erased plate's depth (kept behind the character) and,
    # in its texture, the plate's colours. Cut at the character's edge instead, it left a band of up to 4 px where
    # neither it nor the figure surface (alpha at the full-resolution mask) drew, and the softer, shadowless hidden
    # layer showed through as a halo (edge_metric halo error 9.6 on ToG 228 p6). Continuous behind him, the figure's
    # alpha draws the exact silhouette over it
    under_tex = None
    if layers and chars.any():
        # the FIRST layer (only characters erased): what is directly behind them, objects included. The last layer
        # also erases objects (objects_layer.py) and took the chair from behind the man (frontal seam 2.9 -> 4.6)
        first = 0
        plateB, maskB = layers[first]
        if first not in depth_cache:
            depth_cache[first] = hidden_depth(plateB, maskB, ~binary_dilation(maskB, iterations=16) & (L != 2))
        Dbg = np.maximum(DP.align_locally(depth_cache[first][0], D, maskB, panel & (L != 2)), Dc * 1.02)
        G = np.where(seg == 1, Dbg[::k, ::k][: G.shape[0], : G.shape[1]], G).astype(np.float32)
        under_tex = plateB
    G.tofile(root / "mesh" / f"{pid}.fgclean.f32")
    seg.tofile(root / "mesh" / f"{pid}.seg.u8")
    st = np.stack([G[:-1, :-1], G[:-1, 1:], G[1:, :-1], G[1:, 1:]])
    valid = (st > 0).all(0)
    cut = valid & (st.max(0) / np.where(valid, st.min(0), 1) > m["jump"])
    cutpix = np.zeros((h, w), bool)
    for y, x in zip(*np.nonzero(cut)):
        cutpix[y * k:y * k + k + 1, x * k:x * k + k + 1] = True
    cutpix = binary_dilation(cutpix, iterations=6)
    for old in (root / "mesh").glob(f"{pid}.bg*"):
        old.unlink()
    log = [f"silhouettes: {snapped} character rim pixels snapped to the character's depth; "
           f"{int(cut.sum())} mesh cells cut (depth jumps + character/lettering edges)"]
    for li, (plate, mask) in enumerate(layers, 1):
        # the deepest layer reaches as far as an edge can reveal (the bands' maximum): 24 px left black arcs behind the
        # chair back and the table rim at a large head move (pin 261025-191954)
        grow = DEEP_GROW if li == len(layers) and len(layers) > 1 else GROW
        region = (binary_dilation(mask, iterations=grow) | cutpix) & panel  # gutters stay out
        keep = ~binary_dilation(mask, iterations=16) & panel & (L != 2)
        Dl, err = depth_cache.get(li - 1) or hidden_depth(plate, mask, keep)
        Dl = DP.align_locally(Dl, D, mask, panel & (L != 2))  # meets the box's own depth at the fill's border
        # the same cleanup as the panel's depth (parallax.py): the frame's false edge settled, floaters merged
        Dl = settle_border(Dl, ~panel, BORDER_BAND)
        Dl, _ = merge_floaters(Dl, region)
        if objects is not None and objects.any() and li < len(layers):  # the layers that still show the objects
            Dl = snap_to_mask(Dl, objects, region)
        # outline ink at background depth: the depth cleanup gives most of a character's (or table's) dark outline
        # the depth of the floor beside it (75% of the dark rim pixels, ToG 228 p6), so the panel layer keeps a black
        # contour glued to the floor once the character moves off it. Panel pixels in this layer's mask that are not
        # nearer than the plate's own surface are that background: they take the plate's clean colour
        # never inside the character and lettering masks themselves: feet and a robe hem touch the floor and have its
        # depth, but they are the character
        stray = mask & panel & ~figures & (D >= Dl * 0.97)
        # only the ink: the rest of that ring is floor as drawn (with the character's shadow, which the plate has not:
        # taking the plate's colour there drew a light halo around him)
        ink |= stray & lines
        # only inside the mask (where something in front was erased): outside it the layer IS the scene, at the scene's
        # own depth (align_locally); pushed 2% back there too, it never coincided with the visible surface (median
        # 2.7-4.7% apart, ToG 228 p6) and the layered mesh could not join them
        behind = region & binary_dilation(mask, iterations=2)
        # behind the DEEPEST panel depth within PUSH_RADIUS px, not the depth right in front: pushed behind "near" on
        # one side of a panel jump and "far" on the other, the layer copied the jump and was cut in the same place,
        # covering 817 of 3477 panel holes (ToG 228 p6); against the local deepest depth both sides sit at the far
        # side's depth and the layer runs on behind the hole
        deepest = cv2.dilate(front, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * PUSH_RADIUS + 1,) * 2))
        # smoothed: the dilated minimum ends in a hard step PUSH_RADIUS px in from an object's rim, which cut the deeper
        # layer there (black arcs along the table rim and the chair back, pin 261025-192204)
        # Only the deepest layer: in the layer behind the characters the chair and table must keep their cut edges
        # and float (smoothed there too, they were joined to the floor by stretched triangles, pin 261025-193556)
        if li == len(layers) and len(layers) > 1:
            deepest = cv2.GaussianBlur(deepest, (0, 0), PUSH_RADIUS)
        Dl = np.where(behind, np.maximum(Dl, deepest * 1.02), Dl)
        if li == len(layers) == 1:
            # (only without an objects layer: there the objects are erased for real, and this band's raised depth left
            # a step at its edge, black arcs behind the chair back and the table rim, pin 261025-191954)
            # behind object edges (scene depth jumps away from the characters): a 5% head shift opens up to ~50 px
            # behind a table's rim, the layer reached 6 px past the cut and still held the table at its own depth,
            # so a black arc opened there. A band on the near side, as wide as the edge can reveal, takes the far
            # side's depth (the deepest panel depth near it) and colours inpainted from around it
            from occlusion_mask import depth_bands
            away = panel & ~binary_dilation(chars, iterations=GROW + 4)
            band, _ = depth_bands(front.astype(np.float32), away, 0.05)
            band &= away
            if band.any():
                far = cv2.dilate(front, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * BAND_FAR + 1,) * 2))
                Dl = np.where(band, np.maximum(far * 1.02, Dl), Dl).astype(np.float32)
                filled = cv2.inpaint(np.ascontiguousarray(plate), band.astype(np.uint8), 5, cv2.INPAINT_TELEA)
                # the few pixels at the cut itself are seen from the front: they keep the plate's (the art's) colours,
                # inpainted ones raised the frontal seam error from 2.6 to 4.9; only deeper in the band, which only
                # head motion reveals, are the colours inpainted
                at_cut = binary_dilation(cutpix, iterations=2)
                plate = np.where((band & ~at_cut)[..., None], filled, plate)
                region = region | band
                log.append(f"layer {li}: {int(band.sum())} px of band behind object edges (far depth, inpainted colour)")
        front = np.where(region, np.maximum(front, Dl), front)
        allP.append(np.stack([(u - w / 2) * Dl / f, -(v - h / 2) * Dl / f, -Dl], -1)[region])
        allC.append(plate[region])
        allL.append(np.full(int(region.sum()), 3, np.uint8))
        np.where(region, Dl, 0)[::k, ::k][: m["gh"], : m["gw"]].astype(np.float32).tofile(root / "mesh" / f"{pid}.bg{li}.f32")
        Image.fromarray(plate).save(root / "mesh" / f"{pid}.bg{li}.png")
        log.append(f"layer {li}: depth error outside its mask {err * 100:.1f}% (median); "
                   f"{region.mean() * 100:.1f}% of the panel, {int(region.sum())} points; "
                   f"{int((stray & lines).sum())} outline ink pixels at background depth")
    # grown 1 px for the antialiased edge of the line, filled from the floor around it
    fg = cv2.inpaint(np.ascontiguousarray(fg), binary_dilation(ink, iterations=1).astype(np.uint8), 3, cv2.INPAINT_TELEA)
    allC.insert(0, fg.reshape(-1, 3))  # the cloud keeps the characters' own colours
    tex = fg.copy()
    if under_tex is not None:  # the scene surface's texture: background under the characters (figure surface on top)
        # where the figure surface draws (the glow included): no halo left on the floor. Not the whole ring: its
        # other pixels (his cast shadow) are seen from the front and must stay as drawn (halo error 5.4 -> 32)
        under = chars | glow
        tex[under] = under_tex[under]
    Image.fromarray(tex).save(root / "mesh" / f"{pid}.fgclean.png")  # the mesh's texture with hidden layers on
    out = root / "cloud3"
    out.mkdir(exist_ok=True)
    with open(out / f"{pid}.bin", "wb") as fh:
        for a, dt in ((allP, np.float32), (allC, np.uint8), (allL, np.uint8)):
            fh.write(np.concatenate(a).astype(dt).tobytes())
    total = sum(len(x) for x in allL)
    (out / f"{pid}.json").write_text(json.dumps({**info, "count": total, "hidden": total - n}))
    # every layer is cut at its depth jumps like the panel (an uncut backdrop joined a table to the floor with stretched
    # triangles); the backdrop's cuts are filled from behind by its near-side bands (backdrop_bands)
    jumps = [m["jump"]] * len(layers)
    # scene_seg_cut false: the scene surface is not cut at characters (it is background under them, see above)
    (root / "mesh" / f"{pid}.layers.json").write_text(json.dumps({"layers": len(layers), "jump": jumps,
                                                                 "scene_seg_cut": under_tex is None}))
    log.append(f"cloud3: {total} points ({total - n} hidden in {len(layers)} layers)")
    return log


def main():
    import depth as DP
    pid, cpath, lpath = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    layers = [(np.asarray(Image.open(sys.argv[i + 1]).convert("RGB")), np.asarray(Image.open(sys.argv[i + 2]).convert("L")) > 127)
              for i, a in enumerate(sys.argv) if a == "--layer"]
    info, img, P, C, L, D = read_cloud2(pid)
    chars = np.logical_or.reduce([x.mask for x in load_masks(cpath)])
    letters = np.logical_or.reduce([x.mask for x in load_masks(lpath)])
    print("\n".join(export_layers(pid, info, P, C, L, D, chars, letters, layers, DP.load())))


if __name__ == "__main__":
    main()
