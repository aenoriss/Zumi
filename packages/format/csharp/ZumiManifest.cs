// Zumi episode manifest, format 1.0.0. Hand-kept mirror of schema/zumi.schema.json.
// Deserialise with Newtonsoft.Json (com.unity.nuget.newtonsoft-json) or System.Text.Json.
// Paths are relative to the .zumi zip root. Normalised coordinates are 0..1, origin top-left.
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
        public string music;
        public float durationHint;
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
        public float? durationOverride;
        public string mood;
        public List<Layer> layers = new();
        public List<Bubble> bubbles = new();
        public List<Animation> animations = new();
        public string ambience;
        public string panorama;
        public string scene;
        public List<Interaction> interactions = new();
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
