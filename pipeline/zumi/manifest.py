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
    setting: str | None = None
    duration: float | None = None


class Setting(Model):
    id: str
    name: str
    description: str | None = None
    indoor: bool | None = None
    timeOfDay: str | None = None
    weather: str | None = None


class Span(Model):
    from_: str = Field(alias="from")
    to: str
    setting: str | None = None
    mood: Literal["light", "tense", "grave", "epic", "tender"]
    role: Literal["lead", "under", "source", "out"]
    colour: str | None = None


class Placement(Model):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    mode: Literal["point", "wide"]


class Score(Model):
    envelope: dict[str, list[list[float]]]  # track id -> [[seconds, gain], ...]
    placement: list[Placement] = Field(default_factory=list)
    spans: list[Span] = Field(default_factory=list)


HEX = r"^#[0-9a-f]{6}$"


class Ambient(Model):
    sky: str = Field(pattern=HEX)
    horizon: str = Field(pattern=HEX)
    ground: str = Field(pattern=HEX)


class KeyLight(Model):
    yaw: float
    pitch: float
    color: str = Field(pattern=HEX)
    strength: float = Field(ge=0, le=1)


class RoomGrade(Model):
    brightness: float = Field(ge=-1, le=1)
    tint: str = Field(pattern=HEX)
    tintStrength: float = Field(ge=0, le=1)


class PlaceLight(Model):
    ambient: Ambient
    key: KeyLight
    room: RoomGrade
    occlusion: float = Field(ge=0, le=1)


class PlaceMesh(Model):
    setting: str
    front: str = Field(pattern=r"^episode/places/[a-z0-9_-]+/front\.glb$")
    back: str = Field(pattern=r"^episode/places/[a-z0-9_-]+/back\.glb$")
    hDeg: float = Field(gt=0)
    vDeg: float = Field(gt=0)
    light: PlaceLight | None = None


class PlaceShow(Model):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    setting: str


class Places(Model):
    fade: float = Field(1.0, ge=0)
    meshes: list[PlaceMesh]
    timeline: list[PlaceShow]


class Episode(Model):
    id: str
    index: int
    title: str
    summary: str | None = None
    thumbnail: str | None = None
    music: list[MusicTrack] = Field(default_factory=list)
    durationHint: float | None = None
    layout: Layout | None = None
    settings: list[Setting] = Field(default_factory=list)
    places: Places | None = None
    score: Score | None = None


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
    startTime: float | None = None  # from the episode's start, precomputed
    endTime: float | None = None


class FrameTiming(Model):
    index: int
    startOffset: float
    duration: float
    setting: str | None = None


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
    startTime: float | None = None  # from the episode's start, precomputed
    endTime: float | None = None
    frames: list[FrameTiming] = Field(default_factory=list)  # the comic frames inside the panel, when each is reached
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
        return self.model_dump_json(indent=2, exclude_none=True, by_alias=True)
