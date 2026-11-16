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
    /// chest (its height is the desk's). A ripple spreads where it touched, and a page-shaped guide (A4) lies centred
    /// there: square to the surface's edge nearest the reader when the surface is known, else facing the reader.
    /// The reader lays a pencil page in it and presses the Scan disc to the right of the guide (poked, or pointed at
    /// and pinched): the guide's area of the passthrough camera image is straightened to a full-size page (each corner
    /// projected into the image with the camera's pose and intrinsics, then a homography drawn by ZumiWarp), a light
    /// sweeps the guide, and the page flies onto a stack floating beside the reader. The small disc beside Scan takes
    /// the last page off the stack. The reader presses Done under the stack. The discs stand a little above the desk,
    /// tilted toward the reader, so a fingertip can press through them before it meets the table. With no camera
    /// access on the headset, or in the editor, a press takes the making-of's next pencil page instead; with the
    /// camera there but not yet giving images, the disc shakes and the caption says so.
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
        /// <summary>The Scan button stands to the right of the guide: its radius, and the gap to the guide.</summary>
        public const float ScanRadius = 0.028f, ScanGap = 0.075f;
        /// <summary>Undo, a small disc right of Scan: its radius, the gap between the two; a page taken off drops and fades.</summary>
        public const float UndoRadius = 0.016f, UndoGap = 0.016f, UndoSeconds = 0.4f;
        /// <summary>The discs lean this many degrees toward the reader, their near edge this far above the desk (a
        /// fingertip must pass through a disc's plane before it meets the table); a ray or a poke counts within
        /// HitRadius of a disc's centre at least (4 cm and more across, wider than the small disc drawn).</summary>
        public const float DiscTilt = 35f, DiscClearance = 0.015f, HitRadius = 0.022f;
        /// <summary>Hovered: the disc grows by this; pressed: it dips, then springs back; refused: it shakes.</summary>
        public const float HoverScale = 1.08f, PressSeconds = 0.25f, ShakeSeconds = 0.4f;
        public const string CameraNotReady = "Camera not ready yet", OpeningLine = "Upload your sketches";
        /// <summary>The stack: metres ahead of the eye, to its left, below it; a stacked page's height.</summary>
        public const float StackAhead = 0.55f, StackSide = -0.36f, StackDrop = 0.12f, StackPageHeight = 0.2f;
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
        Disc scanDisc, undoDisc;
        static readonly Color RingColour = ZumiDraw.Hex(0xD9C7B4);
        static readonly Color CornersColour = new(ZumiDraw.FaintInk.r, ZumiDraw.FaintInk.g, ZumiDraw.FaintInk.b, 0.85f);
        Material outlineMaterial, cornersMaterial;
        Color outlineColour;
        Transform sweep;
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
            Debug.Log("[ZumiScan] no passthrough camera in the editor; a press takes the making-of's next pencil page");
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
            Debug.Log($"[ZumiScan] touched at {at:F3} ({source})");
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
            // the four corners as quiet brackets, a faint outline between them
            var marks = new List<Vector2[]>();
            foreach (var (sx, sy) in new[] { (-1, -1), (1, -1), (1, 1), (-1, 1) })
            {
                marks.Add(ZumiDraw.Box(sx < 0 ? -w : w - corner, sy < 0 ? -h : h - t, corner, t));
                marks.Add(ZumiDraw.Box(sx < 0 ? -w : w - t, sy < 0 ? -h : h - corner, t, corner));
            }
            cornersMaterial = ZumiDraw.Shape(flat, guideParts, "Corners", guide, -0.0005f, CornersColour, 1, marks.ToArray()).GetComponent<MeshRenderer>().sharedMaterial;
            const float line = 0.0012f;
            outlineColour = new Color(ZumiDraw.Ink.r, ZumiDraw.Ink.g, ZumiDraw.Ink.b, 0.35f);
            outlineMaterial = ZumiDraw.Shape(flat, guideParts, "Outline", guide, -0.0003f, outlineColour, 1,
                ZumiDraw.Box(-w, -h, 2f * w, line), ZumiDraw.Box(-w, h - line, 2f * w, line), ZumiDraw.Box(-w, -h, line, 2f * h), ZumiDraw.Box(w - line, -h, line, 2f * h)).GetComponent<MeshRenderer>().sharedMaterial;
            // the capture's light: a soft band across the guide, swept far edge to near
            sweep = ZumiDraw.Shape(flat, guideParts, "Sweep", guide, -0.0007f, new Color(1f, 0.93f, 0.78f, 0.9f), 1,
                ZumiDraw.Box(-w, -0.006f, 2f * w, 0.012f), ZumiDraw.Box(-w, -0.02f, 2f * w, 0.014f));
            sweep.gameObject.SetActive(false);
            // everything lies flat, the right way up for the reader looking down from the seat
            var label = ZumiDraw.Text(flat, guideParts, "Hint", guide, new Vector3(0f, -h - 0.025f, -0.001f), 0.012f, ZumiDraw.Ink, 2, "Lay a page here, then press the button");
            label.transform.localRotation = Quaternion.identity;
            // Scan: one cream disc to the right of the guide, a thin ring and a scan glyph, nothing else; the count is
            // a light line under it
            var bx = w + ScanGap;
            scanDisc = MakeDisc("Scan", new Vector2(bx, 0f), ScanRadius, 0.0016f, how => PressScan(how));
            const float g = 0.009f, s = 0.0045f, k = 0.0014f;
            var glyph = new List<Vector2[]>();
            foreach (var (sx, sy) in new[] { (-1, -1), (1, -1), (1, 1), (-1, 1) })
            {
                glyph.Add(ZumiDraw.Box(sx < 0 ? -g : g - s, sy < 0 ? -g : g - k, s, k));
                glyph.Add(ZumiDraw.Box(sx < 0 ? -g : g - k, sy < 0 ? -g : g - s, k, s));
            }
            ZumiDraw.Shape(flat, guideParts, "Glyph", scanDisc.face, -0.0006f, ZumiDraw.SoftInk, 3, glyph.ToArray());
            counter = ZumiDraw.Text(flat, guideParts, "Counter", guide, new Vector3(bx, -ScanRadius - 0.022f, -0.001f), 0.0105f, ZumiDraw.SoftInk, 2, Count(captures.Count));
            counter.transform.localRotation = Quaternion.identity;
            // Undo: a smaller disc to the right of Scan with a curved arrow, there once a page is on the stack
            undoDisc = MakeDisc("Undo", new Vector2(bx + ScanRadius + UndoGap + UndoRadius, 0f), UndoRadius, 0.0012f, how => PressUndo(how));
            ZumiDraw.Shape(flat, guideParts, "Arrow", undoDisc.face, -0.0006f, ZumiDraw.SoftInk, 3, UndoArrow());
            undoDisc.root.gameObject.SetActive(captures.Count > 0);
            Ready();
            Debug.Log($"[ZumiScan] guide laid on {source} at {at:F2}");
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
            var lift = radius * Mathf.Sin(DiscTilt * Mathf.Deg2Rad) + DiscClearance;
            // the guide's -z is up; turning about x by -tilt leans the disc's face (its -z) toward -y, the reader
            d.root.localPosition = new Vector3(at.x, at.y, -lift);
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
            switch (State)
            {
                case "waiting_desk":
                    AnimateHint();
                    if (data == null) break;
                    if (Touched(out var at, out var away, out var source)) Place(at, away, source);
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
            AnimateDisc(scanDisc);
            AnimateDisc(undoDisc);
        }

        void Ready()
        {
            State = "ready";
            stateSince = Time.time;
        }

        // ---- capture -------------------------------------------------------------------------------------------

        Capture taking;

        /// <summary>Takes the page in the guide now, as the Scan disc does (for tools and tests).</summary>
        public void Scan() => PressScan("tool");

        // the camera's image now, then the sweep, then the page flies; without camera access, the next pencil page
        void PressScan(string how)
        {
            Debug.Log($"[ZumiScan] scan disc pressed ({how}), state {State}");
            if (State != "ready")
            {
                Debug.Log($"[ZumiScan] press ignored: the scanner is {State}");
                return;
            }
            scanDisc.pressedAt = Time.time;
            LastCaptureTrigger = how;
            LastRefusal = null;
            Debug.Log($"[ZumiScan] capture started (page {captures.Count + 1})");
            Texture texture = null;
            string source;
            if (cameraAccess)
            {
                var problem = CameraProblem();
                if (problem == null)
                {
                    texture = Straighten(out problem);
                }
                if (!texture)
                {
                    Refuse(problem);
                    return;
                }
                source = "camera";
            }
            else
            {
                source = "fallback";
                if (data != null && data.pages.Count > 0) texture = data.pages[captures.Count % data.pages.Count].pencilTexture;
                Debug.Log($"[ZumiScan] no camera access: the making-of's pencil page {captures.Count + 1} stands in ({(texture ? $"{texture.width}x{texture.height}" : "none loaded")})");
            }
            LastCaptureSource = source;
            taking = new Capture { texture = texture, source = source };
            State = "scanning";
            stateSince = Time.time;
            sweep.gameObject.SetActive(true);
        }

        // no page: the disc shakes and the caption says why, for a moment
        void Refuse(string reason)
        {
            LastRefusal = reason;
            scanDisc.shakenAt = Time.time;
            Debug.LogWarning($"[ZumiScan] capture failed: {reason}");
            caption.Show(CameraNotReady, 0.05f);
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

        // the outline lights up, a band of light passes over the page, far edge to near, and the page is taken
        void Sweep()
        {
            var t = (Time.time - stateSince) / SweepSeconds;
            var glow = Mathf.Sin(Mathf.Clamp01(t) * Mathf.PI);
            ZumiFlowKit.SetTint(outlineMaterial, Color.Lerp(outlineColour, ZumiDraw.Hover, glow));
            ZumiFlowKit.SetTint(cornersMaterial, Color.Lerp(ZumiDraw.Hover, Color.white, glow * 0.6f));
            var h = Guide.y / 2f - 0.012f;
            sweep.localPosition = new Vector3(0f, Mathf.Lerp(h, -h, ZumiFlowKit.Smooth(t)), -0.0007f);
            if (t < 1f) return;
            sweep.gameObject.SetActive(false);
            ZumiFlowKit.SetTint(outlineMaterial, outlineColour);
            ZumiFlowKit.SetTint(cornersMaterial, CornersColour);
            Shoot();
        }

        void Shoot()
        {
            var capture = taking;
            taking = null;
            capture.card = ZumiFlowKit.Card($"Scanned page {captures.Count + 1}", null, new Vector2(Guide.x, Guide.y), ZumiFlowKit.Picture(capture.texture, Color.white, 3250)).transform;
            // it starts where the page lies, a breath above the guide, and flies onto the stack
            capture.card.SetPositionAndRotation(guide.position - guide.forward * 0.004f, guide.rotation);
            captures.Add(capture);
            flying = capture;
            flyFrom = new Pose(capture.card.position, capture.card.rotation);
            flyFromScale = capture.card.localScale;
            // the line has done its work
            CancelInvoke(nameof(HideRefusal));
            caption.Hide();
            State = "flying";
            stateSince = Time.time;
            Debug.Log($"[ZumiScan] page added: {captures.Count} on the stack ({capture.source}, {LastCaptureTrigger})");
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
            if (undoDisc != null && undoDisc.root) undoDisc.root.gameObject.SetActive(captures.Count > 0);
            if (doneWanted && captures.Count > 0)
            {
                Finish();
                return;
            }
            doneWanted = false;
            Ready();
        }

        // ---- undo: the last page comes off the stack --------------------------------------------------------------

        void PressUndo(string how)
        {
            Debug.Log($"[ZumiScan] undo disc pressed ({how}), state {State}, {captures.Count} pages");
            if (State != "ready" || captures.Count == 0) return;
            undoDisc.pressedAt = Time.time;
            removing = captures[^1];
            captures.RemoveAt(captures.Count - 1);
            flyFrom = new Pose(removing.card.position, removing.card.rotation);
            flyFromScale = removing.card.localScale;
            State = "undoing";
            stateSince = Time.time;
            Debug.Log($"[ZumiScan] undo: page {captures.Count + 1} taken off the stack, {captures.Count} left");
        }

        /// <summary>Takes the last page off the stack, as the undo disc does (for tools and tests).</summary>
        public void Undo() => PressUndo("tool");

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
        // toward the far edge. The image is from the frame before (the texture is filled on the render thread).
        Vector2[] GuideInImage(out Pose pose)
        {
            pose = cameraAccess.GetCameraPose();
            float w = Guide.x / 2f, h = Guide.y / 2f;
            var corners = new[] { new Vector3(-w, -h), new Vector3(w, -h), new Vector3(w, h), new Vector3(-w, h) };
            var uv = new Vector2[4];
            for (var i = 0; i < 4; i++) uv[i] = cameraAccess.WorldToViewportPoint(guide.TransformPoint(corners[i]), pose);
            return uv;
        }

        // the page drawn upright, full size, from the guide's corners in the camera image
        Texture Straighten(out string problem)
        {
            problem = null;
            var image = cameraAccess.GetTexture();
            if (!image)
            {
                problem = "camera texture null";
                return null;
            }
            Debug.Log($"[ZumiScan] camera texture ready {image.width}x{image.height}");
            var uv = GuideInImage(out _);
            if (!warp) warp = new Material(ZumiFlowKit.WarpShader);
            SetHomography(warp, uv);
            var rt = new RenderTexture(Mathf.RoundToInt(CaptureHeight * Guide.x / Guide.y), CaptureHeight, 0, RenderTextureFormat.ARGB32) { name = $"capture {captures.Count + 1}", wrapMode = TextureWrapMode.Clamp };
            rt.Create();
            Graphics.Blit(image, rt, warp);
            Debug.Log($"[ZumiScan] warp done {rt.width}x{rt.height}, page corners in the camera image {uv[0]:F3} {uv[1]:F3} {uv[2]:F3} {uv[3]:F3}");
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
            if (cameraAccess) Destroy(cameraAccess);
        }

        void OnDestroy() => Close();
    }
}
