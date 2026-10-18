"""zumi CLI. Step 1: `zumi intake <folder> --out ep.zumi [--report cuts.png]`."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import typer
from PIL import Image

from . import FORMAT_VERSION, GENERATOR, intake
from .manifest import Episode, Layer, Layout, Manifest, Panel, Series, Size, StripPlacement
from .pack import pack

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", s.lower()).strip("-") or "episode"


@app.command()
def intake_cmd(
    folder: Path = typer.Argument(..., exists=True, file_okay=False, help="Per-panel files or webtoon slices"),
    out: Path = typer.Option(..., "--out", "-o", help="Output .zumi path"),
    report: Path | None = typer.Option(None, "--report", help="Write a PNG of the strip with detected cuts"),
    mode: str = typer.Option("auto", help="auto | strip | panels. auto: >1 file with equal widths and no 'p' prefix = strip"),
    series_id: str = typer.Option(None, "--series"),
    episode_index: int = typer.Option(1, "--index"),
    tolerance: int = typer.Option(20, help="Per-channel distance from the row's median colour that makes a pixel an outlier; a row is blank with < 0.2 % outliers"),
    min_gutter: int = typer.Option(40, help="Blank rows needed to count as a gutter"),
    min_panel: int = typer.Option(120, help="Slabs shorter than this merge into the panel above"),
):
    """Stitch, cut at gutters and pack a .zumi with one flat base layer per panel."""
    files = intake.list_images(folder)
    if not files:
        raise typer.BadParameter(f"no images in {folder}")
    if mode == "auto":
        mode = "panels" if all(f.stem.lower().startswith("p") for f in files) else "strip"

    series_id = series_id or _slug(folder.parent.name)
    episode_id = _slug(folder.name)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    panels: list[Panel] = []
    images: dict[str, Image.Image] = {}
    layout: Layout | None = None

    if mode == "strip":
        strip = intake.split_strip(files, tolerance=tolerance, min_gutter=min_gutter, min_panel=min_panel)
        bg = "#{:02X}{:02X}{:02X}".format(*strip.background)
        layout = Layout(mode="scroll", width=strip.image.width, height=strip.image.height, background=bg)
        for i, (slab, im) in enumerate(zip(strip.slabs, intake.crop_slabs(strip))):
            pid = f"p{i:03d}"
            images[pid] = im
            panels.append(
                Panel(
                    id=pid,
                    index=i,
                    size=Size(w=im.width, h=im.height),
                    strip=StripPlacement(y=slab.y, h=slab.h, gutterAfter=slab.gutter_after),
                    layers=[Layer(id="base", name="source", image=f"panels/{pid}/layers/base.png", depth=0.0, band="background")],
                )
            )
        typer.echo(f"strip {strip.image.width}x{strip.image.height}, background {bg}, {len(files)} slices -> {len(panels)} panels")
        if report:
            intake.report(strip, report)
            typer.echo(f"report {report}")
    else:
        layout = Layout(mode="carousel")
        for i, f in enumerate(files):
            pid = f"p{i:03d}"
            im = Image.open(f).convert("RGBA")
            images[pid] = im
            panels.append(
                Panel(
                    id=pid,
                    index=i,
                    size=Size(w=im.width, h=im.height),
                    layers=[Layer(id="base", name="source", image=f"panels/{pid}/layers/base.png", depth=0.0, band="background")],
                )
            )
        typer.echo(f"{len(panels)} panel files")

    manifest = Manifest(
        formatVersion=FORMAT_VERSION,
        generator=GENERATOR,
        createdAt=now,
        series=Series(id=series_id, title=series_id),
        episode=Episode(id=episode_id, index=episode_index, title=folder.name, layout=layout),
        panels=panels,
    )
    pack(manifest, images, out)
    typer.echo(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")


app.command(name="intake")(intake_cmd)

if __name__ == "__main__":
    app()
