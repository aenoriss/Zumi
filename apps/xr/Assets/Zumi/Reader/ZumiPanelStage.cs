using System;
using System.Collections.Generic;
using UnityEngine;
using Zumi.Format;
using static System.FormattableString;

namespace Zumi
{
    /// <summary>
    /// What a panel's scene shows at a time on the episode clock, as the browser viewer's play mode does: every balloon
    /// is there from the panel's start, greyed and blurred until its bubble's startTime (mid grey in a lit frame, near
    /// black in a frame still ahead), then in full and staying so; each frame greyed and blurred until the clock
    /// reaches it; and the pipeline's accents (the panel's animation tracks). A frame lights at the earliest of its own
    /// start, the first start of a balloon filed under it or drawn in it, and the first start of a balloon said by a
    /// card of this panel drawn in it, so a lit balloon never sits on a grey frame nor its speaker in one. Show(t) states
    /// all of it from t alone, so a pause holds it and a seek lands on what straight play would show.
    /// </summary>
    public sealed class ZumiPanelStage
    {
        /// <summary>Seconds a balloon takes from waiting to full. Its colour and blur only: lettering is never moved
        /// or scaled.</summary>
        public const float BalloonFadeSeconds = 0.16f;
        /// <summary>Seconds a frame takes from grey to its colours when the clock reaches it.</summary>
        public const float FrameFadeSeconds = 0.12f;
        /// <summary>What a frame ahead of the clock is multiplied by (the browser viewer's #282828).</summary>
        public static readonly Color AheadTint = new(40f / 255f, 40f / 255f, 40f / 255f, 1f);
        /// <summary>A balloon not yet read: in a lit frame (#707070), and in a frame still ahead (#101010).</summary>
        public static readonly Color WaitingTint = new(112f / 255f, 112f / 255f, 112f / 255f, 1f), WaitingAheadTint = new(16f / 255f, 16f / 255f, 16f / 255f, 1f);
        /// <summary>Blur in texels: anything ahead of the clock, and a balloon waiting in a lit frame (the viewer's
        /// 1.5 and 0.8 px at full size).</summary>
        public const float BlurAhead = 1.5f, BlurWaiting = 0.8f;

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
        /// <summary>Each lettering node's frame by where it is drawn: the window holding its middle (the smallest
        /// when several do), else the nearest, as the viewer's frameOfBubble.</summary>
        readonly Dictionary<ZumiPanelScene.Node, int> drawnIn = new();
        readonly List<Track> tracks = new();
        readonly HashSet<ZumiPanelScene.Node> moved = new();
        readonly List<string> visibleBubbles = new(), litBubbles = new(), frameStates = new(), activeTracks = new(), finishedTracks = new();

        /// <summary>The bubbles whose balloon is drawn now: all of the panel's, from its start.</summary>
        public IReadOnlyList<string> VisibleBubbleIds => visibleBubbles;
        /// <summary>The bubbles whose balloon is in full now (its startTime reached).</summary>
        public IReadOnlyList<string> LitBubbleIds => litBubbles;
        /// <summary>Frames that light before their own start because a balloon drawn in them starts earlier:
        /// "frame n at t (own start s, bubble b)".</summary>
        public readonly List<string> EarlyFrames = new();
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
            LightFramesByBalloons(panel);
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

