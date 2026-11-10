// Zumi episode manifest, format 1.0.0. Hand-kept mirror of schema/zumi.schema.json.
// Deserialise with Newtonsoft.Json (com.unity.nuget.newtonsoft-json) or System.Text.Json.
// Paths are relative to the .zumi zip root; every panel's assets live under panels/<panelId>/.
// Normalised coordinates are 0..1, origin top-left.
using System;
using System.Collections.Generic;

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

    [Serializable]
    public sealed class PlaceMesh
    {
        /// <summary>EpisodeInfo.settings[].id.</summary>
        public string setting;
        /// <summary>episode/places/&lt;setting&gt;/front.glb: eye at the origin, the view's centre down -z, y up.</summary>
        public string front;
        /// <summary>The surface behind the front's near objects, seen through its gaps.</summary>
        public string back;
        public float hDeg;
        public float vDeg;
        /// <summary>How the place lights the reader's room while it is open; null in hand-made files.</summary>
        public PlaceLight light;
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

    [Serializable]
    public sealed class PlaceKeyLight
    {
        /// <summary>Degrees from straight ahead (the key wall), positive to the right.</summary>
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
    }

    [Serializable]
    public sealed class Score
    {
        /// <summary>music[].id -> knots [seconds, gain] in time order; linear between knots, 0 outside them.</summary>
        public Dictionary<string, List<List<float>>> envelope = new();
        /// <summary>How the music sits in the room over time: "point" = from a point inside the place behind the key
        /// wall (music heard in the scene), "wide" = spread across the open walls (lead, underscore).</summary>
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
        public string file;
        public bool loop = true;
        public float gain = 0.6f;
        public float? loopStart;
        public float? loopEnd;
        public string mood;
        public string setting;
        public float? duration;
    }

    public enum MusicTransition { crossfade, fadeOutIn, cut }

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
    public enum BubbleKind { speech, thought, shout, caption }
    public enum AnimationTrack { translate, rotate, scale, opacity, sway, shake, spriteCycle }
    public enum Easing { linear, inOut, @out, @in }
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
        public List<Layer> layers = new();
        public List<Bubble> bubbles = new();
        public List<Animation> animations = new();
        public string ambience;
        public MusicCue musicCue;
        public string panorama;
        public string scene;
        public List<Interaction> interactions = new();
    }

    [Serializable]
    public sealed class FrameTiming
    {
        /// <summary>The frame's index in the panel's scene (the layers' frame).</summary>
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
        public string speakerId;
        public BubbleKind kind = BubbleKind.speech;
        public Vec2 position;
        public Vec2? anchor;
        public string anchorLayer;
        public string audio;
        public float startOffset;
        public float durationHint;
        /// <summary>Seconds from the episode's start when the bubble appears and its clip plays, and when it is
        /// over, precomputed by the pipeline (panel startTime + startOffset). Null in hand-made files.</summary>
        public float? startTime;
        public float? endTime;
    }

    [Serializable]
    public sealed class Keyframe
    {
        public float t;
        /// <summary>Scalar for rotate/scale/opacity.</summary>
        public float? value;
        /// <summary>Vector for translate.</summary>
        public Vec2? vector;
    }

    [Serializable]
    public sealed class Animation
    {
        public string id;
        public string target;
        public AnimationTrack track;
        public float duration = 2f;
        public float delay;
        public bool loop = true;
        public Easing easing = Easing.inOut;
        public List<Keyframe> keyframes = new();
        public Dictionary<string, object> @params = new();
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
