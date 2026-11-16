using System;
using System.Collections.Generic;
using UnityEngine;
using Zumi.Format;
using static System.FormattableString;

namespace Zumi
{
    /// <summary>
    /// What a panel's scene shows at a time on the episode clock: each balloon from its bubble's startTime, each
    /// frame greyed until the clock reaches it, and the pipeline's accents (the panel's animation tracks). Show(t)
    /// states all of it from t alone, so a pause holds it and a seek lands on what straight play would show.
    /// </summary>
    public sealed class ZumiPanelStage
    {
        /// <summary>Seconds a balloon takes to appear. Its alpha only: lettering is never moved or scaled.</summary>
        public const float BalloonFadeSeconds = 0.12f;
        /// <summary>Seconds a frame takes from grey to its colours when the clock reaches it.</summary>
        public const float FrameFadeSeconds = 0.12f;
        /// <summary>What a frame ahead of the clock is multiplied by (the browser viewer's #282828).</summary>
        public static readonly Color AheadTint = new(40f / 255f, 40f / 255f, 40f / 255f, 1f);

        sealed class Track
        {
            public Format.Animation animation;
            public double start;
            public readonly List<ZumiPanelScene.Node> targets = new();
            /// <summary>scale: the fixed point as the camera sees it, at distance 1 (x to the scene's +x, y up).</summary>
            public Vector2 pivot;
            public Dictionary<string, string> pin;
            public float amplitude, frequency, decay;
            public bool vertical;
            public bool active;
            /// <summary>The furthest the target got from rest while the track ran: scale - 1, or the offset as a
            /// share of the panel's width. Read back from the transforms.</summary>
            public float peak;
        }

        readonly ZumiPanelScene scene;
        readonly string panelId;
        readonly double panelStart;
        readonly Dictionary<string, double> bubbleStart = new();
        readonly Dictionary<int, double> frameStart = new();
        readonly List<Track> tracks = new();
        readonly HashSet<ZumiPanelScene.Node> moved = new();
        readonly List<string> visibleBubbles = new(), frameStates = new(), activeTracks = new(), finishedTracks = new();

        /// <summary>The bubbles whose balloon is drawn now, at any alpha above 0.</summary>
        public IReadOnlyList<string> VisibleBubbleIds => visibleBubbles;
        /// <summary>Each timed frame as "n:lit" or "n:ahead" (ahead: drawn grey).</summary>
        public IReadOnlyList<string> FrameStates => frameStates;
        public IReadOnlyList<string> ActiveTrackIds => activeTracks;
        /// <summary>The tracks whose time has passed; their targets are at rest.</summary>
        public IReadOnlyList<string> FinishedTrackIds => finishedTracks;
        /// <summary>Called when a track that ran reaches its end: its id, what it moved, how far, and how far from
        /// rest its targets are left (0 is exactly at rest).</summary>
        public Action<string> TrackEnded;

