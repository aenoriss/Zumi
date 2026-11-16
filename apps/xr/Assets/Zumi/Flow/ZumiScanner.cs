using System.Collections.Generic;
using Meta.XR;
using Meta.XR.MRUtilityKit;
using Oculus.Interaction;
using Oculus.Interaction.Surfaces;
using UnityEngine;
#if UNITY_ANDROID && !UNITY_EDITOR
using UnityEngine.Android;
#endif

namespace Zumi
{
    /// <summary>
    /// Load: the page scanner. First the reader touches the surface they will scan on (a hint with a fingertip coming
    /// down asks for it): an index fingertip coming down onto a level surface of the scanned room (a table's or any
    /// furniture's top), or, without one, a fingertip that came down and holds still for TouchStillSeconds below the
    /// chest (its height is the desk's). A ripple spreads where it touched, and a guide lies centred there: a grid of
    /// A4 portrait slots (Layouts, columns x rows, SlotGap apart, numbered faintly in reading order, the top row the
    /// one farthest from the reader), square to the surface's edge nearest the reader when the surface is known, else
    /// facing the reader, and kept on that surface's top. The Grid disc cycles the layouts the table's top has room
    /// for (all of them on an unknown surface); the grid grows from its near right corner, so the discs stay put. The
    /// grip under the grid slides the whole guide along the table (ZumiGuideDrag).
    /// The reader lays pencil pages in the slots and presses the Scan disc right of the grid's near edge (poked, or
    /// pointed at and pinched): one passthrough camera image is taken, every slot is projected into it with the
    /// camera's pose and intrinsics and straightened to a full-size page by its own homography (ZumiWarp), a light
    /// sweeps the grid, and the pages fly onto a stack floating left of the grid (the buttons are on its right) in slot order (at most the pages the episode
    /// has left). If any slot is out of the camera's image the press takes nothing: those slots flush red and the
    /// caption asks the reader to step back. The small disc beside Scan takes the last press's pages off the stack. The
    /// reader presses Done under the stack. The discs stand a little above the desk, tilted toward the reader, so a
    /// fingertip can press through them before it meets the table. With no camera access on the headset, or in the
    /// editor, a press takes the making-of's next pencil pages instead; with the camera there but not yet giving
    /// images, the disc shakes and the caption says so.
    /// </summary>
    public class ZumiScanner : MonoBehaviour
    {
        public const float DoneRadius = 0.03f;
        /// <summary>A4, metres: one slot.</summary>
        public static readonly Vector2 Guide = new(0.21f, 0.297f);
        /// <summary>Metres between slots; and the margin the grid keeps inside a known table's top.</summary>
        public const float SlotGap = 0.015f, FitMargin = 0.02f;
        /// <summary>The grid's layouts, columns x rows, in the order the Grid disc steps through them.</summary>
        public static readonly Vector2Int[] Layouts =
        {
            new(1, 1), new(2, 1), new(3, 1), new(2, 2), new(3, 2), new(4, 2), new(5, 2), new(5, 3),
        };
        /// <summary>The first layout is the largest that fits, up to this one (3 x 2): 5 x 3 is big.</summary>
        public const int DefaultLayoutCap = 4;
        /// <summary>Pages the demo episode has, when the making-of's pages are not loaded.</summary>
        public const int DemoPages = 10;
        /// <summary>The touch on a known surface: the fingertip within this of its top (above it, or pressed through
        /// it, as tracking allows), having been at least TouchDrop above it within TouchWindow seconds; the footprint
        /// is widened by TouchMargin.</summary>
        public const float TouchAbove = 0.015f, TouchBelow = 0.08f, TouchDrop = 0.03f, TouchWindow = 0.8f, TouchMargin = 0.02f;
        /// <summary>A surface counts when its top is between these heights above the floor.</summary>
        public const float SurfaceMin = 0.25f, SurfaceMax = 1.4f;
        /// <summary>Without a known surface: a fingertip that came down at least StillDrop and then held within
        /// StillRadius for TouchStillSeconds, at least BelowEye under the eyes.</summary>
        public const float TouchStillSeconds = 0.4f, StillRadius = 0.008f, StillDrop = 0.04f, BelowEye = 0.35f;
        /// <summary>The ripple: seconds, and its radius from start to end.</summary>
        public const float RippleSeconds = 0.8f, RippleFrom = 0.008f, RippleTo = 0.07f;
        public const float FlySeconds = 0.9f, FlyStagger = 0.08f;
        /// <summary>The capture: the slots' outlines brighten and a light sweeps the grid once, far edge to near.</summary>
        public const float SweepSeconds = 0.5f;
        /// <summary>The Scan button stands right of the grid's near edge: its radius, the gap to the grid, and its
        /// centre's distance in from the near edge.</summary>
        public const float ScanRadius = 0.028f, ScanGap = 0.075f, ScanInset = 0.04f;
        /// <summary>Undo, a small disc right of Scan: its radius, the gap between the two; a page taken off drops and fades.</summary>
        public const float UndoRadius = 0.016f, UndoGap = 0.016f, UndoSeconds = 0.4f;
        /// <summary>Grid, a disc beyond Scan (away from the reader) that steps through the layouts: its radius and gap.</summary>
        public const float GridRadius = 0.026f, GridGap = 0.018f;
        /// <summary>The grip: a pill this far outside the grid's near edge, and its grab box.</summary>
        public const float GripOut = 0.03f;
        public static readonly Vector3 GripBox = new(0.14f, 0.05f, 0.04f);
        /// <summary>The discs lean this many degrees toward the reader, their near edge this far above the desk (a
        /// fingertip must pass through a disc's plane before it meets the table); a ray or a poke counts within
        /// HitRadius of a disc's centre at least (4 cm and more across, wider than the small disc drawn).</summary>
        public const float DiscTilt = 35f, DiscClearance = 0.015f, HitRadius = 0.022f;
        /// <summary>Hovered: the disc grows by this; pressed: it dips, then springs back; refused: it shakes.</summary>
        public const float HoverScale = 1.08f, PressSeconds = 0.25f, ShakeSeconds = 0.4f;
        /// <summary>Seconds the slots out of the camera's view stay red.</summary>
        public const float OutOfViewSeconds = 1f;
        public const string CameraNotReady = "Camera not ready yet", OpeningLine = "Upload your sketches",
            StepBack = "Step back so I can see every page";
        /// <summary>The stack: metres ahead of the eye, to its left, below it; a stacked page's height.</summary>
        public const float StackAhead = 0.55f, StackSide = -0.36f, StackDrop = 0.12f, StackPageHeight = 0.2f;
        /// <summary>Once the guide lies on the desk the stack floats to the left of the grid (owner, 2026-11-16): this
        /// far left of its left edge, its middle this high above the desk and this far in from the grid's near edge;
        /// it follows the grid as it slides or changes layout, facing the reader.</summary>
        public const float StackBeside = 0.17f, StackAbove = 0.22f, StackIn = 0.15f;
        /// <summary>The straightened page's pixels.</summary>
        public const int CaptureHeight = 1000;
        const string CameraPermission = "horizonos.permission.HEADSET_CAMERA";

