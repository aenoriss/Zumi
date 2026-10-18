"""Pydantic mirror of packages/format/schema/zumi.schema.json (format 1.0.0).

Only what the pipeline writes today. Fields are added as stages start to emit them;
the JSON Schema stays the normative definition and `pnpm --filter @zumi/format validate`
is the check.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Size(Model):
    w: int
    h: int


class Vec2(Model):
    x: float
    y: float


class Style(Model):
    preset: str | None = None
    prompt: str | None = None
    references: list[str] = Field(default_factory=list)


class Series(Model):
    id: str
    title: str
    creator: str | None = None
    language: str = "en"
    cover: str | None = None
    style: Style | None = None


class Layout(Model):
    mode: Literal["scroll", "carousel"]
    width: int | None = None
    height: int | None = None
    background: str | None = None


class MusicTrack(Model):
    id: str
    file: str
    loop: bool = True
    gain: float = 0.6
    loopStart: float | None = None
    loopEnd: float | None = None
    mood: str | None = None


class Episode(Model):
    id: str
    index: int
    title: str
    summary: str | None = None
    thumbnail: str | None = None
    music: list[MusicTrack] = Field(default_factory=list)
    durationHint: float | None = None
    layout: Layout | None = None


class Voice(Model):
    engine: str | None = None
    voiceId: str | None = None
    description: str | None = None


class CastMember(Model):
    id: str
    name: str
    voice: Voice | None = None
    color: str | None = None


class Layer(Model):
    id: str
    name: str
    image: str
    depth: float
    band: Literal["background", "mid", "foreground"]
    bbox: dict | None = None
    depthMap: str | None = None
    interactive: bool | None = None


class Bubble(Model):
    id: str
    text: str
    speakerId: str | None = None
    kind: Literal["speech", "thought", "shout", "caption"] = "speech"
    position: Vec2
    anchor: Vec2 | None = None
    anchorLayer: str | None = None
    audio: str | None = None
    startOffset: float | None = None
    durationHint: float | None = None


class StripPlacement(Model):
    y: int
    h: int
    gutterAfter: int = 0


class Panel(Model):
    id: str
    index: int
    renderMode: Literal["panel", "panorama", "scene3d"] = "panel"
    size: Size
    depthScale: float | None = None
    strip: StripPlacement | None = None
    durationOverride: float | None = None
    mood: str | None = None
    layers: list[Layer]
    bubbles: list[Bubble] = Field(default_factory=list)
    animations: list[dict] = Field(default_factory=list)
    ambience: str | None = None
    musicCue: dict | None = None
    panorama: str | None = None
    scene: str | None = None


class Manifest(Model):
    formatVersion: str
    generator: str
    createdAt: str
    series: Series
    episode: Episode
    cast: list[CastMember] = Field(default_factory=list)
    panels: list[Panel]

    def to_json(self) -> str:
        return self.model_dump_json(indent=2, exclude_none=True)