        public ZumiPanelStage(ZumiPanelScene scene, Panel panel, double panelStart)
        {
            this.scene = scene;
            this.panelStart = panelStart;
            panelId = panel.id;
            foreach (var b in panel.bubbles) bubbleStart[b.id] = b.startTime ?? panelStart + b.startOffset;
            foreach (var f in panel.frames) frameStart[f.index] = panelStart + f.startOffset;
            foreach (var a in panel.animations)
            {
                if (a.track != AnimationTrack.scale && a.track != AnimationTrack.shake)
                {
                    Debug.LogWarning($"[Zumi] motion: {panelId}/{a.id}: {a.track} tracks are not played (the pipeline writes scale and shake)");
                    continue;
                }
                var track = new Track { animation = a, start = a.startTime ?? panelStart + a.delay };
                var wholeFrame = a.TryFrameTarget(out var frame);
                foreach (var node in scene.Nodes)
                    if (wholeFrame ? node.frame == frame && node.kind != "window" : node.card == a.target) track.targets.Add(node);
                if (track.targets.Count == 0)
                {
                    Debug.LogWarning($"[Zumi] motion: {panelId}/{a.id}: nothing in the scene is {a.target}");
                    continue;
                }
                // the targets' box as the camera sees it: every corner brought to distance 1
                float x0 = float.MaxValue, x1 = float.MinValue, y0 = float.MaxValue, y1 = float.MinValue;
                foreach (var node in track.targets)
                {
                    var d = Mathf.Max(node.Depth, 1e-4f);
                    x0 = Mathf.Min(x0, node.bounds.min.x / d);
                    x1 = Mathf.Max(x1, node.bounds.max.x / d);
                    y0 = Mathf.Min(y0, node.bounds.min.y / d);
                    y1 = Mathf.Max(y1, node.bounds.max.y / d);
                }
                // the panel's left is the scene's +x (glTFast mirrors x), its top +y
                var pivot = a.pivot ?? new Vec2 { x = 0.5f, y = 0.5f };
                track.pivot = new Vector2(Mathf.Lerp(x1, x0, pivot.x), Mathf.Lerp(y1, y0, pivot.y));
                track.amplitude = Number(a.@params, "amplitude", 0.01f);
                track.frequency = Number(a.@params, "frequency", 8f);
                track.decay = Number(a.@params, "decay", 0f);
                track.vertical = a.@params != null && a.@params.TryGetValue("axis", out var axis) && axis as string == "y";
                if (a.@params != null && a.@params.TryGetValue("pin", out var pin) && pin is Newtonsoft.Json.Linq.JObject pins)
                    track.pin = pins.ToObject<Dictionary<string, string>>();
                tracks.Add(track);
            }
        }

        /// <summary>Puts the scene in the state it has at t seconds on the episode clock.</summary>
        /// <param name="motion">False: no track plays and every layer rests.</param>
        /// <param name="greyAhead">False: every frame is in its colours from the panel's start.</param>
        public void Show(double t, bool motion, bool greyAhead)
        {
            visibleBubbles.Clear();
            frameStates.Clear();
            foreach (var f in frameStart)
                frameStates.Add(Invariant($"{f.Key}:{(greyAhead && t < f.Value ? "ahead" : "lit")}"));
            foreach (var node in scene.Nodes)
            {
                if (node.kind == "window") continue;
                if (node.kind == "lettering")
                {
                    var alpha = node.bubble != null && bubbleStart.TryGetValue(node.bubble, out var from)
                        ? Mathf.Clamp01((float)(t - from) / BalloonFadeSeconds) : 1f;
                    scene.SetTint(node, new Color(1f, 1f, 1f, alpha));
                    if (alpha > 0f && node.bubble != null && !visibleBubbles.Contains(node.bubble)) visibleBubbles.Add(node.bubble);
                }
                // a frame that starts with its panel is never grey: only the ones the clock still has to reach
                else if (node.frame.HasValue && frameStart.TryGetValue(node.frame.Value, out var reached))
                    scene.SetTint(node, greyAhead && reached > panelStart
                        ? Color.Lerp(AheadTint, Color.white, Mathf.Clamp01((float)(t - reached) / FrameFadeSeconds)) : Color.white);
            }

            // rest first: a track adds to it, and one that is over or ahead leaves it
            foreach (var node in moved)
            {
                node.transform.localPosition = Vector3.zero;
                node.transform.localScale = Vector3.one;
            }
            moved.Clear();
            activeTracks.Clear();
            finishedTracks.Clear();
            foreach (var track in tracks)
            {
                var a = track.animation;
                var d = t - track.start;
                var duration = Math.Max(a.duration, 1e-6f);
                if (a.loop && d >= 0d) d %= duration;
                var active = motion && d >= 0d && d < duration;
                if (!active && d >= duration) finishedTracks.Add(a.id);
                if (active)
                {
                    activeTracks.Add(a.id);
                    if (!track.active) track.peak = 0f;
                    Play(track, (float)d, (float)(d / duration));
                }
                else if (track.active)
                {
                    var off = 0f;
                    foreach (var node in track.targets)
                        off = Mathf.Max(off, node.transform.localPosition.magnitude + (node.transform.localScale - Vector3.one).magnitude);
                    TrackEnded?.Invoke(Invariant($"{panelId}/{a.id} {a.track} on {a.target} ({track.targets.Count} nodes) peak {track.peak:F4} rest {off:G3}"));
                }
                track.active = active;
            }
        }