        // ---- read-only state for tests and tools -----------------------------------------------------------------
        /// <summary>"waiting_desk", "ready", "scanning", "flying", "undoing", "done", "off".</summary>
        public string State { get; private set; } = "off";
        /// <summary>"poke", "ray" or "tool": how the Scan disc was last pressed.</summary>
        public string LastCaptureTrigger { get; private set; }
        /// <summary>Why the last press took no page ("camera not playing", ...), or null.</summary>
        public string LastRefusal { get; private set; }
        public bool ScanHovered => scanDisc != null && scanDisc.Hovered;
        public bool UndoHovered => undoDisc != null && undoDisc.Hovered;
        public bool GridHovered => gridDisc != null && gridDisc.Hovered;
        public int PagesCaptured => captures.Count;
        /// <summary>Pages the last press added.</summary>
        public int LastBatch { get; private set; }
        /// <summary>Where the guide was laid: "touch TABLE" (a known surface, its label), "touch still" (no surface known),
        /// "tool".</summary>
        public string GuideSource { get; private set; }
        /// <summary>The level surfaces of the scanned room a touch may land on.</summary>
        public int TouchSurfaces => surfaces.Count;
        public Vector3 TouchPoint { get; private set; }
        public Vector3 GuideCentre => guide ? guide.position : default;
        /// <summary>The height the guide was laid at (the table's top); it never leaves it.</summary>
        public float GuidePlaneY { get; private set; }
        /// <summary>The guide lies on a known table's top (it is kept on it).</summary>
        public bool OnKnownTable => tableKnown;
        /// <summary>Metres the guide's footprint reaches past the known table's top (0 on it, or with no table).</summary>
        public float GuideOffTable => OffTable();
        /// <summary>"3x2": the grid's columns and rows.</summary>
        public string LayoutName => layout >= 0 ? $"{Layouts[layout].x}x{Layouts[layout].y}" : null;
        public int SlotCount => layout >= 0 ? Layouts[layout].x * Layouts[layout].y : 0;
        /// <summary>The layouts the Grid disc offers here.</summary>
        public int LayoutsOffered { get { var n = 0; for (var i = 0; i < Layouts.Length; i++) if (Fits(i)) n++; return n; } }
        public bool GuideDragging => drag && drag.Dragging;
        public bool GripHovered => drag && drag.Hovered;
        public float GuideSlid => drag ? drag.Slid : 0f;
        /// <summary>Slots out of the camera's image at the last refused press.</summary>
        public int SlotsOutOfView { get; private set; }
        /// <summary>"camera" when the passthrough camera gave the last pages, "fallback" when pencil pages stood in.</summary>
        public string LastCaptureSource { get; private set; }
        public bool CameraPlaying => cameraAccess && cameraAccess.enabled && cameraAccess.IsPlaying;

        public sealed class Capture
        {
            public Texture texture;
            public Transform card;
            public string source;
            internal int slot;
            internal Pose from;
            internal Vector3 fromScale;
        }
        public IReadOnlyList<Capture> Captures => captures;

        Shader flat;
        ZumiCaption caption;
        ZumiMakingOfData data;
        Transform guide, stack, slotsRoot, grip;
        TextMesh counter, hint, gridLabel;
        readonly ZumiDraw.Parts guideParts = new() { blended = true, queue = 3200 };
        readonly ZumiDraw.Parts slotParts = new() { blended = true, queue = 3200 };
        readonly ZumiDraw.Parts stackParts = new() { blended = true, queue = 3300 };
        readonly List<Capture> captures = new();
        readonly List<int> batches = new();
        readonly ZumiPinch pinch = new();
        PassthroughCameraAccess cameraAccess;
        bool intrinsicsLogged;
        Material warp;
        float stateSince;
        Disc scanDisc, undoDisc, gridDisc;
        ZumiGuideDrag drag;
        static readonly Color RingColour = ZumiDraw.Hex(0xD9C7B4), RedInk = ZumiDraw.Hex(0xC2452D);
        static readonly Color CornersColour = new(ZumiDraw.FaintInk.r, ZumiDraw.FaintInk.g, ZumiDraw.FaintInk.b, 0.85f);
        static readonly Color OutlineColour = new(ZumiDraw.Ink.r, ZumiDraw.Ink.g, ZumiDraw.Ink.b, 0.35f);
        static readonly Color GripColour = new(ZumiDraw.SoftInk.r, ZumiDraw.SoftInk.g, ZumiDraw.SoftInk.b, 0.7f);
        readonly List<Material> slotOutlines = new();
        Material cornersMaterial, gripMaterial;
        bool[] outOfView = new bool[0];
        float outOfViewAt = -10f;
        Transform sweep;
        Pose head;
        readonly List<Capture> taking = new(), flying = new(), removing = new();
        int layout = -1;
        bool tableKnown;
        Surface table;

        public System.Action Finished;

        public void Init(Shader flatShader, ZumiCaption caption)
        {
            flat = flatShader;
            this.caption = caption;
        }

        public async void Begin()
        {
            head = ZumiFlowKit.LevelHead();
            State = "waiting_desk";
            stateSince = Time.time;
            // near eye level: the reader looks down at the desk, and the line must not cover the guide
            caption.Show(OpeningLine, 0.05f);
            StartCamera();
            BuildStack();
            FindSurfaces();
            tips.Clear();
            ShowTouchHint();
            Debug.Log($"[ZumiScan] waiting for a touch on the desk ({surfaces.Count} level surfaces known)");
            data = await ZumiMakingOfData.Get();
        }

        void StartCamera()
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            if (!PassthroughCameraAccess.IsSupported)
            {
                Debug.Log("[ZumiScan] this headset has no passthrough camera access; pencil pages stand in");
                return;
            }
            var granted = Permission.HasUserAuthorizedPermission(CameraPermission);
            if (!granted) Permission.RequestUserPermission(CameraPermission);
            cameraAccess = gameObject.AddComponent<PassthroughCameraAccess>();
            cameraAccess.CameraPosition = PassthroughCameraAccess.CameraPositionType.Left;
            cameraAccess.RequestedResolution = new Vector2Int(1280, 960);
            Debug.Log($"[ZumiScan] passthrough camera starting (permission {(granted ? "granted" : "requested")})");
#else
            Debug.Log("[ZumiScan] no passthrough camera in the editor; a press takes the making-of's next pencil pages");
#endif
        }

