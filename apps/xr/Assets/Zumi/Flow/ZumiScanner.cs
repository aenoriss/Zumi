using System.Collections.Generic;
using Meta.XR;
using Meta.XR.MRUtilityKit;
using Unity.Collections;
using UnityEngine;
using UnityEngine.Rendering;
#if UNITY_ANDROID && !UNITY_EDITOR
using UnityEngine.Android;
#endif

namespace Zumi
{
    /// <summary>
    /// Load: the page scanner. First the reader touches the surface they will scan on (a hint with a fingertip coming
    /// down asks for it): an index fingertip coming down onto a level surface of the scanned room (a table's or any
    /// furniture's top), or, without one, a fingertip that came down and holds still for TouchStillSeconds below the
    /// chest (its height is the desk's). A ripple spreads where it touched, and a page-shaped guide (A4) lies centred
    /// there: square to the surface's edge nearest the reader when the surface is known, else facing the reader.
    /// The reader lays a pencil page in it and the scanner takes it by itself: ten times a second the guide's area of
    /// the passthrough camera image, with a ring of desk around it, is straightened into a small sample (each corner
    /// projected into the image with the camera's pose and intrinsics, then a homography drawn by ZumiWarp), read
    /// back without stalling and fed to <see cref="ZumiPageDetector"/>, which says when a new pencil page lies still
    /// in the guide with no hand over it. The guide's corners say what it sees, a line fills along its border while the page holds still, a light sweeps
    /// it, and the full-size straightened page flies onto a stack floating beside the reader. The Scan disc to the
    /// right of the guide takes a page at once; the small disc beside it takes the last page off the stack. The reader
    /// presses Done under the stack. Without the camera (the permission refused, no camera, the editor) the
    /// making-of's pencil pages arrive in the guide one after another as if laid there, and are taken the same way.
    /// </summary>
    public class ZumiScanner : MonoBehaviour
    {
        public const float DoneRadius = 0.03f;
        /// <summary>A4, metres.</summary>
        public static readonly Vector2 Guide = new(0.21f, 0.297f);
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
        public const float FlySeconds = 0.9f;
        /// <summary>The capture: the guide's outline brightens and a light sweeps it once, far edge to near.</summary>
        public const float SweepSeconds = 0.4f;
        /// <summary>The Scan button lies on the desk to the right of the guide: its radius, and the gap to the guide.</summary>
        public const float ScanRadius = 0.028f, ScanGap = 0.075f;
        /// <summary>Undo, a small disc right of Scan: its radius, the gap between the two; a page taken off drops and fades.</summary>
        public const float UndoRadius = 0.016f, UndoGap = 0.016f, UndoSeconds = 0.4f;
        /// <summary>The stack: metres ahead of the eye, to its left, below it; a stacked page's height.</summary>
        public const float StackAhead = 0.55f, StackSide = -0.36f, StackDrop = 0.12f, StackPageHeight = 0.2f;
        /// <summary>The straightened page's pixels.</summary>
        public const int CaptureHeight = 1000;
        const string CameraPermission = "horizonos.permission.HEADSET_CAMERA";

        // ---- detection ------------------------------------------------------------------------------------------
        /// <summary>Seconds between samples.</summary>
        public const float SampleInterval = 0.1f;
        /// <summary>On: a page whose pencil matches a page taken this session is not taken by itself (simulation: no
        /// page taken twice). Off: after a capture the next page counts once the guide was seen empty or a hand passed
        /// over it. Either way the Scan disc takes whatever lies in the guide.</summary>
        [Tooltip("Refuse a page whose pencil matches a page already taken; off: re-arm by an empty guide or a hand pass")]
        public bool RequireNovelty = true;

        // ---- recording, for tuning the detector on the headset (scan_sim.py replay FILE) ------------------------
        /// <summary>The recording: [float32 time][ReadWidth x ReadHeight x 4 RGBA bytes] per sample, appended.</summary>
        public const string RecordFile = "scan-samples.bin";
        const string RecordKey = "zumi.scanner.record";
        static int recordSetting = -1;
        /// <summary>Every sample appended to <see cref="RecordFile"/> under Application.persistentDataPath, and the
        /// detector's measures logged once a second; the hand menu's settings face switches it, kept across launches.</summary>
        public static bool RecordSamples
        {
            get
            {
                if (recordSetting < 0) recordSetting = PlayerPrefs.GetInt(RecordKey, 0);
                return recordSetting == 1;
            }
            set
            {
                recordSetting = value ? 1 : 0;
                PlayerPrefs.SetInt(RecordKey, recordSetting);
                PlayerPrefs.Save();
                Debug.Log($"[Zumi] scanner: recording scan samples {(value ? "on" : "off")} ({RecordPath})");
            }
        }
        public static string RecordPath => System.IO.Path.Combine(Application.persistentDataPath, RecordFile);