        // A frame lights at the earliest of its own start and the first start of a balloon in it: the frame the
        // bubble names, the one it is drawn in (they differ where a balloon overlaps an inset frame), and the one its
        // speaking card is in
        void LightFramesByBalloons(Panel panel)
        {
            var windows = new List<(int frame, Rect seen)>();
            foreach (var node in scene.Nodes)
                if (node.kind == "window" && node.frame.HasValue) windows.Add((node.frame.Value, Seen(node)));
            foreach (var node in scene.Nodes)
            {
                if (node.kind != "lettering" || windows.Count == 0) continue;
                var c = Seen(node).center;
                int best = -1;
                var bestArea = float.MaxValue;
                var bestDistance = float.MaxValue;
                foreach (var (frame, seen) in windows)
                {
                    var d = Mathf.Max(seen.xMin - c.x, 0f, c.x - seen.xMax) + Mathf.Max(seen.yMin - c.y, 0f, c.y - seen.yMax);
                    var area = seen.width * seen.height;
                    if (d < bestDistance || (d == 0f && bestDistance == 0f && area < bestArea))
                    {
                        best = frame;
                        bestDistance = d;
                        bestArea = area;
                    }
                }
                drawnIn[node] = best;
            }

            void Earlier(int frame, string bubble)
            {
                if (!frameStart.TryGetValue(frame, out var own) || !bubbleStart.TryGetValue(bubble, out var said) || said >= own) return;
                frameStart[frame] = said;
                EarlyFrames.Add(Invariant($"frame {frame} at {said:F2} (own start {own:F2}, bubble {bubble})"));
            }
            foreach (var b in panel.bubbles)
                if (b.frame.HasValue) Earlier(b.frame.Value, b.id);
            foreach (var (node, frame) in drawnIn)
                if (node.bubble != null) Earlier(frame, node.bubble);
            // and the frame of the card that says it, when that card is in this panel (one in another panel, or a
            // speaker off the panel, lights nothing more)
            foreach (var b in panel.bubbles)
            {
                if (!b.TrySpeakerCard(panel.id, out var inPanel, out var card) || inPanel != panel.id) continue;
                foreach (var node in scene.Nodes)
                    if (node.card == card && node.frame.HasValue) Earlier(node.frame.Value, b.id);
            }
            foreach (var line in EarlyFrames) Debug.Log($"[Zumi] frames: {panelId} {line}");
        }

        // a node's box as the camera sees it, at distance 1
        static Rect Seen(ZumiPanelScene.Node node)
        {
            var d = Mathf.Max(node.Depth, 1e-4f);
            return Rect.MinMaxRect(node.bounds.min.x / d, node.bounds.min.y / d, node.bounds.max.x / d, node.bounds.max.y / d);
        }

        /// <summary>Puts the scene in the state it has at t seconds on the episode clock.</summary>
        /// <param name="motion">False: no track plays and every layer rests.</param>
        /// <param name="greyAhead">False: every frame is in its colours from the panel's start.</param>
        public void Show(double t, bool motion, bool greyAhead)
        {
            visibleBubbles.Clear();
            litBubbles.Clear();
            frameStates.Clear();
            foreach (var f in frameStart)
                frameStates.Add(Invariant($"{f.Key}:{(greyAhead && t < f.Value ? "ahead" : "lit")}"));
            foreach (var node in scene.Nodes)
            {
                if (node.kind == "window") continue;
                if (node.kind == "lettering")
                {
                    // waiting: mid grey and soft in a lit frame, near black and softer in a frame still ahead
                    var frameLit = drawnIn.TryGetValue(node, out var f) ? FrameLit(f, t, greyAhead) : 1f;
                    var waiting = Color.Lerp(WaitingAheadTint, WaitingTint, frameLit);
                    var waitingBlur = Mathf.Lerp(BlurAhead, BlurWaiting, frameLit);
                    var said = node.bubble != null && bubbleStart.TryGetValue(node.bubble, out var from)
                        ? Mathf.Clamp01((float)(t - from) / BalloonFadeSeconds) : 1f;
                    said = said * said * (3f - 2f * said);
                    scene.SetLook(node, Color.Lerp(waiting, Color.white, said), Mathf.Lerp(waitingBlur, 0f, said));
                    if (node.bubble == null) continue;
                    if (!visibleBubbles.Contains(node.bubble)) visibleBubbles.Add(node.bubble);
                    if (said >= 1f && !litBubbles.Contains(node.bubble)) litBubbles.Add(node.bubble);
                }
                else if (node.frame.HasValue && frameStart.ContainsKey(node.frame.Value))
                {
                    var lit = FrameLit(node.frame.Value, t, greyAhead);
                    scene.SetLook(node, Color.Lerp(AheadTint, Color.white, lit), Mathf.Lerp(BlurAhead, 0f, lit));
                }
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

        // 0 grey ahead to 1 in its colours. A frame that starts with its panel is never grey: only the ones the clock
        // still has to reach
        float FrameLit(int frame, double t, bool greyAhead)
        {
            if (!greyAhead || !frameStart.TryGetValue(frame, out var reached) || reached <= panelStart) return 1f;
            return Mathf.Clamp01((float)(t - reached) / FrameFadeSeconds);
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