        // why the camera cannot give a page now, or null
        string CameraProblem()
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            if (!Permission.HasUserAuthorizedPermission(CameraPermission)) return "camera permission missing";
#endif
            if (!cameraAccess.enabled) return "camera access disabled";
            if (!cameraAccess.IsPlaying) return "camera not playing";
            return null;
        }

        // the camera's real field of view, once, from its intrinsics over the image it gives
        void LogIntrinsics()
        {
            if (intrinsicsLogged || !CameraPlaying) return;
            intrinsicsLogged = true;
            var k = cameraAccess.Intrinsics;
            Vector2 sensor = k.SensorResolution, image = cameraAccess.CurrentResolution;
            var scale = image / sensor;
            scale /= Mathf.Max(scale.x, scale.y);
            var crop = Vector2.Scale(sensor, scale);
            float h = 2f * Mathf.Atan(crop.x / 2f / k.FocalLength.x) * Mathf.Rad2Deg, v = 2f * Mathf.Atan(crop.y / 2f / k.FocalLength.y) * Mathf.Rad2Deg;
            Debug.Log($"[ZumiScan] camera intrinsics: focal {k.FocalLength:F1}, principal {k.PrincipalPoint:F1}, sensor {k.SensorResolution}, image {cameraAccess.CurrentResolution}; field of view {h:F1} x {v:F1} degrees");
        }

        // ---- the guide on the desk -------------------------------------------------------------------------------

        /// <summary>A level surface of the scanned room: its footprint on the ground plan and its top.</summary>
        struct Surface
        {
            public string label;
            public Vector2 centre, axis, half;
            public float top;

            public bool Over(Vector2 p, float margin)
            {
                var d = p - centre;
                return Mathf.Abs(Vector2.Dot(d, axis)) <= half.x + margin && Mathf.Abs(Vector2.Dot(d, ZumiRoom.Perp(axis))) <= half.y + margin;
            }

            /// <summary>Half its extent along a level direction.</summary>
            public float Reach(Vector2 dir) => Mathf.Abs(Vector2.Dot(dir, axis)) * half.x + Mathf.Abs(Vector2.Dot(dir, ZumiRoom.Perp(axis))) * half.y;

            /// <summary>Level, pointing into the surface from its edge nearest the eye.</summary>
            public Vector3 Inward(Vector2 eye)
            {
                var rel = eye - centre;
                var perp = ZumiRoom.Perp(axis);
                Vector2 best = default;
                var beyond = float.MinValue;
                foreach (var (n, h) in new[] { (axis, half.x), (-axis, half.x), (perp, half.y), (-perp, half.y) })
                {
                    var b = Vector2.Dot(rel, n) - h;
                    if (b > beyond)
                    {
                        beyond = b;
                        best = n;
                    }
                }
                return new Vector3(-best.x, 0f, -best.y);
            }
        }

        readonly List<Surface> surfaces = new();

        // the tops of the room's furniture (volumes) and its level plane anchors, within reach of a seated hand
        void FindSurfaces()
        {
            surfaces.Clear();
            var mruk = MRUK.Instance;
            var room = mruk && mruk.IsInitialized && mruk.Rooms.Count > 0 ? mruk.GetCurrentRoom() : null;
            if (!room) return;
            var floor = room.FloorAnchors.Count > 0 ? room.FloorAnchors[0].transform.position.y : head.position.y - 1.2f;
            foreach (var anchor in room.Anchors)
            {
                var label = anchor.Label.ToString();
                if (label.Contains("FLOOR") || label.Contains("CEILING") || label.Contains("WALL")) continue;
                Surface s;
                if (anchor.VolumeBounds.HasValue)
                {
                    var box = ZumiRoom.Box(anchor);
                    s = new Surface { label = label, centre = box.footCentre, axis = box.footAxis, half = box.footHalf, top = box.top };
                }
                else if (anchor.PlaneRect.HasValue && anchor.transform.forward.y > 0.9f)
                {
                    var rect = anchor.PlaneRect.Value;
                    var t = anchor.transform;
                    s = new Surface { label = label, centre = ZumiRoom.Flat(t.TransformPoint(rect.center)), axis = ZumiRoom.Flat(t.right).normalized, half = rect.size / 2f, top = t.position.y };
                }
                else continue;
                if (s.top - floor < SurfaceMin || s.top - floor > SurfaceMax) continue;
                surfaces.Add(s);
            }
        }

        // ---- the touch -----------------------------------------------------------------------------------------

        sealed class TipTrack
        {
            public readonly Queue<(float t, Vector3 p)> history = new();
            public Vector3 stillAt;
            public float stillSince;
        }

        readonly List<TipTrack> tips = new();

        // an index fingertip coming down onto a known surface, or (none known) coming down and holding still
        bool Touched(out Vector3 at, out Vector3 away, out string source, out int on)
        {
            at = away = default;
            source = null;
            on = -1;
            var now = Time.time;
            var eye = ZumiRoom.Flat(head.position);
            var i = 0;
            foreach (var p in pinch.Tips())
            {
                if (tips.Count <= i) tips.Add(new TipTrack { stillAt = p, stillSince = now });
                var track = tips[i++];
                track.history.Enqueue((now, p));
                while (track.history.Count > 0 && now - track.history.Peek().t > TouchWindow + TouchStillSeconds) track.history.Dequeue();
                var flat = ZumiRoom.Flat(p);
                if (surfaces.Count > 0)
                {
                    for (var k = 0; k < surfaces.Count; k++)
                    {
                        var s = surfaces[k];
                        if (!s.Over(flat, TouchMargin) || p.y > s.top + TouchAbove || p.y < s.top - TouchBelow) continue;
                        var cameDown = false;
                        foreach (var (t, q) in track.history)
                            if (now - t <= TouchWindow && q.y >= s.top + TouchDrop) cameDown = true;
                        if (!cameDown) continue;
                        at = new Vector3(p.x, s.top, p.z);
                        away = s.Inward(eye);
                        source = "touch " + s.label;
                        on = k;
                        return true;
                    }
                    continue;
                }
                if ((p - track.stillAt).magnitude > StillRadius)
                {
                    track.stillAt = p;
                    track.stillSince = now;
                    continue;
                }
                if (now - track.stillSince < TouchStillSeconds || p.y > head.position.y - BelowEye) continue;
                var high = float.MinValue;
                foreach (var (t, q) in track.history)
                    if (t < track.stillSince) high = Mathf.Max(high, q.y);
                if (high - track.stillAt.y < StillDrop) continue;
                at = track.stillAt;
                away = Vector3.ProjectOnPlane(at - head.position, Vector3.up);
                source = "touch still";
                return true;
            }
            return false;
        }

        void Place(Vector3 at, Vector3 away, string source, int on)
        {
            TouchPoint = at;
            tableKnown = on >= 0;
            if (tableKnown) table = surfaces[on];
            HideTouchHint();
            Ripple(at, away);
            Debug.Log($"[ZumiScan] touched at {at:F3} ({source})");
            // centred on the touch, a breath above the surface
            Lay(at + Vector3.up * 0.002f, away, source);
        }

        /// <summary>Lays the guide as a touch there would (tools and tests): on the known surface under the point, if
        /// there is one.</summary>
        public void TouchAt(Vector3 at)
        {
            if (State != "waiting_desk") return;
            var eye = ZumiRoom.Flat(head.position);
            for (var k = 0; k < surfaces.Count; k++)
            {
                var s = surfaces[k];
                if (!s.Over(ZumiRoom.Flat(at), TouchMargin) || Mathf.Abs(at.y - s.top) > 0.1f) continue;
                Place(new Vector3(at.x, s.top, at.z), s.Inward(eye), "tool " + s.label, k);
                return;
            }
            Place(at, Vector3.ProjectOnPlane(at - head.position, Vector3.up), "tool", -1);
        }

        static Vector2 GridSize(Vector2Int g) => new(g.x * Guide.x + (g.x - 1) * SlotGap, g.y * Guide.y + (g.y - 1) * SlotGap);
        Vector2 Size => GridSize(Layouts[layout]);

        // the layout's grid fits the known table's top, the margin inside its edges (any fits on an unknown surface)
        bool Fits(int i)
        {
            if (!tableKnown || !guide) return true;
            var size = GridSize(Layouts[i]);
            return size.x <= 2f * (table.Reach(ZumiRoom.Flat(guide.right).normalized) - FitMargin) + 1e-4f
                && size.y <= 2f * (table.Reach(ZumiRoom.Flat(guide.up).normalized) - FitMargin) + 1e-4f;
        }

        // a guide centre kept on the known table's top (centred on it along a side it is longer than)
        Vector3 Clamp(Vector3 centre)
        {
            if (!tableKnown || !guide || layout < 0) return centre;
            Vector2 r = ZumiRoom.Flat(guide.right).normalized, f = ZumiRoom.Flat(guide.up).normalized;
            var rel = ZumiRoom.Flat(centre) - table.centre;
            var size = Size;
            float ra = Mathf.Max(table.Reach(r) - size.x / 2f - FitMargin, 0f), rb = Mathf.Max(table.Reach(f) - size.y / 2f - FitMargin, 0f);
            var a = Mathf.Clamp(Vector2.Dot(rel, r), -ra, ra);
            var b = Mathf.Clamp(Vector2.Dot(rel, f), -rb, rb);
            var flat = table.centre + r * a + f * b;
            return new Vector3(flat.x, centre.y, flat.y);
        }

        float OffTable()
        {
            if (!tableKnown || !guide || layout < 0) return 0f;
            Vector2 r = ZumiRoom.Flat(guide.right).normalized, f = ZumiRoom.Flat(guide.up).normalized;
            var rel = ZumiRoom.Flat(guide.position) - table.centre;
            var size = Size;
            return Mathf.Max(0f, Mathf.Abs(Vector2.Dot(rel, r)) + size.x / 2f - table.Reach(r), Mathf.Abs(Vector2.Dot(rel, f)) + size.y / 2f - table.Reach(f));
        }

        // slot k's centre on the guide, in reading order: left to right, the far row first
        static Vector2 SlotCentre(Vector2Int g, int k)
        {
            var size = GridSize(g);
            int c = k % g.x, r = k / g.x;
            return new Vector2(-size.x / 2f + Guide.x / 2f + c * (Guide.x + SlotGap), size.y / 2f - Guide.y / 2f - r * (Guide.y + SlotGap));
        }

        void Lay(Vector3 at, Vector3 away, string source)
        {
            GuideSource = source;
            if (guide) Destroy(guide.gameObject);
            guideParts.Destroy();
            slotParts.Destroy();
            guide = new GameObject("Scan guide").transform;
            // the guide lies flat: its -z (the side ZumiDraw draws on) faces up, its +y points away from the reader
            guide.SetPositionAndRotation(at, Quaternion.LookRotation(Vector3.down, away.sqrMagnitude > 1e-6f ? away.normalized : head.rotation * Vector3.forward));
            GuidePlaneY = at.y;
            // the largest layout that fits, up to 3 x 2
            layout = 0;
            for (var i = 0; i <= DefaultLayoutCap; i++)
                if (Fits(i)) layout = i;
            guide.position = Clamp(at);

            // Scan: one cream disc right of the grid's near edge, a thin ring and a scan glyph; the count is a light
            // line under it
            scanDisc = MakeDisc("Scan", Vector2.zero, ScanRadius, 0.0016f, how => PressScan(how));
            const float g = 0.009f, s = 0.0045f, k = 0.0014f;
            var glyph = new List<Vector2[]>();
            foreach (var (sx, sy) in new[] { (-1, -1), (1, -1), (1, 1), (-1, 1) })
            {
                glyph.Add(ZumiDraw.Box(sx < 0 ? -g : g - s, sy < 0 ? -g : g - k, s, k));
                glyph.Add(ZumiDraw.Box(sx < 0 ? -g : g - k, sy < 0 ? -g : g - s, k, s));
            }
            ZumiDraw.Shape(flat, guideParts, "Glyph", scanDisc.face, -0.0006f, ZumiDraw.SoftInk, 3, glyph.ToArray());
            counter = ZumiDraw.Text(flat, guideParts, "Counter", guide, Vector3.zero, 0.0105f, ZumiDraw.SoftInk, 2, Count(captures.Count));
            counter.transform.localRotation = Quaternion.identity;
            // Undo: a smaller disc right of Scan with a curved arrow, there once a page is on the stack
            undoDisc = MakeDisc("Undo", Vector2.zero, UndoRadius, 0.0012f, how => PressUndo(how));
            ZumiDraw.Shape(flat, guideParts, "Arrow", undoDisc.face, -0.0006f, ZumiDraw.SoftInk, 3, UndoArrow());
            undoDisc.root.gameObject.SetActive(captures.Count > 0);
            // Grid: beyond Scan, its layout written on it
            gridDisc = MakeDisc("Grid", Vector2.zero, GridRadius, 0.0014f, how => PressGrid(how));
            gridLabel = ZumiDraw.Text(flat, guideParts, "Layout", gridDisc.face, new Vector3(0f, 0f, -0.0008f), 0.0085f, ZumiDraw.Ink, 3, "");
            gridLabel.transform.localRotation = Quaternion.identity;
            // the grip: a soft pill with three ridges under the grid's near edge; grabbing it slides the guide
            var gripObject = new GameObject("Grip");
            gripObject.SetActive(false);
            grip = gripObject.transform;
            grip.SetParent(guide, false);
            drag = ZumiGuideDrag.Make(gripObject, guide, GripBox, Clamp);
            ZumiDraw.Shape(flat, guideParts, "Grip plate", grip, 0f, new Color(1f, 1f, 1f, 0.55f), 1, ZumiDraw.Rounded(0.08f, 0.018f, 0.009f));
            var ridges = new List<Vector2[]>();
            for (var r = -1; r <= 1; r++) ridges.Add(ZumiDraw.Box(-0.022f, r * 0.004f - 0.0006f, 0.044f, 0.0012f));
            gripMaterial = ZumiDraw.Shape(flat, guideParts, "Grip ridges", grip, -0.0005f, GripColour, 2, ridges.ToArray()).GetComponent<MeshRenderer>().sharedMaterial;
            gripObject.SetActive(true);
            // everything lies flat, the right way up for the reader looking down from the seat
            hint = ZumiDraw.Text(flat, guideParts, "Hint", guide, Vector3.zero, 0.012f, ZumiDraw.Ink, 2, "");
            hint.transform.localRotation = Quaternion.identity;
            BuildGrid();
            FollowGrid(true);
            Ready();
            Debug.Log($"[ZumiScan] guide laid on {source} at {guide.position:F2}, layout {LayoutName} ({LayoutsOffered} offered)");
        }

        // the slots, the sweep, and where the discs, grip and lines sit round them, for the current layout
        void BuildGrid()
        {
            if (slotsRoot) Destroy(slotsRoot.gameObject);
            slotParts.Destroy();
            slotOutlines.Clear();
            slotsRoot = new GameObject("Slots").transform;
            slotsRoot.SetParent(guide, false);
            var g = Layouts[layout];
            var size = Size;
            float w = Guide.x / 2f, h = Guide.y / 2f;
            const float t = 0.004f, corner = 0.035f, line = 0.0012f;
            var marks = new List<Vector2[]>();
            var fills = new List<Vector2[]>();
            for (var k = 0; k < g.x * g.y; k++)
            {
                var c = SlotCentre(g, k);
                fills.Add(ZumiDraw.Box(c.x - w, c.y - h, Guide.x, Guide.y));
                // the corners as quiet brackets, a faint outline between them, a faint number in the middle
                foreach (var (sx, sy) in new[] { (-1, -1), (1, -1), (1, 1), (-1, 1) })
                {
                    marks.Add(ZumiDraw.Box(c.x + (sx < 0 ? -w : w - corner), c.y + (sy < 0 ? -h : h - t), corner, t));
                    marks.Add(ZumiDraw.Box(c.x + (sx < 0 ? -w : w - t), c.y + (sy < 0 ? -h : h - corner), t, corner));
                }
                slotOutlines.Add(ZumiDraw.Shape(flat, slotParts, $"Outline {k + 1}", slotsRoot, -0.0003f, OutlineColour, 1,
                    ZumiDraw.Box(c.x - w, c.y - h, Guide.x, line), ZumiDraw.Box(c.x - w, c.y + h - line, Guide.x, line),
                    ZumiDraw.Box(c.x - w, c.y - h, line, Guide.y), ZumiDraw.Box(c.x + w - line, c.y - h, line, Guide.y)).GetComponent<MeshRenderer>().sharedMaterial);
                var number = ZumiDraw.Text(flat, slotParts, $"Number {k + 1}", slotsRoot, new Vector3(c.x, c.y, -0.0004f), 0.03f,
                    new Color(ZumiDraw.FaintInk.r, ZumiDraw.FaintInk.g, ZumiDraw.FaintInk.b, 0.45f), 1, (k + 1).ToString());
                number.transform.localRotation = Quaternion.identity;
            }
            ZumiDraw.Shape(flat, slotParts, "Fill", slotsRoot, 0f, new Color(1f, 1f, 1f, 0.18f), 0, fills.ToArray());
            cornersMaterial = ZumiDraw.Shape(flat, slotParts, "Corners", slotsRoot, -0.0005f, CornersColour, 1, marks.ToArray()).GetComponent<MeshRenderer>().sharedMaterial;
            outOfView = new bool[g.x * g.y];
            // the capture's light: a soft band across the whole grid, swept far edge to near
            float W = size.x / 2f, H = size.y / 2f;
            sweep = ZumiDraw.Shape(flat, slotParts, "Sweep", slotsRoot, -0.0007f, new Color(1f, 0.93f, 0.78f, 0.9f), 2,
                ZumiDraw.Box(-W, -0.006f, 2f * W, 0.012f), ZumiDraw.Box(-W, -0.02f, 2f * W, 0.014f));
            sweep.gameObject.SetActive(false);

            var scanAt = new Vector2(W + ScanGap, -H + ScanInset);
            Lift(scanDisc, scanAt, ScanRadius);
            Lift(undoDisc, scanAt + new Vector2(ScanRadius + UndoGap + UndoRadius, 0f), UndoRadius);
            Lift(gridDisc, scanAt + new Vector2(0f, ScanRadius + GridGap + GridRadius), GridRadius);
            counter.transform.localPosition = new Vector3(scanAt.x, scanAt.y - ScanRadius - 0.022f, -0.001f);
            grip.localPosition = new Vector3(0f, -H - GripOut, 0f);
            hint.transform.localPosition = new Vector3(0f, -H - GripOut - 0.035f, -0.001f);
            Hint();
            gridLabel.text = $"{g.x} × {g.y}";
        }

        // the line under the grid: how many pages to lay now
        void Hint()
        {
            if (!hint) return;
            var lay = Mathf.Min(SlotCount, PageLimit - captures.Count);
            hint.text = lay <= 0 ? "All pages are in" : lay == 1 ? "Lay a page here, then press the button" : $"Lay up to {lay} pages, then press the button";
        }

        /// <summary>Steps to the next layout that fits, as the Grid disc does (tools and tests).</summary>
        public void NextLayout() => PressGrid("tool");

        /// <summary>Sets a layout by name ("5x3"), even one the table has no room for (tools and screenshots).</summary>
        public bool SetLayout(string name)
        {
            if (!guide || State != "ready") return false;
            for (var i = 0; i < Layouts.Length; i++)
                if ($"{Layouts[i].x}x{Layouts[i].y}" == name)
                {
                    ApplyLayout(i);
                    return true;
                }
            return false;
        }

        void PressGrid(string how)
        {
            Debug.Log($"[ZumiScan] grid disc pressed ({how}), state {State}, layout {LayoutName}");
            if (State != "ready") return;
            gridDisc.pressedAt = Time.time;
            for (var step = 1; step <= Layouts.Length; step++)
            {
                var i = (layout + step) % Layouts.Length;
                if (!Fits(i)) continue;
                ApplyLayout(i);
                return;
            }
        }

        // the new grid keeps its near right corner where it was (the discs stay under the hand), then stays on the table
        void ApplyLayout(int i)
        {
            Vector3 right = guide.right, ahead = guide.up;
            var old = Size;
            var corner = guide.position + right * (old.x / 2f) - ahead * (old.y / 2f);
            layout = i;
            var size = Size;
            var centre = Clamp(corner - right * (size.x / 2f) + ahead * (size.y / 2f));
            centre.y = GuidePlaneY;
            drag.Reset(centre);
            BuildGrid();
            Debug.Log($"[ZumiScan] layout {LayoutName} ({SlotCount} slots), guide at {centre:F2}");
        }

        // ---- the discs -----------------------------------------------------------------------------------------

        /// <summary>A disc the reader pokes, or points at with the hand's ray and pinches. The root carries the
        /// targets and stands still; the face (drawn) grows while hovered, dips when pressed, shakes when refused.</summary>
        sealed class Disc
        {
            public string name;
            public Transform root, face;
            public Material ring;
            public float ringWidth;
            public PokeInteractable poke;
            public RayInteractable ray;
            public float scale = 1f, pressedAt = -10f, shakenAt = -10f;
            bool wasHovered;

            public bool Hovered => poke.State is InteractableState.Hover or InteractableState.Select
                || ray.State is InteractableState.Hover or InteractableState.Select;

            /// <summary>True once each time the hover starts.</summary>
            public bool HoverStarted()
            {
                var now = Hovered;
                var started = now && !wasHovered;
                wasHovered = now;
                return started;
            }
        }

        // tilted toward the reader (the guide's -y), lifted so its near edge clears the desk
        Disc MakeDisc(string name, Vector2 at, float radius, float ringWidth, System.Action<string> pressed)
        {
            var d = new Disc { name = name, ringWidth = ringWidth };
            var go = new GameObject(name);
            go.SetActive(false);
            d.root = go.transform;
            d.root.SetParent(guide, false);
            Lift(d, at, radius);
            // the guide's -z is up; turning about x by -tilt leans the disc's face (its -z) toward -y, the reader
            d.root.localRotation = Quaternion.Euler(-DiscTilt, 0f, 0f);
            var hit = Mathf.Max(radius, HitRadius);
            // the poke: a circle on the disc's plane, its normal (-z) toward the finger coming down
            var plane = go.AddComponent<PlaneSurface>();
            var circle = go.AddComponent<CircleSurface>();
            circle.InjectAllCircleSurface(plane);
            circle.InjectOptionalRadius(hit);
            d.poke = go.AddComponent<PokeInteractable>();
            d.poke.InjectAllPokeInteractable(circle);
            // the ray: a thin box the target's size, so a ray at a grazing angle still finds it
            var box = go.AddComponent<BoxCollider>();
            box.isTrigger = true;
            box.size = new Vector3(2f * hit, 2f * hit, 0.012f);
            var surface = go.AddComponent<ColliderSurface>();
            surface.InjectAllColliderSurface(box);
            d.ray = go.AddComponent<RayInteractable>();
            d.ray.InjectAllRayInteractable(surface);
            d.face = new GameObject("Face").transform;
            d.face.SetParent(d.root, false);
            ZumiDraw.Shape(flat, guideParts, "Disc", d.face, 0f, ZumiDraw.Plate, 1, ZumiDraw.Disc(radius));
            d.ring = ZumiDraw.Shape(flat, guideParts, "Ring", d.face, -0.0005f, RingColour, 2, ZumiDraw.Arc(radius, ringWidth, 0f, 360f, 48)).GetComponent<MeshRenderer>().sharedMaterial;
            d.poke.WhenStateChanged += change =>
            {
                if (change.NewState == InteractableState.Select) pressed("poke");
            };
            d.ray.WhenStateChanged += change =>
            {
                if (change.NewState == InteractableState.Select) pressed("ray");
            };
            go.SetActive(true);
            return d;
        }

        static void Lift(Disc d, Vector2 at, float radius)
        {
            var lift = radius * Mathf.Sin(DiscTilt * Mathf.Deg2Rad) + DiscClearance;
            d.root.localPosition = new Vector3(at.x, at.y, -lift);
        }

        // hover: a little larger, the rim amber; press: a dip into the disc and a flash; refused: a short shake
        void AnimateDisc(Disc d)
        {
            if (d == null || !d.root || !d.root.gameObject.activeInHierarchy) return;
            if (d.HoverStarted()) Debug.Log($"[ZumiScan] {d.name} disc hovered ({(d.poke.State != InteractableState.Normal ? "poke" : "ray")})");
            var hovered = d.Hovered;
            d.scale = Mathf.Lerp(d.scale, hovered ? HoverScale : 1f, 1f - Mathf.Exp(-14f * Time.deltaTime));
            var pt = (Time.time - d.pressedAt) / PressSeconds;
            var press = pt is >= 0f and < 1f ? Mathf.Sin(pt * Mathf.PI) : 0f;
            var st = (Time.time - d.shakenAt) / ShakeSeconds;
            var shake = st is >= 0f and < 1f ? Mathf.Sin(st * 40f) * 0.004f * (1f - st) : 0f;
            d.face.localScale = Vector3.one * d.scale;
            // the face's +z is into the disc
            d.face.localPosition = new Vector3(shake, 0f, 0.004f * press);
            d.ring.SetColor("_Color", Color.Lerp(RingColour, ZumiDraw.Hover, Mathf.Max(hovered ? 1f : 0f, press)));
        }

        // the grip's ridges and the slots' outlines turn amber while a hand is on or over it
        void AnimateGrip()
        {
            if (!drag || !gripMaterial) return;
            var lit = drag.Hovered || drag.Dragging;
            gripMaterial.SetColor("_Color", lit ? ZumiDraw.Hover : GripColour);
        }

        // the slots' outlines: amber while the guide is held, red for a moment where the camera could not see
        void AnimateOutlines(float sweepGlow)
        {
            var red = Time.time - outOfViewAt < OutOfViewSeconds;
            var held = drag && (drag.Dragging || drag.Hovered);
            for (var k = 0; k < slotOutlines.Count; k++)
            {
                var c = red && k < outOfView.Length && outOfView[k] ? RedInk
                    : Color.Lerp(held ? new Color(ZumiDraw.Hover.r, ZumiDraw.Hover.g, ZumiDraw.Hover.b, 0.8f) : OutlineColour, ZumiDraw.Hover, sweepGlow);
                slotOutlines[k].SetColor("_Color", c);
            }
            if (cornersMaterial) cornersMaterial.SetColor("_Color", Color.Lerp(CornersColour, Color.white, sweepGlow * 0.6f));
        }

        /// <summary>A curved arrow turning back: an arc over the top, its head at the left end pointing down.</summary>
        static Vector2[][] UndoArrow()
        {
            const float r = 0.0065f, from = -40f, to = 200f;
            var parts = new List<Vector2[]>(ZumiDraw.Arc(r, 0.0016f, from, to, 14));
            var a = to * Mathf.Deg2Rad;
            var radial = new Vector2(Mathf.Cos(a), Mathf.Sin(a));
            var along = new Vector2(-Mathf.Sin(a), Mathf.Cos(a));
            var p = radial * r;
            parts.Add(new[] { p + radial * 0.0034f, p + along * 0.0042f, p - radial * 0.0034f });
            return parts.ToArray();
        }

        // ---- the hint and the ripple ----------------------------------------------------------------------------

        public const string TouchHint = "Touch the table you'll scan on";
        Transform touchHint, finger, fingerRing, ripple;
        Material fingerRingMaterial;
        readonly ZumiDraw.Parts hintParts = new() { blended = true, queue = 3200 };
        readonly ZumiDraw.Parts rippleParts = new() { blended = true, queue = 3210 };
        float rippleSince = -10f;

        // a small cream plate below the eyes: a fingertip coming down onto a line, a ring where it lands, and the words
        void ShowTouchHint()
        {
            HideTouchHint();
            touchHint = new GameObject("Touch hint").transform;
            var at = head.position + head.rotation * new Vector3(0f, -0.2f, 0.6f);
            touchHint.SetPositionAndRotation(at, ZumiFlowKit.Facing(at, head.position));
            const float cap = 0.014f, icon = 0.05f;
            var width = ZumiDraw.Width(TouchHint, cap) + icon + 0.05f;
            ZumiDraw.Shape(flat, hintParts, "Plate", touchHint, 0f, ZumiDraw.Plate, 0, ZumiDraw.Rounded(width, 0.06f, 0.03f));
            var ix = -width / 2f + 0.025f + icon / 2f;
            ZumiDraw.Text(flat, hintParts, "Line", touchHint, new Vector3(ix + icon / 2f + 0.01f + ZumiDraw.Width(TouchHint, cap) / 2f, 0f, -0.002f), cap, ZumiDraw.Ink, 2, TouchHint);
            // the surface: a short line; the fingertip: a rounded bar with a nail
            ZumiDraw.Shape(flat, hintParts, "Surface", touchHint, -0.002f, ZumiDraw.SoftInk, 1, ZumiDraw.Box(ix - 0.018f, -0.016f, 0.036f, 0.0018f));
            finger = new GameObject("Finger").transform;
            finger.SetParent(touchHint, false);
            ZumiDraw.Shape(flat, hintParts, "Tip", finger, -0.003f, ZumiDraw.SoftInk, 2, ZumiDraw.Rounded(0.011f, 0.03f, 0.0055f));
            ZumiDraw.Shape(flat, hintParts, "Nail", finger, -0.004f, ZumiDraw.Plate, 3, ZumiDraw.Moved(ZumiDraw.Rounded(0.006f, 0.007f, 0.003f), new Vector2(0f, -0.006f)));
            fingerRing = ZumiDraw.Shape(flat, hintParts, "Ring", touchHint, -0.002f, ZumiDraw.Hover, 1, ZumiDraw.Arc(1f, 0.12f, 0f, 360f, 36));
            fingerRingMaterial = fingerRing.GetComponent<MeshRenderer>().sharedMaterial;
            fingerRing.localPosition = new Vector3(ix, -0.015f, -0.002f);
            finger.localPosition = new Vector3(ix, 0f, 0f);
            hintX = ix;
        }

        float hintX;

        // down in 0.45 s, a beat on the line (the ring spreads), back up
        void AnimateHint()
        {
            if (!touchHint) return;
            var c = Time.time % 1.6f / 1.6f;
            var down = c < 0.35f ? ZumiFlowKit.Smooth(c / 0.35f) : c < 0.6f ? 1f : 1f - ZumiFlowKit.Smooth((c - 0.6f) / 0.4f);
            finger.localPosition = new Vector3(hintX, 0.002f + 0.012f * (1f - down), 0f);
            var r = c is >= 0.35f and < 0.75f ? (c - 0.35f) / 0.4f : 1f;
            fingerRing.localScale = new Vector3(0.004f + 0.012f * r, 0.004f + 0.012f * r, 1f);
            fingerRing.localRotation = Quaternion.identity;
            ZumiFlowKit.SetTint(fingerRingMaterial, new Color(ZumiDraw.Hover.r, ZumiDraw.Hover.g, ZumiDraw.Hover.b, c is >= 0.35f and < 0.75f ? 1f - r : 0f));
        }

        void HideTouchHint()
        {
            if (touchHint) Destroy(touchHint.gameObject);
            hintParts.Destroy();
            touchHint = null;
        }

        // an amber ring spreading flat from the touch, fading
        void Ripple(Vector3 at, Vector3 away)
        {
            if (ripple) Destroy(ripple.gameObject);
            rippleParts.Destroy();
            ripple = new GameObject("Touch ripple").transform;
            ripple.SetPositionAndRotation(at + Vector3.up * 0.003f, Quaternion.LookRotation(Vector3.down, away.sqrMagnitude > 1e-6f ? away.normalized : Vector3.forward));
            ZumiDraw.Shape(flat, rippleParts, "Ring", ripple, 0f, ZumiDraw.Hover, 0, ZumiDraw.Arc(1f, 0.08f, 0f, 360f, 48));
            ZumiDraw.Shape(flat, rippleParts, "Dot", ripple, 0f, ZumiDraw.Hover, 1, ZumiDraw.Disc(0.12f, 24));
            rippleSince = Time.time;
            AnimateRipple();
        }

        void AnimateRipple()
        {
            if (!ripple) return;
            var t = (Time.time - rippleSince) / RippleSeconds;
            if (t >= 1f)
            {
                Destroy(ripple.gameObject);
                rippleParts.Destroy();
                ripple = null;
                return;
            }
            ripple.localScale = Vector3.one * Mathf.Lerp(RippleFrom, RippleTo, 1f - (1f - t) * (1f - t));
            rippleParts.SetAlpha(1f - t);
        }

        /// <summary>The ripple shows (for screenshots and tests).</summary>
        public bool RippleShown => ripple;

        // ---- the stack -----------------------------------------------------------------------------------------

        void BuildStack()
        {
            stack = new GameObject("Scan stack").transform;
            var at = head.position + head.rotation * new Vector3(StackSide, -StackDrop, StackAhead);
            stack.SetPositionAndRotation(at, ZumiFlowKit.Facing(at, head.position));
            // Done, under the stack, once there is a page
            doneButton = new GameObject("Done").transform;
            doneButton.SetParent(stack, false);
            doneButton.localPosition = new Vector3(0f, -StackPageHeight / 2f - 0.05f, -0.01f);
            var round = ZumiDraw.Round(flat, doneParts, "Done button", doneButton, Vector2.zero, DoneRadius, 1, PressDone);
            done = round;
            ZumiDraw.Shape(flat, doneParts, "Tick", round.transform, -0.002f, ZumiDraw.Ink, 2, Tick());
            ZumiDraw.Text(flat, doneParts, "Done label", doneButton, new Vector3(0f, -DoneRadius - 0.018f, -0.002f), 0.014f, ZumiDraw.Ink, 2, "Done");
            doneButton.gameObject.SetActive(false);
        }

        static string Count(int n) => n == 0 ? "No pages yet" : n == 1 ? "1 page" : $"{n} pages";

        Transform doneButton;
        ZumiDraw.RoundButton done;
        readonly ZumiDraw.Parts doneParts = new() { blended = true, queue = 3300 };
        bool doneWanted;

        void PressDone()
        {
            if (captures.Count == 0 || State is not ("ready" or "flying" or "undoing")) return;
            Debug.Log($"[ZumiScan] done, {captures.Count} pages");
            if (State is "flying" or "undoing") doneWanted = true;
            else Finish();
        }

        /// <summary>Ends the scan now, as Done does (for tools and tests).</summary>
        public void Done() => PressDone();

        void Finish()
        {
            State = "done";
            CancelInvoke(nameof(HideRefusal));
            if (doneButton) doneButton.gameObject.SetActive(false);
            Debug.Log("[ZumiScan] all pages captured");
            Finished?.Invoke();
        }

        public Pose StackPose(int i)
        {
            var local = new Vector3((i % 2 == 0 ? -1f : 1f) * 0.002f * (i % 3), 0f, -0.004f * i);
            return new Pose(stack.TransformPoint(local), stack.rotation * Quaternion.Euler(0f, 0f, (i % 2 == 0 ? -1.5f : 1.5f) * (i % 3)));
        }

        public Vector2 StackPageSize(Texture t)
        {
            var aspect = t ? (float)t.width / t.height : Guide.x / Guide.y;
            return new Vector2(StackPageHeight * aspect, StackPageHeight);
        }

        static Vector2[][] Tick() => new[]
        {
            new[] { new Vector2(-0.013f, 0.001f), new Vector2(-0.009f, 0.005f), new Vector2(-0.003f, -0.002f), new Vector2(-0.006f, -0.008f) },
            new[] { new Vector2(-0.006f, -0.008f), new Vector2(-0.003f, -0.002f), new Vector2(0.011f, 0.012f), new Vector2(0.014f, 0.008f) },
        };

        // ---- the loop ------------------------------------------------------------------------------------------

        void Update()
        {
            AnimateRipple();
            if (State == "off" || State == "done") return;
            LogIntrinsics();
            var glow = 0f;
            switch (State)
            {
                case "waiting_desk":
                    AnimateHint();
                    if (data == null) break;
                    if (Touched(out var at, out var away, out var source, out var on)) Place(at, away, source, on);
                    break;
                case "scanning":
                    glow = Sweep();
                    break;
                case "flying":
                    Fly();
                    break;
                case "undoing":
                    Undoing();
                    break;
            }
            AnimateDisc(scanDisc);
            AnimateDisc(undoDisc);
            AnimateDisc(gridDisc);
            AnimateGrip();
            AnimateOutlines(glow);
            FollowGrid(false);
        }

        /// <summary>Where the stack floats: left of the grid, above the desk, facing the reader.</summary>
        public Pose StackHome()
        {
            var size = Size;
            var at = guide.position - guide.right * (size.x / 2f + StackBeside) - guide.up * (size.y / 2f - StackIn) + Vector3.up * StackAbove;
            var eye = Camera.main ? Camera.main.transform.position : head.position;
            return new Pose(at, ZumiFlowKit.Facing(at, eye));
        }

        // the stack (and the pages on it) eases to its place beside the grid
        void FollowGrid(bool now)
        {
            if (!guide || !stack || layout < 0) return;
            var home = StackHome();
            var k = now ? 1f : 1f - Mathf.Exp(-10f * Time.deltaTime);
            stack.SetPositionAndRotation(Vector3.Lerp(stack.position, home.position, k), Quaternion.Slerp(stack.rotation, home.rotation, k));
        }

        void Ready()
        {
            State = "ready";
            stateSince = Time.time;
        }

        // ---- capture -------------------------------------------------------------------------------------------

        int PageLimit => data != null && data.pages.Count > 0 ? data.pages.Count : DemoPages;

        /// <summary>Takes the pages in the guide now, as the Scan disc does (for tools and tests).</summary>
        public void Scan() => PressScan("tool");

        // one camera image, every slot straightened from it, then the sweep, then the pages fly; without camera
        // access, the next pencil pages
        void PressScan(string how)
        {
            Debug.Log($"[ZumiScan] scan disc pressed ({how}), state {State}");
            if (State != "ready")
            {
                Debug.Log($"[ZumiScan] press ignored: the scanner is {State}");
                return;
            }
            if (drag && drag.Dragging)
            {
                Debug.Log("[ZumiScan] press ignored: the guide is being moved");
                return;
            }
            scanDisc.pressedAt = Time.time;
            LastCaptureTrigger = how;
            LastRefusal = null;
            var n = Mathf.Min(SlotCount, PageLimit - captures.Count);
            if (n <= 0)
            {
                Refuse("every page is taken", $"All {PageLimit} pages are in");
                return;
            }
            Debug.Log($"[ZumiScan] capture started (pages {captures.Count + 1} to {captures.Count + n}, layout {LayoutName})");
            taking.Clear();
            string source;
            if (cameraAccess)
            {
                var problem = CameraProblem();
                if (problem != null)
                {
                    Refuse(problem, CameraNotReady);
                    return;
                }
                var pose = cameraAccess.GetCameraPose();
                var corners = new Vector2[n][];
                var outside = 0;
                System.Array.Clear(outOfView, 0, outOfView.Length);
                for (var k = 0; k < n; k++)
                {
                    corners[k] = SlotInImage(k, pose, out var inView);
                    if (inView) continue;
                    outOfView[k] = true;
                    outside++;
                }
                SlotsOutOfView = outside;
                if (outside > 0)
                {
                    outOfViewAt = Time.time;
                    Refuse($"{outside} of {n} slots out of the camera's view", StepBack);
                    return;
                }
                var image = cameraAccess.GetTexture();
                if (!image)
                {
                    Refuse("camera texture null", CameraNotReady);
                    return;
                }
                Debug.Log($"[ZumiScan] camera texture ready {image.width}x{image.height}");
                for (var k = 0; k < n; k++) taking.Add(new Capture { texture = Straighten(image, corners[k], captures.Count + k + 1), source = "camera", slot = k });
                source = "camera";
            }
            else
            {
                source = "fallback";
                for (var k = 0; k < n; k++)
                {
                    Texture texture = data != null && data.pages.Count > 0 ? data.pages[(captures.Count + k) % data.pages.Count].pencilTexture : null;
                    taking.Add(new Capture { texture = texture, source = source, slot = k });
                }
                Debug.Log($"[ZumiScan] no camera access: the making-of's pencil pages {captures.Count + 1} to {captures.Count + n} stand in");
            }
            LastCaptureSource = source;
            State = "scanning";
            stateSince = Time.time;
            sweep.gameObject.SetActive(true);
        }

        // no page: the disc shakes and the caption says why, for a moment
        void Refuse(string reason, string line)
        {
            LastRefusal = reason;
            scanDisc.shakenAt = Time.time;
            Debug.LogWarning($"[ZumiScan] capture failed: {reason}");
            caption.Show(line, 0.05f);
            CancelInvoke(nameof(HideRefusal));
            Invoke(nameof(HideRefusal), 2f);
        }

        // back to the opening line until the first page is taken, else nothing
        void HideRefusal()
        {
            if (State is "off" or "done") return;
            if (captures.Count == 0) caption.Show(OpeningLine, 0.05f);
            else caption.Hide();
        }

        // the outlines light up, a band of light passes over the grid, far edge to near, and the pages are taken
        float Sweep()
        {
            var t = (Time.time - stateSince) / SweepSeconds;
            var glow = Mathf.Sin(Mathf.Clamp01(t) * Mathf.PI);
            var h = Size.y / 2f - 0.012f;
            sweep.localPosition = new Vector3(0f, Mathf.Lerp(h, -h, ZumiFlowKit.Smooth(t)), -0.0007f);
            if (t < 1f) return glow;
            sweep.gameObject.SetActive(false);
            Shoot();
            return 0f;
        }

        void Shoot()
        {
            var g = Layouts[layout];
            flying.Clear();
            foreach (var capture in taking)
            {
                var c = SlotCentre(g, capture.slot);
                capture.card = ZumiFlowKit.Card($"Scanned page {captures.Count + 1}", null, new Vector2(Guide.x, Guide.y), ZumiFlowKit.Picture(capture.texture, Color.white, 3250)).transform;
                // it starts where the page lies, a breath above its slot, and flies onto the stack
                capture.card.SetPositionAndRotation(guide.TransformPoint(new Vector3(c.x, c.y, -0.004f)), guide.rotation);
                capture.from = new Pose(capture.card.position, capture.card.rotation);
                capture.fromScale = capture.card.localScale;
                captures.Add(capture);
                flying.Add(capture);
            }
            LastBatch = taking.Count;
            batches.Add(taking.Count);
            taking.Clear();
            // the line has done its work
            CancelInvoke(nameof(HideRefusal));
            caption.Hide();
            State = "flying";
            stateSince = Time.time;
            Debug.Log($"[ZumiScan] pages added: {LastBatch} this press, {captures.Count} on the stack ({LastCaptureSource}, {LastCaptureTrigger})");
        }

        // the pages fly in slot order, each a beat after the one before
        void Fly()
        {
            var first = captures.Count - flying.Count;
            var all = true;
            for (var i = 0; i < flying.Count; i++)
            {
                var page = flying[i];
                var t = (Time.time - stateSince - i * FlyStagger) / FlySeconds;
                var to = StackPose(first + i);
                var size = StackPageSize(page.texture);
                var k = ZumiFlowKit.Smooth(Mathf.Clamp01(t));
                var lift = Mathf.Sin(Mathf.Clamp01(t) * Mathf.PI) * 0.15f;
                page.card.SetPositionAndRotation(Vector3.Lerp(page.from.position, to.position, k) + Vector3.up * lift, Quaternion.Slerp(page.from.rotation, to.rotation, k));
                page.card.localScale = Vector3.Lerp(page.fromScale, new Vector3(size.x, size.y, 1f), k);
                if (t < 1f) all = false;
            }
            if (!all) return;
            // landed: they ride with the stack from now on
            foreach (var page in flying) page.card.SetParent(stack, true);
            flying.Clear();
            Landed();
        }

        void Landed()
        {
            counter.text = Count(captures.Count);
            Hint();
            if (doneButton) doneButton.gameObject.SetActive(captures.Count > 0);
            if (undoDisc != null && undoDisc.root) undoDisc.root.gameObject.SetActive(captures.Count > 0);
            if (doneWanted && captures.Count > 0)
            {
                Finish();
                return;
            }
            doneWanted = false;
            Ready();
        }

        // ---- undo: the last press's pages come off the stack -----------------------------------------------------

        void PressUndo(string how)
        {
            Debug.Log($"[ZumiScan] undo disc pressed ({how}), state {State}, {captures.Count} pages");
            if (State != "ready" || captures.Count == 0) return;
            undoDisc.pressedAt = Time.time;
            var n = batches.Count > 0 ? batches[^1] : 1;
            if (batches.Count > 0) batches.RemoveAt(batches.Count - 1);
            n = Mathf.Min(n, captures.Count);
            removing.Clear();
            for (var i = captures.Count - n; i < captures.Count; i++)
            {
                var page = captures[i];
                page.from = new Pose(page.card.position, page.card.rotation);
                page.fromScale = page.card.localScale;
                removing.Add(page);
            }
            captures.RemoveRange(captures.Count - n, n);
            State = "undoing";
            stateSince = Time.time;
            Debug.Log($"[ZumiScan] undo: {n} pages taken off the stack, {captures.Count} left");
        }

        /// <summary>Takes the last press's pages off the stack, as the undo disc does (for tools and tests).</summary>
        public void Undo() => PressUndo("tool");

        void Undoing()
        {
            var t = (Time.time - stateSince) / UndoSeconds;
            var k = ZumiFlowKit.Smooth(t);
            foreach (var page in removing)
            {
                page.card.position = page.from.position + Vector3.down * 0.08f * k;
                page.card.localScale = page.fromScale * (1f - 0.6f * k);
                ZumiFlowKit.SetTint(page.card.GetComponent<MeshRenderer>().sharedMaterial, new Color(1f, 1f, 1f, 1f - k));
            }
            if (t < 1f) return;
            foreach (var page in removing) Drop(page);
            removing.Clear();
            Landed();
        }

        static void Drop(Capture page)
        {
            if (page.card)
            {
                Destroy(page.card.GetComponent<MeshRenderer>().sharedMaterial);
                Destroy(page.card.gameObject);
            }
            // a camera capture is this page's own; a stand-in is the bundle's
            if (page.source == "camera" && page.texture is RenderTexture rt) Destroy(rt);
        }

        /// <summary>Takes the bundle's pages left at once and ends the scan (the flow's skip).</summary>
        public void FillRemaining()
        {
            if (State is "scanning")
            {
                foreach (var page in taking)
                    if (page.source == "camera" && page.texture is RenderTexture rt) Destroy(rt);
                taking.Clear();
                if (sweep) sweep.gameObject.SetActive(false);
                Ready();
            }
            var added = 0;
            while (data != null && captures.Count < data.pages.Count)
            {
                var tex = data.pages[captures.Count].pencilTexture;
                var c = new Capture { texture = tex, source = "fallback" };
                var pose = StackPose(captures.Count);
                var size = StackPageSize(tex);
                c.card = ZumiFlowKit.Card($"Scanned page {captures.Count + 1}", null, size, ZumiFlowKit.Picture(tex, Color.white, 3250)).transform;
                c.card.SetPositionAndRotation(pose.position, pose.rotation);
                c.card.SetParent(stack, true);
                captures.Add(c);
                added++;
            }
            if (added > 0) batches.Add(added);
            if (counter) counter.text = Count(captures.Count);
            // a page still in the air lands first
            if (State is "flying" or "undoing") doneWanted = true;
            else if (captures.Count > 0) Finish();
        }

        // Slot k's corners in the camera image, page (u, v): (0, 0) the near left corner as the reader sees it, v
        // toward the far edge; and whether all four are in front of the camera and inside its image. The image is from
        // the frame before (the texture is filled on the render thread).
        Vector2[] SlotInImage(int k, Pose pose, out bool inView)
        {
            var c = SlotCentre(Layouts[layout], k);
            float w = Guide.x / 2f, h = Guide.y / 2f;
            var corners = new[] { new Vector3(c.x - w, c.y - h), new Vector3(c.x + w, c.y - h), new Vector3(c.x + w, c.y + h), new Vector3(c.x - w, c.y + h) };
            var uv = new Vector2[4];
            inView = true;
            for (var i = 0; i < 4; i++)
            {
                var world = guide.TransformPoint(corners[i]);
                uv[i] = cameraAccess.WorldToViewportPoint(world, pose);
                var ahead = (Quaternion.Inverse(pose.rotation) * (world - pose.position)).z;
                if (ahead <= 0.01f || uv[i].x < 0f || uv[i].x > 1f || uv[i].y < 0f || uv[i].y > 1f) inView = false;
            }
            return uv;
        }

        // one page drawn upright, full size, from its slot's corners in the camera image
        Texture Straighten(Texture image, Vector2[] uv, int number)
        {
            if (!warp) warp = new Material(ZumiFlowKit.WarpShader);
            SetHomography(warp, uv);
            var rt = new RenderTexture(Mathf.RoundToInt(CaptureHeight * Guide.x / Guide.y), CaptureHeight, 0, RenderTextureFormat.ARGB32) { name = $"capture {number}", wrapMode = TextureWrapMode.Clamp };
            rt.Create();
            Graphics.Blit(image, rt, warp);
            Debug.Log($"[ZumiScan] page {number} warped {rt.width}x{rt.height}, corners in the camera image {uv[0]:F3} {uv[1]:F3} {uv[2]:F3} {uv[3]:F3}");
            return rt;
        }

        /// <summary>The homography from the unit square onto the quad p0 (0,0), p1 (1,0), p2 (1,1), p3 (0,1) (Heckbert's
        /// square-to-quad), as three rows for ZumiWarp.</summary>
        public static void SetHomography(Material m, Vector2[] p)
        {
            float sx = p[0].x - p[1].x + p[2].x - p[3].x, sy = p[0].y - p[1].y + p[2].y - p[3].y;
            float a, b, c, d, e, f, g, hh;
            if (Mathf.Abs(sx) < 1e-7f && Mathf.Abs(sy) < 1e-7f)
            {
                a = p[1].x - p[0].x; b = p[2].x - p[1].x; c = p[0].x;
                d = p[1].y - p[0].y; e = p[2].y - p[1].y; f = p[0].y;
                g = hh = 0f;
            }
            else
            {
                float dx1 = p[1].x - p[2].x, dx2 = p[3].x - p[2].x, dy1 = p[1].y - p[2].y, dy2 = p[3].y - p[2].y;
                var den = dx1 * dy2 - dx2 * dy1;
                g = (sx * dy2 - dx2 * sy) / den;
                hh = (dx1 * sy - sx * dy1) / den;
                a = p[1].x - p[0].x + g * p[1].x; b = p[3].x - p[0].x + hh * p[3].x; c = p[0].x;
                d = p[1].y - p[0].y + g * p[1].y; e = p[3].y - p[0].y + hh * p[3].y; f = p[0].y;
            }
            m.SetVector("_H0", new Vector4(a, b, c, 0f));
            m.SetVector("_H1", new Vector4(d, e, f, 0f));
            m.SetVector("_H2", new Vector4(g, hh, 1f, 0f));
        }

        /// <summary>The guide and the counter go; the captured pages stay for the making-of to take.</summary>
        public void Close()
        {
            State = "off";
            CancelInvoke();
            if (guide) Destroy(guide.gameObject);
            guideParts.Destroy();
            slotParts.Destroy();
            HideTouchHint();
            if (ripple) Destroy(ripple.gameObject);
            rippleParts.Destroy();
            // the captured pages stay: off the stack before it goes
            foreach (var page in captures)
                if (page.card && page.card.parent == stack) page.card.SetParent(null, true);
            if (stack) Destroy(stack.gameObject);
            stackParts.Destroy();
            doneParts.Destroy();
            foreach (var page in taking)
                if (page.source == "camera" && page.texture is RenderTexture rt) Destroy(rt);
            taking.Clear();
            foreach (var page in removing) Drop(page);
            removing.Clear();
            if (cameraAccess) Destroy(cameraAccess);
        }

        void OnDestroy() => Close();
    }
}