        void Play(Track track, float seconds, float u)
        {
            var a = track.animation;
            if (a.track == AnimationTrack.scale)
            {
                var k = Value(a, u);
                foreach (var node in track.targets)
                {
                    // about the pivot, in the panel's plane: the layer keeps its depth
                    var pivot = track.pivot * node.Depth;
                    node.transform.localPosition += new Vector3(pivot.x, pivot.y, 0f) * (1f - k);
                    node.transform.localScale = Vector3.Scale(node.transform.localScale, new Vector3(k, k, 1f));
                    moved.Add(node);
                    track.peak = Mathf.Max(track.peak, Mathf.Abs(node.transform.localScale.x - 1f));
                }
                return;
            }
            // shake: positive to the panel's right (the scene's -x) or down, a share of the panel's width
            var offset = track.amplitude * Mathf.Pow(1f - u, track.decay) * Mathf.Sin(2f * Mathf.PI * track.frequency * seconds);
            foreach (var node in track.targets)
            {
                var own = offset;
                if (track.pin != null && node.card != null && track.pin.TryGetValue(node.card, out var side))
                    own = side == "l" ? Mathf.Min(own, 0f) : side == "r" ? Mathf.Max(own, 0f) : 0f;
                // the same shift on the panel for every layer: a deeper one moves further to cover it
                var metres = own * scene.PanelSize.x * node.Depth;
                node.transform.localPosition -= track.vertical ? new Vector3(0f, metres, 0f) : new Vector3(metres, 0f, 0f);
                moved.Add(node);
                track.peak = Mathf.Max(track.peak, Mathf.Abs(own));
            }
        }

        // the value at u of the way through the track: each segment between two keyframes eased on its own
        static float Value(Format.Animation a, float u)
        {
            var keys = a.keyframes;
            if (keys == null || keys.Count == 0) return 1f;
            if (u <= keys[0].t) return keys[0].Scalar;
            for (var i = 1; i < keys.Count; i++)
            {
                if (u > keys[i].t) continue;
                float from = keys[i - 1].Scalar, to = keys[i].Scalar;
                var v = (u - keys[i - 1].t) / Mathf.Max(keys[i].t - keys[i - 1].t, 1e-6f);
                var eased = a.easing switch
                {
                    Easing.step => u < keys[i].t ? 0f : 1f,
                    Easing.linear => v,
                    Easing.@in => v * v * v,
                    Easing.@out => 1f - Mathf.Pow(1f - v, 3f),
                    _ => v < 0.5f ? 4f * v * v * v : 1f - Mathf.Pow(2f - 2f * v, 3f) / 2f,
                };
                return from + (to - from) * eased;
            }
            return keys[^1].Scalar;
        }

        static float Number(Dictionary<string, object> values, string key, float fallback) =>
            values != null && values.TryGetValue(key, out var v) && v != null ? Convert.ToSingle(v, System.Globalization.CultureInfo.InvariantCulture) : fallback;

        /// <summary>The middle of a card of this scene, in world space.</summary>
        public bool TryCardCentre(string card, out Vector3 world)
        {
            foreach (var node in scene.Nodes)
                if (node.card == card)
                {
                    world = scene.Root.TransformPoint(node.bounds.center);
                    return true;
                }
            world = default;
            return false;
        }
    }
}
