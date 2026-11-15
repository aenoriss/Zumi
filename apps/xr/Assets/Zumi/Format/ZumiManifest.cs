// Zumi episode manifest, format 1.1.0. Hand-kept mirror of packages/format/schema/zumi.schema.json, which is the
// source of truth: every rule a field follows is stated there. This file is kept identical in two places,
// packages/format/csharp/ and apps/xr/Assets/Zumi/Format/.
// Deserialise with Newtonsoft.Json (com.unity.nuget.newtonsoft-json).
// Paths are relative to the .zumi zip root; every panel's assets live under panels/<panelId>/.
// Normalised coordinates are 0..1, origin top-left.
using System;
using System.Collections.Generic;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Zumi.Format
{
    [Serializable]
    public sealed class ZumiManifest
    {
        public string formatVersion;
        public string generator;
        public string createdAt;
        public SeriesInfo series;
        public EpisodeInfo episode;
        /// <summary>Everyone a character card of the episode is, speaking or not.</summary>
        public List<CastMember> cast = new();
        public List<Panel> panels = new();
    }

    [Serializable]
    public sealed class SeriesInfo
    {
        public string id;
        public string title;
        public string creator;
        public string language = "en";
        public string cover;
        public StyleInfo style;
    }

    [Serializable]
    public sealed class StyleInfo
    {
        public string preset;
        public string prompt;
        public List<string> references = new();
    }

    [Serializable]
    public sealed class EpisodeInfo
    {
        public string id;
        public int index;
        public string title;
        public string summary;
        public string thumbnail;
        public List<MusicTrack> music = new();
        public float durationHint;
        /// <summary>Null means carousel.</summary>
        public Layout layout;
        /// <summary>The places the episode is drawn in; a frame names its setting (FrameTiming.setting).</summary>
        public List<Setting> settings = new();
        /// <summary>Settings' surroundings shown through the walls, and which one shows when. Null: none.</summary>
        public Places places;
        /// <summary>The music resolved by the pipeline: per-track gain envelopes a reader interpolates. When present,
        /// follow it and ignore musicCue.</summary>
        public Score score;
    }

    [Serializable]
    public sealed class Setting
    {
        public string id;
        public string name;
        public string description;
        public bool? indoor;
        public string timeOfDay;
        public string weather;
    }

    [Serializable]
    public sealed class Places
    {
        /// <summary>Seconds of each half of a swap: the open place fades out, then the next fades in.</summary>
        public float fade = 1f;
        public List<PlaceMesh> meshes = new();
        /// <summary>In time order on the episode clock; no place outside it.</summary>
        public List<PlaceShow> timeline = new();
    }

    /// <summary>One place. Its frame (glTF's): the seat's eye at the origin, +y up, the view's centre down -z, +x right;
    /// both meshes unlit, in the depth model's metres. The reader puts the origin at the seat's eye, turns -z to the
    /// key wall and scales both meshes by one factor about the origin so the place lies beyond the wall: with a wall D
    /// metres ahead, (D + 0.25) / nearM (the schema states the full rule).</summary>
    [Serializable]
    public sealed class PlaceMesh
    {
        /// <summary>EpisodeInfo.settings[].id.</summary>
        public string setting;
        /// <summary>episode/places/&lt;setting&gt;/front.glb: the view as a mesh, cut at depth edges.</summary>
        public string front;
        /// <summary>The surface behind the front's near objects, seen through its gaps.</summary>
        public string back;
        public float hDeg;
        public float vDeg;
        /// <summary>The 5th percentile, the median and the 95th percentile of the distance from the eye over the view,
        /// in the meshes' units. Null in files before 1.1.</summary>
        public float? nearM;
        public float? medianM;
        public float? farM;
        /// <summary>How the place lights the reader's room while it is open; null in hand-made files.</summary>
        public PlaceLight light;
        /// <summary>Objects of the place that stand in the room while it is open. No positions: the reader places them.</summary>
        public List<PlaceProp> props = new();
    }

    public enum PropSurface { floor, table, shelf }

    /// <summary>A prop's model: one mesh, +y up, centred on the origin inside a unit cube (not resting on it), the side
    /// the place's view shows toward +z. Scale by heightM / (bounds.max[1] - bounds.min[1]) and rest the point under
    /// its middle on the surface. Lit PBR, non-metal, single-sided, no normals (compute them, draw both sides).</summary>
    [Serializable]
    public sealed class PlaceProp
    {
        public string name;
        public string description;
        /// <summary>episode/places/&lt;setting&gt;/props/&lt;name&gt;.glb.</summary>
        public string model;
        /// <summary>Its real height in metres.</summary>
        public float heightM;
        public PropSurface surface;
        /// <summary>The model's bounding box in its own units; null in hand-made files.</summary>
        public PropBounds bounds;
    }

    [Serializable]
    public sealed class PropBounds
    {
        /// <summary>[x, y, z].</summary>
        public float[] min;
        public float[] max;
    }

    /// <summary>Measured from the place's painted view. Colours are sRGB hex light colours (brightest channel full).
    /// Unity: ambient -> RenderSettings trilight (sky, equator, ground); key -> one directional light; room ->
    /// OVRPassthroughLayer brightness and colour map; occlusion -> the props' contact shadows. Blend over places.fade.</summary>
    [Serializable]
    public sealed class PlaceLight
    {
        public PlaceAmbient ambient;
        public PlaceKeyLight key;
        public RoomGrade room;
        public float occlusion;
    }

    [Serializable]
    public sealed class PlaceAmbient
    {
        public string sky;
        public string horizon;
        public string ground;
    }

    /// <summary>yaw and pitch are the direction from the seat toward the light, in the place's frame; the light shines
    /// back along it.</summary>
    [Serializable]
    public sealed class PlaceKeyLight
    {
        /// <summary>Degrees about +y from the place's -z (once placed: from the seat to the key wall), positive toward
        /// +x, the right of a reader facing the key wall.</summary>
        public float yaw;
        /// <summary>Degrees above the horizon.</summary>
        public float pitch;
        public string color;
        /// <summary>0 for an evenly lit place, 1 for a lamp in the dark.</summary>
        public float strength;
    }

    [Serializable]
    public sealed class RoomGrade
    {
        /// <summary>Change of the real room's brightness: -0.4 is 40 % darker.</summary>
        public float brightness;
        public string tint;
        public float tintStrength;
    }

    [Serializable]
    public sealed class PlaceShow
    {
        public float start;
        public float end;
        public string setting;
    }

    [Serializable]
    public sealed class MusicPlacement
    {
        public float start;
        public float end;
        /// <summary>"point" or "wide".</summary>
        public string mode;
        /// <summary>point only: the point's direction from the seat, as PlaceKeyLight.yaw and pitch.</summary>
        public float? yaw;
        public float? pitch;
    }

    [Serializable]
    public sealed class Score
    {
        /// <summary>A gain at or under this is silence: the track is not playing.</summary>
        public const float Silent = 0.001f;

        /// <summary>music[].id -> knots [seconds, gain] in time order; linear between knots, 0 outside them. Final: the
        /// ducking under voices, the fades and the place's opening are already in it. Never duck again.</summary>
        public Dictionary<string, List<List<float>>> envelope = new();
        /// <summary>How the music sits in the room over time: "point" = from a point inside the place (music heard in
        /// the scene), "wide" = spread across the open walls (lead, underscore); wide outside every entry.</summary>
        public List<MusicPlacement> placement = new();
        public List<Span> spans = new();

        /// <summary>A track's gain at t seconds on the episode clock.</summary>
        public static float GainAt(List<List<float>> knots, float t)
        {
            if (knots == null || knots.Count == 0 || t < knots[0][0] || t > knots[knots.Count - 1][0]) return 0f;
            for (int i = 1; i < knots.Count; i++)
                if (t <= knots[i][0])
                {
                    float t0 = knots[i - 1][0], t1 = knots[i][0];
                    float u = t1 > t0 ? (t - t0) / (t1 - t0) : 1f;
                    return knots[i - 1][1] + (knots[i][1] - knots[i - 1][1]) * u;
                }
            return knots[knots.Count - 1][1];
        }

        /// <summary>Where in its file a track plays at t seconds on the episode clock: (t - origin) modulo the file's
        /// duration, the origin being the start of the audible span t lies in (the last knot at or before t that is
        /// silent and followed by a sounding one; the first knot when there is none).</summary>
        public static float PositionAt(List<List<float>> knots, float t, float duration)
        {
            if (knots == null || knots.Count == 0 || duration <= 0f) return 0f;
            float origin = knots[0][0];
            for (int i = 0; i + 1 < knots.Count && knots[i][0] <= t; i++)
                if (knots[i][1] <= Silent && knots[i + 1][1] > Silent) origin = knots[i][0];
            float at = (t - origin) % duration;
            return at < 0f ? at + duration : at;
        }
    }

    [Serializable]
    public sealed class Span
    {
        /// <summary>p&lt;panel&gt;/b&lt;bubble&gt; or p&lt;panel&gt;/f&lt;frame&gt;.</summary>
        public string from;
        public string to;
        public string setting;
        public string mood;
        public string role;
        public string colour;
    }

    public enum LayoutMode { scroll, carousel }

    [Serializable]
    public sealed class Layout
    {
        public LayoutMode mode = LayoutMode.carousel;
        /// <summary>Strip width in source pixels (WEBTOON 800, Naver 700).</summary>
        public int width;
        /// <summary>Total strip height in source pixels, gutters included.</summary>
        public int height;
        /// <summary>Gutter and margin colour measured from the strip edges.</summary>
        public string background;
    }

    /// <summary>Panel position on the original strip, in source pixels. Present for scroll layouts.</summary>
    [Serializable]
    public sealed class StripPlacement
    {
        public int y;
        public int h;
        public int gutterAfter;
    }

    [Serializable]
    public sealed class MusicTrack
    {
        public string id;
        /// <summary>episode/music/&lt;id&gt;.wav in pipeline-made files (PCM: the file is a seamless loop body).</summary>
        public string file;
        public bool loop = true;
        /// <summary>Only for files without a score; with one the envelope is the level.</summary>
        public float gain = 0.6f;
        public float? loopStart;
        public float? loopEnd;
        public string mood;
        public string setting;
        /// <summary>Seconds of audio in the file: the modulus of Score.PositionAt.</summary>
        public float? duration;
    }

    public enum MusicTransition { crossfade, fadeOutIn, cut }

    /// <summary>Hand-made files only; ignored when the episode has a score.</summary>
    [Serializable]
    public sealed class MusicCue
    {
        /// <summary>episode.music[].id, or "none" to fade the music out.</summary>
        public string track;
        public MusicTransition transition = MusicTransition.crossfade;
        public float seconds = 2.5f;
        public float startAt;
        /// <summary>Seconds after the panel appears before the cue fires.</summary>
        public float at;
    }

    [Serializable]
    public sealed class CastMember
    {
        public string id;
        public string name;
        /// <summary>Null for a member who does not speak in this episode.</summary>
        public VoiceInfo voice;
        public string color;
    }

    [Serializable]
    public sealed class VoiceInfo
    {
        public string engine;
        public string voiceId;
        public string description;
    }

    public enum RenderMode { panel, panorama, scene3d }
    public enum DepthBand { background, mid, foreground }
    /// <summary>sfx: a sound no character voices, lettered on the art; never has audio or a speaker.</summary>
    public enum BubbleKind { speech, thought, shout, caption, sfx }
    public enum AnimationTrack { translate, rotate, scale, opacity, sway, shake, spriteCycle }
    /// <summary>Applied to each segment between two keyframes, on its share v of the way: linear v; @in v^3; @out
    /// 1 - (1 - v)^3; inOut 4v^3 below a half, else 1 - (2 - 2v)^3 / 2; step holds the earlier keyframe's value until
    /// the later one's time (a cut).</summary>
    public enum Easing { linear, inOut, @out, @in, step }
    public enum Trigger { gaze, pinch, proximity, time }
    public enum InteractionAction { wiggle, playSound, revealLayer, revealBubble, nextPanel, enterScene, playAnimation }

    [Serializable]
    public struct Vec2 { public float x; public float y; }

    [Serializable]
    public struct BBox { public float x; public float y; public float w; public float h; }

    [Serializable]
    public struct Size { public int w; public int h; }

    [Serializable]
    public sealed class Panel
    {
        public string id;
        public int index;
        public RenderMode renderMode = RenderMode.panel;
        public Size size;
        public float depthScale = 0.6f;
        public StripPlacement strip;
        public float? durationOverride;
        /// <summary>Seconds from the episode's start when this panel is active, precomputed by the pipeline:
        /// the panel holding the episode clock in [startTime, endTime) is the active one. Null in hand-made files.</summary>
        public float? startTime;
        public float? endTime;
        /// <summary>The comic frames inside the panel in reading order and when each is reached, precomputed:
        /// a reader greys the frames ahead of the clock. Empty in hand-made files.</summary>
        public List<FrameTiming> frames = new();
        public string mood;
        /// <summary>A pipeline-made scene3d panel still carries its flat source image as layer "base", the fallback.</summary>
        public List<Layer> layers = new();
        /// <summary>In the order they appear on the clock.</summary>
        public List<Bubble> bubbles = new();
        /// <summary>The pipeline's accents (pop, cut, impact), each one track that plays once.</summary>
        public List<Animation> animations = new();
        public string ambience;
        public MusicCue musicCue;
        public string panorama;
        /// <summary>panels/&lt;id&gt;/scene.glb: every node but the camera is one layer and carries NodeExtras.</summary>
        public string scene;
        public List<Interaction> interactions = new();
    }

    /// <summary>The glTF extras of a node of a panel's scene.glb (deserialise the node's extras into it).</summary>
    [Serializable]
    public sealed class NodeExtras
    {
        /// <summary>window, backdrop, character, object or lettering.</summary>
        public string kind;
        /// <summary>The frame whose window shows the node (FrameTiming.index); the window's own frame; null for lettering.</summary>
        public int? frame;
        /// <summary>The layer's id in its panel ("card-3"): what Bubble.speakerCard and Animation.target name. Null for windows.</summary>
        public string card;
        /// <summary>A character that is a cast member: CastMember.id.</summary>
        public string cast;
        /// <summary>Lettering: the Bubble.id it draws; shown from that bubble's startTime.</summary>
        public string bubble;
    }

    [Serializable]
    public sealed class FrameTiming
    {
        /// <summary>The frame's index in the panel's scene (NodeExtras.frame, Bubble.frame).</summary>
        public int index;
        /// <summary>Seconds after the panel appears.</summary>
        public float startOffset;
        public float duration;
        /// <summary>episode.settings[].id the frame is drawn in; null for a frame with no place.</summary>
        public string setting;
    }

    [Serializable]
    public sealed class Layer
    {
        public string id;
        public string name;
        public string image;
        public float depth;
        public DepthBand band;
        public BBox? bbox;
        public string depthMap;
        public bool interactive;
    }

    [Serializable]
    public sealed class Bubble
    {
        public string id;
        public string text;
        /// <summary>CastMember.id of who says it; null when nobody the cast knows does.</summary>
        public string speakerId;
        /// <summary>The card that says it: a NodeExtras.card of this panel's scene ("card-3"), or
        /// "&lt;panelId&gt;/&lt;card&gt;" for a card drawn in another panel. Null with a speakerId: off-panel.</summary>
        public string speakerCard;
        /// <summary>The frame it belongs to and is timed in (FrameTiming.index); null in a panel without frames.</summary>
        public int? frame;
        public BubbleKind kind = BubbleKind.speech;
        public Vec2 position;
        public Vec2? anchor;
        public string anchorLayer;
        /// <summary>panels/&lt;id&gt;/voice/&lt;bubble&gt;.wav: 24 kHz mono 16-bit PCM, a 44-byte header, nothing after the
        /// samples. Null: the bubble is shown for its durationHint as text only.</summary>
        public string audio;
        public float startOffset;
        public float durationHint;
        /// <summary>Seconds from the episode's start when the bubble appears and its clip plays, and when it is
        /// over, precomputed by the pipeline (panel startTime + startOffset). Null in hand-made files.</summary>
        public float? startTime;
        public float? endTime;

        /// <summary>speakerCard split: the panel the card is in (this panel's id when it names none) and the card.</summary>
        public bool TrySpeakerCard(string ownPanel, out string panel, out string card)
        {
            panel = card = null;
            if (string.IsNullOrEmpty(speakerCard)) return false;
            int slash = speakerCard.IndexOf('/');
            panel = slash < 0 ? ownPanel : speakerCard.Substring(0, slash);
            card = speakerCard.Substring(slash + 1);
            return true;
        }
    }

    [Serializable]
    public sealed class Keyframe
    {
        /// <summary>0..1 of the track's duration.</summary>
        public float t;
        /// <summary>A number (rotate, scale, opacity) or {x, y} (translate).</summary>
        public JToken v;

        [JsonIgnore] public float Scalar => v != null && v.Type != JTokenType.Object ? v.Value<float>() : 0f;
        [JsonIgnore] public Vec2 Vector => v != null && v.Type == JTokenType.Object
            ? new Vec2 { x = v.Value<float>("x"), y = v.Value<float>("y") } : default;
    }

    /// <summary>One track on one target, from startTime on the episode clock (or delay after its panel appears) for
    /// duration seconds. A track with loop false leaves its target at rest after its end.</summary>
    [Serializable]
    public sealed class Animation
    {
        public string id;
        /// <summary>A layer id (flat panels); in a scene: a NodeExtras.card, or "frame:&lt;n&gt;" for the content of
        /// frame n (every node of that frame but its window, moved together behind the window).</summary>
        public string target;
        public AnimationTrack track;
        /// <summary>Seconds from the episode's start; null in hand-made files (use the panel's start + delay).</summary>
        public float? startTime;
        public float duration = 2f;
        public float delay;
        public bool loop = true;
        public Easing easing = Easing.inOut;
        /// <summary>rotate and scale: the fixed point in the target's own bounding box as the panel camera sees it
        /// (0,0 top-left, 1,1 bottom-right); null is the centre.</summary>
        public Vec2? pivot;
        public List<Keyframe> keyframes = new();
        /// <summary>shake: amplitude (a share of the panel's width), frequency (Hz), axis ("x"), decay (the exponent
        /// of (1 - u) the amplitude dies out by), pin ({card: "l" | "r" | "lr"}: a card that takes only the offsets
        /// toward the side it touches).</summary>
        public Dictionary<string, object> @params = new();

        /// <summary>Whether the target is a frame's content, and which frame.</summary>
        public bool TryFrameTarget(out int frame)
        {
            frame = -1;
            return target != null && target.StartsWith("frame:") && int.TryParse(target.Substring(6), out frame);
        }
    }

    [Serializable]
    public sealed class Interaction
    {
        public string id;
        public string target;
        public Trigger trigger;
        public InteractionAction action;
        public Dictionary<string, object> @params = new();
    }

    /// <summary>Pacing rule shared with the pipeline: never diverge from schema/zumi.schema.json's description.</summary>
    public static class Pacing
    {
        public const float SecondsPerBubble = 1.5f;
        public const float MinPanelSeconds = 3f;
        public const float MinImmersiveSeconds = 20f;

        public static float Duration(Panel p, Func<string, float> audioSeconds)
        {
            if (p.startTime.HasValue && p.endTime.HasValue) return p.endTime.Value - p.startTime.Value;
            if (p.durationOverride.HasValue) return p.durationOverride.Value;
            float voices = 0f;
            foreach (var b in p.bubbles) if (!string.IsNullOrEmpty(b.audio)) voices += audioSeconds(b.audio);
            float d = voices + SecondsPerBubble * p.bubbles.Count;
            float floor = p.renderMode == RenderMode.panel ? MinPanelSeconds : MinImmersiveSeconds;
            if (d < floor) d = floor;
            foreach (var a in p.animations) if (!a.loop && a.delay + a.duration > d) d = a.delay + a.duration;
            return d;
        }
    }
}