        // ---- the editor's stand-in: a pencil page arrives in the guide ------------------------------------------
        /// <summary>The guide lies empty this long, then a page slides in for this long, then lies still.</summary>
        public const float SimEmptySeconds = 0.9f, SimArriveSeconds = 0.8f;

        // ---- read-only state for tests and tools -----------------------------------------------------------------
        /// <summary>"waiting_desk", "ready", "scanning", "flying", "undoing", "done", "off".</summary>
        public string State { get; private set; } = "off";
        /// <summary>What the guide sees while ready: "empty", "seen" (a page, moving or not re-armed), "holding" (a
        /// page holding still, the border filling); "capturing" during the sweep.</summary>
        public string Detect { get; private set; } = "empty";
        /// <summary>The detector, its last sample's measures included (camera only).</summary>
        public ZumiPageDetector Detector => detector;
        /// <summary>The border's fill while a page holds still, 0..1.</summary>
        public float HoldProgress => CameraPlaying ? detector.HoldProgress
            : simHoldSince < 0f ? 0f : Mathf.Clamp01((Time.time - simHoldSince) / ZumiPageDetector.HoldSeconds);
        /// <summary>"auto" or "manual": how the last page was taken.</summary>
        public string LastCaptureTrigger { get; private set; }
        public int PagesCaptured => captures.Count;
        /// <summary>Where the guide was laid: "touch TABLE" (a known surface, its label), "touch still" (no surface known),
        /// "tool".</summary>
        public string GuideSource { get; private set; }
        /// <summary>The level surfaces of the scanned room a touch may land on.</summary>
        public int TouchSurfaces => surfaces.Count;
        public Vector3 TouchPoint { get; private set; }
        public Vector3 GuideCentre => guide ? guide.position : default;
        /// <summary>"camera" when the passthrough camera gave the last page, "fallback" when a pencil page stood in.</summary>
        public string LastCaptureSource { get; private set; }
        public bool CameraPlaying => cameraAccess && cameraAccess.enabled && cameraAccess.IsPlaying;

        public sealed class Capture
        {
            public Texture texture;
            public Transform card;
            public string source;
        }
        public IReadOnlyList<Capture> Captures => captures;

        Shader flat;
        ZumiCaption caption;
        ZumiMakingOfData data;
        Transform guide, stack;
        TextMesh counter;
        readonly ZumiDraw.Parts guideParts = new() { blended = true, queue = 3200 };
        readonly ZumiDraw.Parts stackParts = new() { blended = true, queue = 3300 };
        readonly List<Capture> captures = new();
        readonly ZumiPinch pinch = new();
        PassthroughCameraAccess cameraAccess;
        Material warp;
        float stateSince;
        ZumiDraw.RoundButton scanButton, undoButton;
        Material scanRing;
        static readonly Color RingColour = ZumiDraw.Hex(0xD9C7B4);
        static readonly Color CornersEmpty = new(ZumiDraw.FaintInk.r, ZumiDraw.FaintInk.g, ZumiDraw.FaintInk.b, 0.85f);
        Material outlineMaterial, cornersMaterial;
        Color outlineColour, cornersColour;
        Transform sweep;
        readonly Transform[] progress = new Transform[4];
        Pose head;
        Capture flying, removing;
        Pose flyFrom;
        Vector3 flyFromScale;

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
            caption.Show("Upload your sketches", 0.05f);
            StartCamera();
            BuildStack();
            FindSurfaces();
            detector.Reset();
            tips.Clear();
            ShowTouchHint();
            Debug.Log($"[Zumi] scanner: waiting for a touch on the desk ({surfaces.Count} level surfaces known)");
            data = await ZumiMakingOfData.Get();
        }

