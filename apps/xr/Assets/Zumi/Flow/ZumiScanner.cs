using System.Collections.Generic;
using Meta.XR;
using Meta.XR.MRUtilityKit;
using UnityEngine;
#if UNITY_ANDROID && !UNITY_EDITOR
using UnityEngine.Android;
#endif

namespace Zumi
{
    /// <summary>
    /// Load: the page scanner. A page-shaped guide (A4) lies on the desk: on the scanned table nearest the reader, by
    /// its edge nearest them; without a table the reader taps the desk once with a fingertip and the guide lies there.
    /// The reader lays a pencil page in it and presses Scan, a button on the desk to its right (the page count under
    /// it): a light sweeps the guide, then the passthrough camera's last image is straightened into an upright page
    /// (each corner of the guide projected into the image with the camera's pose and intrinsics, then a homography
    /// drawn by ZumiWarp into a page-shaped render texture). The page rises for review: OK sends it onto a stack
    /// floating beside the reader, Delete drops it. The reader scans as many pages as they have and presses Done
    /// under the stack. Without the camera (the permission refused, no camera, the editor) the making-of's pencil
    /// pages stand in for the captures, in order.
    /// </summary>
    public class ZumiScanner : MonoBehaviour
    {
        public const float DoneRadius = 0.03f;
        /// <summary>A4, metres.</summary>
        public static readonly Vector2 Guide = new(0.21f, 0.297f);
        /// <summary>The guide's near edge is this far in from the table's edge.</summary>
        public const float EdgeInset = 0.06f;
        /// <summary>A table farther than this from the head (on the floor's plane) is not the reader's desk.</summary>
        public const float MaxTableDistance = 1.6f;
        /// <summary>Seconds to wait for a tap before the guide lies where a desk would be.</summary>
        public const float TapWaitSeconds = 8f;
        public const float FlySeconds = 0.9f;
        /// <summary>The capture: the guide's outline brightens and a light sweeps it once, far edge to near.</summary>
        public const float SweepSeconds = 0.4f;
        /// <summary>The Scan button lies on the desk to the right of the guide: its radius, and the gap to the guide.</summary>
        public const float ScanRadius = 0.028f, ScanGap = 0.075f;
        /// <summary>Review: the page rises this high over the guide, at this scale, in this time; Delete drops it.</summary>
        public const float ReviewLift = 0.25f, ReviewScale = 0.75f, RiseSeconds = 0.6f, DiscardSeconds = 0.4f;
        /// <summary>The stack: metres ahead of the eye, to its left, below it; a stacked page's height.</summary>
        public const float StackAhead = 0.55f, StackSide = -0.36f, StackDrop = 0.12f, StackPageHeight = 0.2f;
        /// <summary>The straightened page's pixels.</summary>
        public const int CaptureHeight = 1000;
        const string CameraPermission = "horizonos.permission.HEADSET_CAMERA";

        // ---- read-only state for tests and tools -----------------------------------------------------------------
        /// <summary>"waiting_desk", "ready", "scanning", "rising", "review", "discarding", "flying", "done", "off".</summary>
        public string State { get; private set; } = "off";
        public int PagesCaptured => captures.Count;
        /// <summary>"table TABLE", "tap", "virtual": where the guide was laid.</summary>
        public string GuideSource { get; private set; }
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
        ZumiDraw.RoundButton scanButton;
        Material scanRing;
        static readonly Color RingColour = ZumiDraw.Hex(0xD9C7B4);
        Material outlineMaterial, cornersMaterial;
        Color outlineColour, cornersColour;
        Transform sweep;
        Pose head;
        // a fingertip's height, to find a tap
        readonly Queue<(float t, Vector3 p)> tip = new();
        Capture flying;
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
            data = await ZumiMakingOfData.Get();
            if (!this) return;
            if (!LayOnTable())
            {
                GuideSource = "tap";
                Debug.Log("[Zumi] scanner: no table near the reader; waiting for a tap on the desk");
                ShowTapHint();
            }
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

        bool LayOnTable()
        {
            var mruk = MRUK.Instance;
            var room = mruk && mruk.IsInitialized && mruk.Rooms.Count > 0 ? mruk.GetCurrentRoom() : null;
            if (!room) return false;
            RoomBox best = default;
            var found = false;
            var bestDistance = float.MaxValue;
            var eye = ZumiRoom.Flat(head.position);
            foreach (var anchor in room.Anchors)
            {
                if (!anchor.VolumeBounds.HasValue || !anchor.Label.ToString().Contains("TABLE")) continue;
                var box = ZumiRoom.Box(anchor);
                var d = box.Distance(eye);
                if (d < bestDistance && d < MaxTableDistance && box.top < head.position.y - 0.15f)
                {
                    best = box;
                    bestDistance = d;
                    found = true;
                }
            }
            if (!found) return false;
            // the point of the table's top nearest the reader, then in by the guide's half length and a margin
            var axis = best.footAxis;
            var perp = ZumiRoom.Perp(axis);
            var rel = eye - best.footCentre;
            var near = best.footCentre + axis * Mathf.Clamp(Vector2.Dot(rel, axis), -best.footHalf.x, best.footHalf.x)
                       + perp * Mathf.Clamp(Vector2.Dot(rel, perp), -best.footHalf.y, best.footHalf.y);
            var inward = (best.footCentre - near).sqrMagnitude > 1e-6f ? (best.footCentre - near).normalized : -(eye - near).normalized;
            var centre = near + inward * (Guide.y / 2f + EdgeInset);
            // the page's top points away from the reader
            var away = centre - eye;
            Lay(new Vector3(centre.x, best.top + 0.002f, centre.y), new Vector3(away.x, 0f, away.y), "table " + best.label);
            return true;
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
            // the four corners as brackets, amber, and a faint outline between them
            var marks = new List<Vector2[]>();
            foreach (var (sx, sy) in new[] { (-1, -1), (1, -1), (1, 1), (-1, 1) })
            {
                marks.Add(ZumiDraw.Box(sx < 0 ? -w : w - corner, sy < 0 ? -h : h - t, corner, t));
                marks.Add(ZumiDraw.Box(sx < 0 ? -w : w - t, sy < 0 ? -h : h - corner, t, corner));
            }
            cornersColour = ZumiDraw.Hover;
            cornersMaterial = ZumiDraw.Shape(flat, guideParts, "Corners", guide, -0.0005f, cornersColour, 1, marks.ToArray()).GetComponent<MeshRenderer>().sharedMaterial;
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
            State = "ready";
            stateSince = Time.time;
            Debug.Log($"[Zumi] scanner: guide laid on {source} at {at:F2}");
        }

        Transform tapHint;
        readonly ZumiDraw.Parts hintParts = new() { blended = true, queue = 3200 };

        void ShowTapHint()
        {
            tapHint = new GameObject("Tap hint").transform;
            var at = head.position + head.rotation * new Vector3(0f, -0.2f, 0.6f);
            tapHint.SetPositionAndRotation(at, ZumiFlowKit.Facing(at, head.position));
            const string text = "Tap your desk once with a fingertip";
            ZumiDraw.Shape(flat, hintParts, "Plate", tapHint, 0f, ZumiDraw.Plate, 0, ZumiDraw.Rounded(ZumiDraw.Width(text, 0.014f) + 0.05f, 0.05f, 0.025f));
            ZumiDraw.Text(flat, hintParts, "Line", tapHint, new Vector3(0f, 0f, -0.002f), 0.014f, ZumiDraw.Ink, 2, text);
        }

        void HideTapHint()
        {
            if (tapHint) Destroy(tapHint.gameObject);
            hintParts.Destroy();
        }

        // a fingertip that came down fast and stopped, well below the eyes
        bool Tapped(out Vector3 at)
        {
            at = default;
            var now = Time.time;
            Vector3? lowest = null;
            foreach (var p in pinch.Tips())
                if (lowest == null || p.y < lowest.Value.y) lowest = p;
            if (lowest == null) return false;
            tip.Enqueue((now, lowest.Value));
            while (tip.Count > 0 && now - tip.Peek().t > 0.4f) tip.Dequeue();
            if (tip.Count < 4) return false;
            var first = tip.Peek();
            var drop = first.p.y - lowest.Value.y;
            var still = true;
            var arr = tip.ToArray();
            for (var i = arr.Length - 1; i >= 0 && now - arr[i].t < 0.08f; i--)
                if (Mathf.Abs(arr[i].p.y - lowest.Value.y) > 0.004f) still = false;
            if (drop > 0.04f && still && lowest.Value.y < head.position.y - 0.3f)
            {
                at = lowest.Value;
                tip.Clear();
                return true;
            }
            return false;
        }

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
            // a page under review is answered first (OK or Delete)
            if (captures.Count == 0 || State is not ("ready" or "flying")) return;
            Debug.Log($"[Zumi] scanner: done, {captures.Count} pages");
            if (State == "flying") doneWanted = true;
            else Finish();
        }