        void StartCamera()
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            if (!PassthroughCameraAccess.IsSupported)
            {
                Debug.Log("[Zumi] scanner: this headset has no passthrough camera access; pencil pages stand in");
                return;
            }
            if (!Permission.HasUserAuthorizedPermission(CameraPermission)) Permission.RequestUserPermission(CameraPermission);
            cameraAccess = gameObject.AddComponent<PassthroughCameraAccess>();
            cameraAccess.CameraPosition = PassthroughCameraAccess.CameraPositionType.Left;
            cameraAccess.RequestedResolution = new Vector2Int(1280, 960);
#else
            Debug.Log("[Zumi] scanner: no passthrough camera in the editor; the making-of's pencil pages stand in");
#endif
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
        bool Touched(out Vector3 at, out Vector3 away, out string source)
        {
            at = away = default;
            source = null;
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
                    foreach (var s in surfaces)
                    {
                        if (!s.Over(flat, TouchMargin) || p.y > s.top + TouchAbove || p.y < s.top - TouchBelow) continue;
                        var cameDown = false;
                        foreach (var (t, q) in track.history)
                            if (now - t <= TouchWindow && q.y >= s.top + TouchDrop) cameDown = true;
                        if (!cameDown) continue;
                        at = new Vector3(p.x, s.top, p.z);
                        away = s.Inward(eye);
                        source = "touch " + s.label;
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

        void Place(Vector3 at, Vector3 away, string source)
        {
            TouchPoint = at;
            HideTouchHint();
            Ripple(at, away);
            Debug.Log($"[Zumi] scanner: touched at {at:F3} ({source})");
            // centred on the touch, a breath above the surface
            Lay(at + Vector3.up * 0.002f, away, source);
        }

        /// <summary>Lays the guide as a touch there would (tools and tests).</summary>
        public void TouchAt(Vector3 at)
        {
            if (State != "waiting_desk") return;
            Place(at, Vector3.ProjectOnPlane(at - head.position, Vector3.up), "tool");
        }

        void Lay(Vector3 at, Vector3 away, string source)
        {
            GuideSource = source;
            if (guide) Destroy(guide.gameObject);
            guideParts.Destroy();
            guide = new GameObject("Scan guide").transform;
            // the guide lies flat: its -z (the side ZumiDraw draws on) faces up, its +y points away from the reader
            guide.SetPositionAndRotation(at, Quaternion.LookRotation(Vector3.down, away.sqrMagnitude > 1e-6f ? away.normalized : head.rotation * Vector3.forward));
            ZumiDraw.Shape(flat, guideParts, "Fill", guide, 0f, new Color(1f, 1f, 1f, 0.18f), 0, ZumiDraw.Box(-Guide.x / 2f, -Guide.y / 2f, Guide.x, Guide.y));
            const float t = 0.004f, corner = 0.04f;
            float w = Guide.x / 2f, h = Guide.y / 2f;
            // the four corners as brackets, quiet while the guide is empty, amber once it sees a page; a faint
            // outline between them
            var marks = new List<Vector2[]>();
            foreach (var (sx, sy) in new[] { (-1, -1), (1, -1), (1, 1), (-1, 1) })
            {
                marks.Add(ZumiDraw.Box(sx < 0 ? -w : w - corner, sy < 0 ? -h : h - t, corner, t));
                marks.Add(ZumiDraw.Box(sx < 0 ? -w : w - t, sy < 0 ? -h : h - corner, t, corner));
            }
            cornersColour = CornersEmpty;
            cornersMaterial = ZumiDraw.Shape(flat, guideParts, "Corners", guide, -0.0005f, cornersColour, 1, marks.ToArray()).GetComponent<MeshRenderer>().sharedMaterial;
            const float line = 0.0012f;
            outlineColour = new Color(ZumiDraw.Ink.r, ZumiDraw.Ink.g, ZumiDraw.Ink.b, 0.35f);
            outlineMaterial = ZumiDraw.Shape(flat, guideParts, "Outline", guide, -0.0003f, outlineColour, 1,
                ZumiDraw.Box(-w, -h, 2f * w, line), ZumiDraw.Box(-w, h - line, 2f * w, line), ZumiDraw.Box(-w, -h, line, 2f * h), ZumiDraw.Box(w - line, -h, line, 2f * h)).GetComponent<MeshRenderer>().sharedMaterial;
            // the hold: an amber line runs round the border, from the near left corner up the left edge, while a
            // page holds still; one unit-long bar per edge, stretched
            const float pt = 0.0028f;
            var starts = new[] { new Vector2(-w, -h), new Vector2(-w, h), new Vector2(w, h), new Vector2(w, -h) };
            var angles = new[] { 90f, 0f, -90f, 180f };
            for (var i = 0; i < 4; i++)
            {
                progress[i] = ZumiDraw.Shape(flat, guideParts, "Hold " + i, guide, -0.0006f, ZumiDraw.Hover, 2, ZumiDraw.Box(0f, -pt / 2f, 1f, pt));
                progress[i].localPosition = new Vector3(starts[i].x, starts[i].y, -0.0006f);
                progress[i].localRotation = Quaternion.Euler(0f, 0f, angles[i]);
                progress[i].localScale = new Vector3(0f, 1f, 1f);
            }
            // the capture's light: a soft band across the guide, swept far edge to near
            sweep = ZumiDraw.Shape(flat, guideParts, "Sweep", guide, -0.0007f, new Color(1f, 0.93f, 0.78f, 0.9f), 1,
                ZumiDraw.Box(-w, -0.006f, 2f * w, 0.012f), ZumiDraw.Box(-w, -0.02f, 2f * w, 0.014f));
            sweep.gameObject.SetActive(false);
            // everything lies flat, the right way up for the reader looking down from the seat
            var label = ZumiDraw.Text(flat, guideParts, "Hint", guide, new Vector3(0f, -h - 0.025f, -0.001f), 0.012f, ZumiDraw.Ink, 2, "Lay a page here: it is scanned when it lies still");
            label.transform.localRotation = Quaternion.identity;
            // Scan: one flat cream disc on the desk to the right of the guide, a thin ring and a scan glyph, nothing
            // else; the count is a light line under it
            var bx = w + ScanGap;
            scanButton = ZumiDraw.Round(flat, guideParts, "Scan", guide, new Vector2(bx, 0f), ScanRadius, 1, PressScan);
            scanButton.disc.SetColor("_Color", ZumiDraw.Plate);
            scanRing = ZumiDraw.Shape(flat, guideParts, "Ring", scanButton.transform, -0.0005f, RingColour, 2, ZumiDraw.Arc(ScanRadius, 0.0016f, 0f, 360f, 48)).GetComponent<MeshRenderer>().sharedMaterial;
            const float g = 0.009f, s = 0.0045f, k = 0.0014f;
            var glyph = new List<Vector2[]>();
            foreach (var (sx, sy) in new[] { (-1, -1), (1, -1), (1, 1), (-1, 1) })
            {
                glyph.Add(ZumiDraw.Box(sx < 0 ? -g : g - s, sy < 0 ? -g : g - k, s, k));
                glyph.Add(ZumiDraw.Box(sx < 0 ? -g : g - k, sy < 0 ? -g : g - s, k, s));
            }
            ZumiDraw.Shape(flat, guideParts, "Glyph", scanButton.transform, -0.0005f, ZumiDraw.SoftInk, 2, glyph.ToArray());
            counter = ZumiDraw.Text(flat, guideParts, "Counter", guide, new Vector3(bx, -ScanRadius - 0.016f, -0.001f), 0.0105f, ZumiDraw.SoftInk, 2, Count(captures.Count));
            counter.transform.localRotation = Quaternion.identity;
            // Undo: a smaller disc to the right of Scan with a curved arrow, there once a page is on the stack
            undoButton = ZumiDraw.Round(flat, guideParts, "Undo", guide, new Vector2(bx + ScanRadius + UndoGap + UndoRadius, 0f), UndoRadius, 1, PressUndo);
            undoButton.disc.SetColor("_Color", ZumiDraw.Plate);
            ZumiDraw.Shape(flat, guideParts, "Ring", undoButton.transform, -0.0005f, RingColour, 2, ZumiDraw.Arc(UndoRadius, 0.0012f, 0f, 360f, 36));
            ZumiDraw.Shape(flat, guideParts, "Arrow", undoButton.transform, -0.0005f, ZumiDraw.SoftInk, 2, UndoArrow());
            undoButton.transform.gameObject.SetActive(captures.Count > 0);
            Ready();
            Debug.Log($"[Zumi] scanner: guide laid on {source} at {at:F2}");
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
            Debug.Log($"[Zumi] scanner: done, {captures.Count} pages");
            if (State is "flying" or "undoing") doneWanted = true;
            else Finish();
        }

        /// <summary>Ends the scan now, as Done does (for tools and tests).</summary>
        public void Done() => PressDone();

        void Finish()
        {
            State = "done";
            ClearSimSheet();
            if (doneButton) doneButton.gameObject.SetActive(false);
            Debug.Log("[Zumi] scanner: all pages captured");
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
            switch (State)
            {
                case "waiting_desk":
                    AnimateHint();
                    if (data == null) break;
                    if (Touched(out var at, out var away, out var source)) Place(at, away, source);
                    break;
                case "ready":
                    Watch();
                    break;
                case "scanning":
                    Sweep();
                    break;
                case "flying":
                    Fly();
                    break;
                case "undoing":
                    Undoing();
                    break;
            }
            if (State is "ready" or "scanning" or "flying" or "undoing") ShowDetect();
        }

        void Ready()
        {
            State = "ready";
            stateSince = Time.time;
            Detect = "empty";
            // samples resume after the sweep and the flight: no stillness across the gap
            detector.Resume();
            simHoldSince = -1f;
            simStart = Time.time;
        }

        // ---- watching the guide --------------------------------------------------------------------------------

        readonly ZumiPageDetector detector = new();
        RenderTexture sampleRt;
        bool sampling;
        float nextSample;

        void Watch()
        {
            if (Time.time < nextSample) return;
            nextSample = Time.time + SampleInterval;
            if (CameraPlaying) RequestSample();
            else Simulate();
        }

        void RequestSample()
        {
            if (sampling) return;
            var image = cameraAccess.GetTexture();
            if (!image) return;
            if (!warp) warp = new Material(ZumiFlowKit.WarpShader);
            // the guide and a ring of desk around it
            SetHomography(warp, GuideInImage(out _, ZumiPageDetector.RingMetres(Guide)));
            if (!sampleRt)
            {
                sampleRt = new RenderTexture(ZumiPageDetector.ReadWidth, ZumiPageDetector.ReadHeight, 0, RenderTextureFormat.ARGB32) { name = "guide sample", wrapMode = TextureWrapMode.Clamp };
                sampleRt.Create();
            }
            Graphics.Blit(image, sampleRt, warp);
            sampling = true;
            AsyncGPUReadback.Request(sampleRt, 0, TextureFormat.RGBA32, OnSample);
        }

        void OnSample(AsyncGPUReadbackRequest request)
        {
            sampling = false;
            if (!this || State != "ready" || request.hasError) return;
            var now = Time.time;
            Record(request.GetData<byte>(), now);
            detector.RequireNovelty = RequireNovelty;
            var seen = detector.Feed(request.GetData<Color32>().AsReadOnlySpan(), now);
            Detect = seen switch
            {
                ZumiPageDetector.State.Empty => "empty",
                ZumiPageDetector.State.Seen => "seen",
                _ => "holding",
            };
            if (recording && now >= nextRecordLog)
            {
                nextRecordLog = now + 1f;
                Debug.Log($"[Zumi] scanner sample {now:F1}: {seen} {detector}");
            }
            if (seen != ZumiPageDetector.State.Capture) return;
            Debug.Log($"[Zumi] scanner: page held still for {ZumiPageDetector.HoldSeconds:F1} s ({detector})");
            Take("auto");
        }

        // ---- recording -----------------------------------------------------------------------------------------

        System.IO.FileStream recordStream;
        bool recording;
        float nextRecordLog;

        // the sample as scan_sim.py replay reads it: [float32 time][RGBA bytes], appended
        void Record(NativeArray<byte> px, float time)
        {
            recording = RecordSamples;
            if (!recording)
            {
                StopRecording();
                return;
            }
            if (recordStream == null)
            {
                try
                {
                    recordStream = new System.IO.FileStream(RecordPath, System.IO.FileMode.Append, System.IO.FileAccess.Write, System.IO.FileShare.Read, 1 << 18);
                    Debug.Log($"[Zumi] scanner: recording samples to {RecordPath} ({recordStream.Length / (4 + px.Length)} already there)");
                }
                catch (System.Exception e)
                {
                    Debug.LogWarning($"[Zumi] scanner: cannot record to {RecordPath}: {e.Message}");
                    recording = false;
                    return;
                }
            }
            System.Span<byte> stamp = stackalloc byte[4];
            System.BitConverter.TryWriteBytes(stamp, time);
            recordStream.Write(stamp);
            recordStream.Write(px.AsReadOnlySpan());
        }

        void StopRecording()
        {
            if (recordStream == null) return;
            recordStream.Dispose();
            recordStream = null;
        }

        void OnApplicationPause(bool paused)
        {
            if (paused) recordStream?.Flush();
        }

        void OnApplicationQuit() => StopRecording();

        // the corners and the border say what the guide sees
        void ShowDetect()
        {
            if (!cornersMaterial) return;
            var target = State == "ready" && Detect == "empty" ? CornersEmpty : ZumiDraw.Hover;
            cornersColour = Color.Lerp(cornersColour, target, 1f - Mathf.Exp(-10f * Time.deltaTime));
            if (State != "scanning") ZumiFlowKit.SetTint(cornersMaterial, cornersColour);
            var fill = State == "ready" && Detect == "holding" ? ZumiFlowKit.Smooth(HoldProgress) : 0f;
            float w = Guide.x / 2f, h = Guide.y / 2f;
            var lengths = new[] { 2f * h, 2f * w, 2f * h, 2f * w };
            var left = fill * 2f * (Guide.x + Guide.y);
            for (var i = 0; i < 4; i++)
            {
                var len = Mathf.Clamp(left, 0f, lengths[i]);
                left -= len;
                if (progress[i]) progress[i].localScale = new Vector3(len, 1f, 1f);
            }
        }

        // ---- the editor's stand-in -----------------------------------------------------------------------------

        float simStart, simHoldSince = -1f;
        Transform simCard;
        Material simMaterial;

        // the next pencil page slides into the guide, wobbles as a hand lets it go, then lies still: the guide's
        // states are driven directly (empty, seen while it slides, holding once it lies still), not through the
        // detector, which needs camera pixels
        void Simulate()
        {
            if (data == null || data.pages.Count == 0 || captures.Count >= data.pages.Count || Time.time - simStart < SimEmptySeconds)
            {
                ClearSimSheet();
                SimDetect("empty");
                return;
            }
            var t = Time.time - simStart;
            if (!simCard)
            {
                var tex = data.pages[captures.Count % data.pages.Count].pencilTexture;
                simMaterial = ZumiFlowKit.Picture(tex, Color.white, 3199);
                simCard = ZumiFlowKit.Card("Arriving page", guide, new Vector2(Guide.x, Guide.y), simMaterial).transform;
            }
            var k = Mathf.Clamp01((t - SimEmptySeconds) / SimArriveSeconds);
            var slide = ZumiFlowKit.Smooth(k);
            var wobble = (1f - k) * Mathf.Sin(t * 18f) * 0.004f;
            simCard.localPosition = new Vector3(wobble, -Guide.y * 0.7f * (1f - slide), -0.0004f);
            simCard.localRotation = Quaternion.Euler(0f, 0f, (1f - slide) * 8f);
            SimDetect(k >= 1f ? "holding" : slide > 0.5f ? "seen" : "empty");
            if (Detect == "holding" && Time.time - simHoldSince >= ZumiPageDetector.HoldSeconds) Take("auto");
        }

        void SimDetect(string seen)
        {
            if (seen == "holding" && simHoldSince < 0f) simHoldSince = Time.time;
            if (seen != "holding") simHoldSince = -1f;
            Detect = seen;
        }

        void ClearSimSheet()
        {
            if (simCard) Destroy(simCard.gameObject);
            if (simMaterial) Destroy(simMaterial);
            simCard = null;
        }

        // ---- capture -------------------------------------------------------------------------------------------

        Capture taking;

        void PressScan() => Take("manual");

        /// <summary>Takes the page in the guide now, as the Scan disc does (for tools and tests).</summary>
        public void Scan() => PressScan();

        // the camera's image now (the page held still), then the sweep, then the page flies
        void Take(string trigger)
        {
            if (State != "ready") return;
            var texture = CameraPlaying ? Straighten() : null;
            var source = texture ? "camera" : "fallback";
            if (!texture && data != null && data.pages.Count > 0) texture = data.pages[captures.Count % data.pages.Count].pencilTexture;
            LastCaptureSource = source;
            LastCaptureTrigger = trigger;
            taking = new Capture { texture = texture, source = source };
            // the sheet just taken (its pencil, or with novelty off until the scanner re-arms) is not taken again
            if (source == "camera") detector.Captured();
            simHoldSince = -1f;
            Detect = "capturing";
            State = "scanning";
            stateSince = Time.time;
            sweep.gameObject.SetActive(true);
            Debug.Log($"[Zumi] scanner: scan ({trigger})");
        }

        // the outline lights up, a band of light passes over the page, far edge to near, and the page is taken
        void Sweep()
        {
            var t = (Time.time - stateSince) / SweepSeconds;
            var glow = Mathf.Sin(Mathf.Clamp01(t) * Mathf.PI);
            ZumiFlowKit.SetTint(outlineMaterial, Color.Lerp(outlineColour, ZumiDraw.Hover, glow));
            ZumiFlowKit.SetTint(cornersMaterial, Color.Lerp(ZumiDraw.Hover, Color.white, glow * 0.6f));
            var h = Guide.y / 2f - 0.012f;
            sweep.localPosition = new Vector3(0f, Mathf.Lerp(h, -h, ZumiFlowKit.Smooth(t)), -0.0007f);
            // the press: the disc dips a few millimetres (the guide's +z is down) and its ring flashes once
            var press = LastCaptureTrigger == "manual" ? Mathf.Sin(Mathf.Clamp01(t * 1.6f) * Mathf.PI) : 0f;
            var p = scanButton.transform.localPosition;
            scanButton.transform.localPosition = new Vector3(p.x, p.y, -0.001f + 0.004f * press);
            scanRing.SetColor("_Color", Color.Lerp(RingColour, ZumiDraw.Hover, press));
            if (t < 1f) return;
            scanButton.transform.localPosition = new Vector3(p.x, p.y, -0.001f);
            scanRing.SetColor("_Color", RingColour);
            sweep.gameObject.SetActive(false);
            ZumiFlowKit.SetTint(outlineMaterial, outlineColour);
            Shoot();
        }

        void Shoot()
        {
            var capture = taking;
            taking = null;
            // the stand-in sheet in the guide becomes the page that flies
            ClearSimSheet();
            capture.card = ZumiFlowKit.Card($"Scanned page {captures.Count + 1}", null, new Vector2(Guide.x, Guide.y), ZumiFlowKit.Picture(capture.texture, Color.white, 3250)).transform;
            // it starts where the page lies, a breath above the guide, and flies onto the stack
            capture.card.SetPositionAndRotation(guide.position - guide.forward * 0.004f, guide.rotation);
            captures.Add(capture);
            flying = capture;
            flyFrom = new Pose(capture.card.position, capture.card.rotation);
            flyFromScale = capture.card.localScale;
            // the line has done its work
            caption.Hide();
            State = "flying";
            stateSince = Time.time;
            Debug.Log($"[Zumi] scanner: page {captures.Count} captured ({capture.source}, {LastCaptureTrigger})");
        }

        void Fly()
        {
            var t = (Time.time - stateSince) / FlySeconds;
            var to = StackPose(captures.Count - 1);
            var size = StackPageSize(flying.texture);
            var k = ZumiFlowKit.Smooth(t);
            var lift = Mathf.Sin(Mathf.Clamp01(t) * Mathf.PI) * 0.15f;
            flying.card.SetPositionAndRotation(Vector3.Lerp(flyFrom.position, to.position, k) + Vector3.up * lift, Quaternion.Slerp(flyFrom.rotation, to.rotation, k));
            flying.card.localScale = Vector3.Lerp(flyFromScale, new Vector3(size.x, size.y, 1f), k);
            if (t < 1f) return;
            flying = null;
            Landed();
        }

        void Landed()
        {
            counter.text = Count(captures.Count);
            if (doneButton) doneButton.gameObject.SetActive(captures.Count > 0);
            if (undoButton != null) undoButton.transform.gameObject.SetActive(captures.Count > 0);
            if (doneWanted && captures.Count > 0)
            {
                Finish();
                return;
            }
            doneWanted = false;
            Ready();
        }

        // ---- undo: the last page comes off the stack --------------------------------------------------------------

        void PressUndo()
        {
            if (State != "ready" || captures.Count == 0) return;
            removing = captures[^1];
            captures.RemoveAt(captures.Count - 1);
            // that page's pencil may be taken again
            if (removing.source == "camera") detector.Forget();
            flyFrom = new Pose(removing.card.position, removing.card.rotation);
            flyFromScale = removing.card.localScale;
            ClearSimSheet();
            State = "undoing";
            stateSince = Time.time;
            Debug.Log($"[Zumi] scanner: page {captures.Count + 1} taken off the stack");
        }

        /// <summary>Takes the last page off the stack, as the undo disc does (for tools and tests).</summary>
        public void Undo() => PressUndo();

        void Undoing()
        {
            var t = (Time.time - stateSince) / UndoSeconds;
            var k = ZumiFlowKit.Smooth(t);
            removing.card.position = flyFrom.position + Vector3.down * 0.08f * k;
            removing.card.localScale = flyFromScale * (1f - 0.6f * k);
            var m = removing.card.GetComponent<MeshRenderer>().sharedMaterial;
            ZumiFlowKit.SetTint(m, new Color(1f, 1f, 1f, 1f - k));
            if (t < 1f) return;
            Destroy(m);
            Destroy(removing.card.gameObject);
            // a camera capture is this page's own; a stand-in is the bundle's
            if (removing.source == "camera" && removing.texture is RenderTexture rt) Destroy(rt);
            removing = null;
            Landed();
        }

        /// <summary>Takes the bundle's pages left at once and ends the scan (the flow's skip).</summary>
        public void FillRemaining()
        {
            ClearSimSheet();
            if (State is "scanning")
            {
                if (taking?.source == "camera" && taking.texture is RenderTexture rt) Destroy(rt);
                taking = null;
                if (sweep) sweep.gameObject.SetActive(false);
                Ready();
            }
            while (data != null && captures.Count < data.pages.Count)
            {
                var tex = data.pages[captures.Count].pencilTexture;
                var c = new Capture { texture = tex, source = "fallback" };
                var pose = StackPose(captures.Count);
                var size = StackPageSize(tex);
                c.card = ZumiFlowKit.Card($"Scanned page {captures.Count + 1}", null, size, ZumiFlowKit.Picture(tex, Color.white, 3250)).transform;
                c.card.SetPositionAndRotation(pose.position, pose.rotation);
                captures.Add(c);
            }
            if (counter) counter.text = Count(captures.Count);
            // a page still in the air lands first
            if (State is "flying" or "undoing") doneWanted = true;
            else if (captures.Count > 0) Finish();
        }

        // The guide's corners in the camera image, page (u, v): (0, 0) the near left corner as the reader sees it, v
        // toward the far edge. The image is from the frame before (the texture is filled on the render thread). The
        // corners are moved out by grow on each side (the detector's desk ring).
        Vector2[] GuideInImage(out Pose pose, Vector2 grow = default)
        {
            pose = cameraAccess.GetCameraPose();
            float w = Guide.x / 2f + grow.x, h = Guide.y / 2f + grow.y;
            var corners = new[] { new Vector3(-w, -h), new Vector3(w, -h), new Vector3(w, h), new Vector3(-w, h) };
            var uv = new Vector2[4];
            for (var i = 0; i < 4; i++) uv[i] = cameraAccess.WorldToViewportPoint(guide.TransformPoint(corners[i]), pose);
            return uv;
        }

        // the page drawn upright, full size, from the guide's corners in the camera image
        Texture Straighten()
        {
            var image = cameraAccess.GetTexture();
            if (!image) return null;
            var uv = GuideInImage(out _);
            if (!warp) warp = new Material(ZumiFlowKit.WarpShader);
            SetHomography(warp, uv);
            var rt = new RenderTexture(Mathf.RoundToInt(CaptureHeight * Guide.x / Guide.y), CaptureHeight, 0, RenderTextureFormat.ARGB32) { name = $"capture {captures.Count + 1}", wrapMode = TextureWrapMode.Clamp };
            rt.Create();
            Graphics.Blit(image, rt, warp);
            Debug.Log($"[Zumi] scanner: page corners in the camera image {uv[0]:F3} {uv[1]:F3} {uv[2]:F3} {uv[3]:F3}");
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
            ClearSimSheet();
            if (guide) Destroy(guide.gameObject);
            guideParts.Destroy();
            HideTouchHint();
            if (ripple) Destroy(ripple.gameObject);
            rippleParts.Destroy();
            if (stack) Destroy(stack.gameObject);
            stackParts.Destroy();
            doneParts.Destroy();
            if (taking?.source == "camera" && taking.texture is RenderTexture rt) Destroy(rt);
            taking = null;
            if (removing != null && removing.card) Destroy(removing.card.gameObject);
            removing = null;
            if (sampleRt) Destroy(sampleRt);
            if (cameraAccess) Destroy(cameraAccess);
            StopRecording();
        }

        void OnDestroy() => Close();
    }
}