        /// <summary>Ends the scan now, as Done does (for tools and tests).</summary>
        public void Done() => PressDone();

        void Finish()
        {
            State = "done";
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

        // ---- capture -------------------------------------------------------------------------------------------

        void Update()
        {
            if (State == "off" || State == "done") return;
            switch (State)
            {
                case "waiting_desk":
                    if (data == null) break;
                    if (Tapped(out var at))
                    {
                        HideTapHint();
                        var away = Vector3.ProjectOnPlane(at - head.position, Vector3.up);
                        // the tap is the guide's near edge
                        Lay(at + away.normalized * (Guide.y / 2f) + Vector3.up * 0.002f, away, "tap");
                    }
                    else if (Time.time - stateSince > TapWaitSeconds)
                    {
                        HideTapHint();
                        var desk = head.position + head.rotation * new Vector3(0f, -0.55f, 0.45f);
                        Lay(desk, head.rotation * Vector3.forward, "virtual");
                    }
                    break;
                case "scanning":
                    Sweep();
                    break;
                case "rising":
                    Rise();
                    break;
                case "review":
                    if (pending != null && pending.card) pending.card.position = reviewPose.position + Vector3.up * (Mathf.Sin((Time.time - stateSince) * 1.6f) * 0.003f);
                    break;
                case "discarding":
                    Discarding();
                    break;
                case "flying":
                    Fly();
                    break;
            }
        }

        // ---- review: the page just taken, held up over the guide, with OK and Delete ----------------------------

        Capture pending;
        Pose reviewPose;
        Transform review;
        readonly ZumiDraw.Parts reviewParts = new() { blended = true, queue = 3300 };

        /// <summary>The page held for review: over the guide, tipped up toward the eyes.</summary>
        Pose ReviewPose()
        {
            var eye = head.position;
            var at = guide.position + Vector3.up * ReviewLift + Vector3.ProjectOnPlane(eye - guide.position, Vector3.up).normalized * 0.06f;
            return new Pose(at, ZumiFlowKit.Facing(at, eye));
        }

        void Rise()
        {
            var t = (Time.time - stateSince) / RiseSeconds;
            var k = ZumiFlowKit.Smooth(t);
            pending.card.SetPositionAndRotation(Vector3.Lerp(flyFrom.position, reviewPose.position, k), Quaternion.Slerp(flyFrom.rotation, reviewPose.rotation, k));
            pending.card.localScale = Vector3.Lerp(new Vector3(Guide.x, Guide.y, 1f), new Vector3(Guide.x, Guide.y, 1f) * ReviewScale, k);
            if (t < 1f) return;
            State = "review";
            stateSince = Time.time;
            ShowReview(true);
        }

        void ShowReview(bool on)
        {
            // the page under review answers first: the scan disc and its count step aside meanwhile
            if (scanButton != null) scanButton.transform.gameObject.SetActive(!on);
            if (counter) counter.gameObject.SetActive(!on);
            if (!on)
            {
                if (review) Destroy(review.gameObject);
                reviewParts.Destroy();
                return;
            }
            review = new GameObject("Review").transform;
            review.SetPositionAndRotation(reviewPose.position, reviewPose.rotation);
            // beside the page on the right (the side of the right hand and the scan disc), OK above Delete, off the
            // page and off the guide under it
            var x = Guide.x * ReviewScale / 2f + 0.045f;
            var ok = ZumiDraw.Round(flat, reviewParts, "OK", review, new Vector2(x, 0.06f), DoneRadius, 1, Keep);
            ZumiDraw.Shape(flat, reviewParts, "Tick", ok.transform, -0.002f, ZumiDraw.Ink, 2, Tick());
            ZumiDraw.Text(flat, reviewParts, "OK label", review, new Vector3(x, 0.06f - DoneRadius - 0.014f, -0.002f), 0.012f, ZumiDraw.Ink, 2, "OK");
            var del = ZumiDraw.Round(flat, reviewParts, "Delete", review, new Vector2(x, -0.025f), DoneRadius, 1, Discard);
            ZumiDraw.Shape(flat, reviewParts, "Cross", del.transform, -0.002f, ZumiDraw.Ink, 2, Bar(45f), Bar(-45f));
            ZumiDraw.Text(flat, reviewParts, "Delete label", review, new Vector3(x, -0.025f - DoneRadius - 0.014f, -0.002f), 0.012f, ZumiDraw.Ink, 2, "Delete");
            okButton = ok;
            deleteButton = del;
        }

        ZumiDraw.RoundButton okButton, deleteButton;

        static Vector2[] Bar(float degrees)
        {
            var r = Quaternion.Euler(0f, 0f, degrees);
            var box = ZumiDraw.Box(-0.012f, -0.0018f, 0.024f, 0.0036f);
            for (var i = 0; i < box.Length; i++) box[i] = r * box[i];
            return box;
        }

        static Vector2[][] Tick() => new[]
        {
            new[] { new Vector2(-0.013f, 0.001f), new Vector2(-0.009f, 0.005f), new Vector2(-0.003f, -0.002f), new Vector2(-0.006f, -0.008f) },
            new[] { new Vector2(-0.006f, -0.008f), new Vector2(-0.003f, -0.002f), new Vector2(0.011f, 0.012f), new Vector2(0.014f, 0.008f) },
        };

        /// <summary>OK: the page under review goes onto the stack (for tools and tests as well).</summary>
        public void Keep()
        {
            if (State != "review" || pending == null) return;
            ShowReview(false);
            captures.Add(pending);
            flying = pending;
            pending = null;
            flyFrom = new Pose(flying.card.position, flying.card.rotation);
            flyFromScale = flying.card.localScale;
            State = "flying";
            stateSince = Time.time;
            Debug.Log($"[Zumi] scanner: page {captures.Count} kept ({flying.source})");
        }

        /// <summary>Delete: the page under review is dropped, and the reader scans it again.</summary>
        public void Discard()
        {
            if (State != "review" || pending == null) return;
            ShowReview(false);
            State = "discarding";
            stateSince = Time.time;
            flyFrom = new Pose(pending.card.position, pending.card.rotation);
            Debug.Log("[Zumi] scanner: page deleted");
        }

        void Discarding()
        {
            var t = (Time.time - stateSince) / DiscardSeconds;
            var k = ZumiFlowKit.Smooth(t);
            pending.card.position = flyFrom.position + Vector3.down * 0.08f * k;
            pending.card.localScale = new Vector3(Guide.x, Guide.y, 1f) * ReviewScale * (1f - 0.6f * k);
            var m = pending.card.GetComponent<MeshRenderer>().sharedMaterial;
            ZumiFlowKit.SetTint(m, new Color(1f, 1f, 1f, 1f - k));
            if (t < 1f) return;
            Destroy(m);
            Destroy(pending.card.gameObject);
            // a camera capture is this page's own; a stand-in is the bundle's
            if (pending.source == "camera" && pending.texture is RenderTexture rt) Destroy(rt);
            pending = null;
            State = "ready";
            stateSince = Time.time;
        }

        void PressScan()
        {
            if (State != "ready") return;
            State = "scanning";
            stateSince = Time.time;
            sweep.gameObject.SetActive(true);
            Debug.Log("[Zumi] scanner: scan");
        }

        /// <summary>Scans the page in the guide, as the Scan button does (for tools and tests).</summary>
        public void Scan() => PressScan();

        // the outline lights up, a band of light passes over the page, far edge to near, and the page is taken
        void Sweep()
        {
            var t = (Time.time - stateSince) / SweepSeconds;
            var glow = Mathf.Sin(Mathf.Clamp01(t) * Mathf.PI);
            ZumiFlowKit.SetTint(outlineMaterial, Color.Lerp(outlineColour, ZumiDraw.Hover, glow));
            ZumiFlowKit.SetTint(cornersMaterial, Color.Lerp(cornersColour, Color.white, glow * 0.6f));
            var h = Guide.y / 2f - 0.012f;
            sweep.localPosition = new Vector3(0f, Mathf.Lerp(h, -h, ZumiFlowKit.Smooth(t)), -0.0007f);
            // the press: the disc dips a few millimetres (the guide's +z is down) and its ring flashes once
            var press = Mathf.Sin(Mathf.Clamp01(t * 1.6f) * Mathf.PI);
            var p = scanButton.transform.localPosition;
            scanButton.transform.localPosition = new Vector3(p.x, p.y, -0.001f + 0.004f * press);
            scanRing.SetColor("_Color", Color.Lerp(RingColour, ZumiDraw.Hover, press));
            if (t < 1f) return;
            scanButton.transform.localPosition = new Vector3(p.x, p.y, -0.001f);
            scanRing.SetColor("_Color", RingColour);
            sweep.gameObject.SetActive(false);
            ZumiFlowKit.SetTint(outlineMaterial, outlineColour);
            ZumiFlowKit.SetTint(cornersMaterial, cornersColour);
            State = "ready";
            Shoot();
        }

        void Shoot()
        {
            if (State != "ready") return;
            var texture = CameraPlaying ? Straighten() : null;
            var source = texture ? "camera" : "fallback";
            if (!texture && data != null && data.pages.Count > 0) texture = data.pages[captures.Count % data.pages.Count].pencilTexture;
            LastCaptureSource = source;
            var capture = new Capture { texture = texture, source = source };
            var size = new Vector2(Guide.x, Guide.y);
            capture.card = ZumiFlowKit.Card($"Scanned page {captures.Count + 1}", null, size, ZumiFlowKit.Picture(texture, Color.white, 3250)).transform;
            // it starts where the page lies, a breath above the guide, and rises to be reviewed
            capture.card.SetPositionAndRotation(guide.position - guide.forward * 0.004f, guide.rotation);
            pending = capture;
            flyFrom = new Pose(capture.card.position, capture.card.rotation);
            reviewPose = ReviewPose();
            // the line has done its work, and the page under review is where it stood
            caption.Hide();
            State = "rising";
            stateSince = Time.time;
            Debug.Log($"[Zumi] scanner: page {captures.Count + 1} captured ({source}), for review");
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
            counter.text = Count(captures.Count);
            flying = null;
            if (doneButton) doneButton.gameObject.SetActive(true);
            if (doneWanted)
            {
                Finish();
                return;
            }
            State = "ready";
            stateSince = Time.time;
        }

        /// <summary>Takes the bundle's pages left at once and ends the scan (the flow's skip).</summary>
        public void FillRemaining()
        {
            DropPending();
            if (State is "rising" or "review" or "discarding")
            {
                State = "ready";
                stateSince = Time.time;
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
            if (State == "flying") doneWanted = true;
            else if (captures.Count > 0) Finish();
        }

        void DropPending()
        {
            ShowReview(false);
            if (pending == null) return;
            if (pending.card)
            {
                Destroy(pending.card.GetComponent<MeshRenderer>().sharedMaterial);
                Destroy(pending.card.gameObject);
            }
            if (pending.source == "camera" && pending.texture is RenderTexture rt) Destroy(rt);
            pending = null;
        }

        // The guide's corners, projected into the camera image with its pose and intrinsics, and the page drawn
        // upright from them. The image is from the frame before (the texture is filled on the render thread).
        Texture Straighten()
        {
            var image = cameraAccess.GetTexture();
            if (!image) return null;
            var pose = cameraAccess.GetCameraPose();
            // page (u, v): (0, 0) the near left corner as the reader sees it, v toward the far edge
            float w = Guide.x / 2f, h = Guide.y / 2f;
            var corners = new[] { new Vector3(-w, -h), new Vector3(w, -h), new Vector3(w, h), new Vector3(-w, h) };
            var uv = new Vector2[4];
            for (var i = 0; i < 4; i++) uv[i] = cameraAccess.WorldToViewportPoint(guide.TransformPoint(corners[i]), pose);
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
            if (guide) Destroy(guide.gameObject);
            guideParts.Destroy();
            HideTapHint();
            if (stack) Destroy(stack.gameObject);
            stackParts.Destroy();
            doneParts.Destroy();
            DropPending();
            if (cameraAccess) Destroy(cameraAccess);
        }

        void OnDestroy() => Close();
    }
}
