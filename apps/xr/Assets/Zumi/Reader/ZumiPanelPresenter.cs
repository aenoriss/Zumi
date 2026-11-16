using System;
using System.Collections.Generic;
using System.Threading;
using UnityEngine;

namespace Zumi
{
    /// <summary>
    /// Shows the panel the clock is on, and nothing else: no neighbours. Every panel is seen from its own camera
    /// point: its scene is scaled so its windows float ReadingDistance in front of the seat's eye, which makes each
    /// panel 55 degrees on its long side whatever its shape. The panel belongs to the seat, not the head: it stays
    /// where it is when the reader moves, and that is its parallax. This reads the clock every frame and never moves
    /// it: balloons, greyed frames and accents are what the clock's time says (ZumiPanelStage). Only a few panels
    /// exist at a time (the constants below): the one on the clock and the next, built ahead while the current one
    /// is read so the swap is a visibility switch, not a load. A panel that leaves that window is destroyed with its
    /// meshes and textures.
    /// </summary>
    [RequireComponent(typeof(ZumiSeat))]
    public class ZumiPanelPresenter : MonoBehaviour
    {
        /// <summary>Metres from the seat's eye to a panel's windows, the same for every panel: one scene unit. 1 m:
        /// the lettering sits near the headset's focal distance (about 1.3 m on Quest 3) and beyond arm's reach, so
        /// the hand menu (0.3 m) never meets it, and the layers behind the window land 1 to 3 m away, where the eyes'
        /// convergence and focus still agree. A panel's size in view does not depend on it (always 55 degrees); what
        /// it sets is how much a head move shifts the layers.</summary>
        public const float ReadingDistance = 1.0f;
        /// <summary>Panels after the one on the clock that are built ahead.</summary>
        public const int PrefetchAhead = 1;
        /// <summary>Panels before the one on the clock that are kept. None: going back loads again.</summary>
        public const int KeepBehind = 0;
        /// <summary>The most panels that exist at once, a load still in flight for a panel already left included.</summary>
        public const int MaxLoaded = 1 + PrefetchAhead + KeepBehind;
        const int AccentLogLength = 64;

        [Tooltip("Zumi/PanelWindow: each frame's window in a panel's scene")]
        [SerializeField] Shader windowShader;
        [Tooltip("Zumi/Card: each layer of a panel's scene")]
        [SerializeField] Shader cardShader;
        [Tooltip("Zumi/FrameShadow: a soft shadow round each frame, so the frames float in front of what is behind; none: no shadow")]
        [SerializeField] Shader frameShadowShader;
        [Tooltip("A frame the clock has not reached yet is drawn grey (as the browser viewer does); off: every frame is in its colours from the panel's start")]
        [SerializeField] bool greyFramesAhead = true;
        [Tooltip("The pipeline's accents (pop, cut, impact) play; off: nothing moves")]
        [SerializeField] bool motionEnabled = true;

        internal Shader WindowShader => windowShader;
        internal Shader CardShader => cardShader;

        sealed class Slot
        {
            public int index;
            public string id;
            public Transform root;
            public ZumiPanelScene scene;
            public ZumiPanelStage stage;
            public CancellationTokenSource loading;
            public bool failed;
            // left the window while its scene was still loading: it holds its place until the load has returned
            public bool dropped;
        }

        static readonly IReadOnlyList<string> None = Array.Empty<string>();

        IEpisodeSource source;
        ZumiTimeline timeline;
        IEpisodeClock clock;
        ZumiSeat seat;
        readonly List<Slot> slots = new();
        readonly List<string> loadedIds = new();
        readonly List<string> accentLog = new();
        readonly List<string> failedIds = new();
        Slot shownSlot;

        /// <summary>The panel the reader sees now; null while none is drawn.</summary>
        public string ShownPanelId => shownSlot?.id;
        /// <summary>Every panel that exists now, loading ones included, in panel order.</summary>
        public IReadOnlyList<string> LoadedPanelIds => loadedIds;
        public int LoadedCount => slots.Count;
        /// <summary>The panel on the clock is drawn, or never will be (it has no scene that loads).</summary>
        public bool CurrentSettled { get; private set; }
        /// <summary>The panel on the clock has no scene that loads: nothing of it is drawn (ZumiCards puts a plain
        /// card in its place), the clock keeps time and its voices go on.</summary>
        public bool CurrentFailed { get; private set; }
        /// <summary>Every panel that could not be shown since the episode opened, in the order it was found out.</summary>
        public IReadOnlyList<string> FailedPanelIds => failedIds;
        /// <summary>The shown panel's width and height at its windows, in metres; zero while none is drawn.</summary>
        public Vector2 ShownPanelMetres => shownSlot != null ? shownSlot.scene.PanelSize * PanelScale : Vector2.zero;

        /// <summary>The comfort switch: off, no accent plays and every layer rests.</summary>
        public bool MotionEnabled
        {
            get => motionEnabled;
            set => motionEnabled = value;
        }

        /// <summary>The open choice between "greyed ahead" (on) and "all frames lit" (off).</summary>
        public bool GreyFramesAhead
        {
            get => greyFramesAhead;
            set => greyFramesAhead = value;
        }

        // ---- read-only state of the panel on screen, for tests and tools ----------------------------------------

        /// <summary>Metres of one scene unit of the panel on screen (ReadingDistance); 0 while none is drawn.</summary>
        public float PanelScale => shownSlot != null ? shownSlot.scene.Root.lossyScale.x : 0f;
        /// <summary>Metres from the seat's eye to the shown panel's windows, measured on their meshes along the
        /// seat's forward; 0 while none is drawn.</summary>
        public float EyeDistance => WindowExtent(out var distance, out _, out _) ? distance : 0f;
        /// <summary>Degrees the shown panel's windows span on their long side, seen from the seat's eye, measured on
        /// their meshes. The frames' outer edges: at most the panel's 55, less by the page margin.</summary>
        public float WindowLongSideDegrees => WindowExtent(out _, out var across, out var up) ? Mathf.Max(across, up) : 0f;
        /// <summary>Degrees the whole panel spans on its long side from the seat's eye: the scene camera's field of
        /// view at the shown scale.</summary>
        public float PanelLongSideDegrees
        {
            get
            {
                if (shownSlot == null) return 0f;
                var size = shownSlot.scene.PanelSize * PanelScale;
                return 2f * Mathf.Atan(Mathf.Max(size.x, size.y) / 2f / Mathf.Max(EyeDistance, 1e-4f)) * Mathf.Rad2Deg;
            }
        }
        /// <summary>The middle of every panel: ReadingDistance straight ahead of the seat.</summary>
        public Vector3 PanelCentre => transform.TransformPoint(0f, 0f, ReadingDistance);
        public IReadOnlyList<string> VisibleBubbleIds => shownSlot?.stage.VisibleBubbleIds ?? None;
        public IReadOnlyList<string> LitBubbleIds => shownSlot?.stage.LitBubbleIds ?? None;
        public IReadOnlyList<string> FrameStates => shownSlot?.stage.FrameStates ?? None;
        public IReadOnlyList<string> ActiveTrackIds => shownSlot?.stage.ActiveTrackIds ?? None;
        public IReadOnlyList<string> FinishedTrackIds => shownSlot?.stage.FinishedTrackIds ?? None;
        /// <summary>The tracks that ran to their end, oldest first (the last 64): "panel/track kind on target
        /// (n nodes) peak p rest r".</summary>
        public IReadOnlyList<string> AccentLog => accentLog;
        /// <summary>How far the shown panel's layers are from rest right now: the largest offset in scene units plus
        /// the largest change of scale. 0 with nothing moving.</summary>
        public float Displacement
        {
            get
            {
                var most = 0f;
                if (shownSlot != null)
                    foreach (var node in shownSlot.scene.Nodes)
                        most = Mathf.Max(most, node.transform.localPosition.magnitude + (node.transform.localScale - Vector3.one).magnitude);
                return most;
            }
        }

        /// <summary>What the shown panel costs to draw: its layers that are drawn now (one draw each) and their triangles.</summary>
        public int ShownDrawCalls => Cost(false);
        public int ShownTriangles => Cost(true);

        int Cost(bool triangles)
        {
            var n = 0;
            if (shownSlot != null)
                foreach (var node in shownSlot.scene.Nodes)
                    foreach (var r in node.renderers)
                        if (r.enabled) n += triangles ? (int)(r.GetComponent<MeshFilter>().sharedMesh.GetIndexCount(0) / 3) : 1;
            return n;
        }

        public void Bind(IEpisodeSource source, ZumiTimeline timeline, IEpisodeClock clock)
        {
            this.source = source;
            this.timeline = timeline;
            this.clock = clock;
            seat = GetComponent<ZumiSeat>();
        }

        /// <summary>Where a card of a loaded panel is, in world space; false when that panel has no scene here.</summary>
        public bool TryCardCentre(string panelId, string card, out Vector3 world)
        {
            foreach (var slot in slots)
                if (slot.id == panelId && slot.stage != null) return slot.stage.TryCardCentre(card, out world);
            world = default;
            return false;
        }

        /// <summary>Where a frame's window of a loaded panel is, in world space; false when that panel has no scene
        /// here or no window for that frame.</summary>
        public bool TryFrameCentre(string panelId, int frame, out Vector3 world)
        {
            foreach (var slot in slots)
                if (slot.id == panelId && slot.stage != null) return slot.stage.TryFrameCentre(frame, out world);
            world = default;
            return false;
        }

        void Update()
        {
            if (clock == null) return;

            var current = timeline.IndexAt(clock.Time);
            int first = Mathf.Max(0, current - KeepBehind), last = Mathf.Min(timeline.Panels.Count - 1, current + PrefetchAhead);
            for (var i = slots.Count - 1; i >= 0; i--)
                if (slots[i].index < first || slots[i].index > last) Drop(slots[i]);
            // the panel on the clock first; the others only once it is drawn, so they never compete with it
            var currentSlot = Want(current);
            CurrentSettled = currentSlot != null && (currentSlot.scene != null || currentSlot.failed);
            CurrentFailed = currentSlot != null && currentSlot.failed;
            if (CurrentSettled)
                for (var i = first; i <= last; i++) Want(i);

            shownSlot = null;
            loadedIds.Clear();
            foreach (var slot in slots)
            {
                loadedIds.Add(slot.id);
                var visible = seat.Taken && slot == currentSlot && slot.scene != null;
                // before it is switched on: a panel never shows a frame of another time
                if (visible) slot.stage.Show(clock.Time, motionEnabled, greyFramesAhead);
                if (slot.root.gameObject.activeSelf != visible) slot.root.gameObject.SetActive(visible);
                if (visible) shownSlot = slot;
            }
        }

        Slot Want(int index)
        {
            if (index < 0) return null;
            foreach (var s in slots)
                if (s.index == index && !s.dropped) return s;
            if (slots.Count >= MaxLoaded) return null;
            var entry = timeline.Panels[index];
            var slot = new Slot { index = index, id = entry.id, root = new GameObject($"Panel {entry.id}").transform };
            slot.root.gameObject.SetActive(false);
            // at the seat's eye: the panel's scene is built around its own camera, which goes there
            slot.root.SetParent(transform, false);
            slots.Insert(slots.FindLastIndex(s => s.index < index) + 1, slot);
            Load(slot);
            return slot;
        }

        async void Load(Slot slot)
        {
            var panel = source.Manifest.panels[slot.index];
            slot.loading = new CancellationTokenSource();
            var cancel = slot.loading.Token;
            ZumiPanelScene scene = null;
            var why = string.IsNullOrEmpty(panel.scene) ? "it has no scene (only scene3d panels are shown)" : "its scene does not load";
            try
            {
                var glb = string.IsNullOrEmpty(panel.scene) ? null : await source.Read(panel.scene, cancel);
                if (glb == null && !string.IsNullOrEmpty(panel.scene)) why = $"{panel.scene} is not in the episode";
                if (glb != null && this && !cancel.IsCancellationRequested)
                    scene = await ZumiPanelScene.Load(glb, slot.root, ReadingDistance, windowShader, cardShader, frameShadowShader, cancel);
            }
            catch (OperationCanceledException) { }
            catch (Exception e)
            {
                why = e.Message;
            }
            slot.loading.Dispose();
            slot.loading = null;
            if (slot.dropped || !this)
            {
                scene?.Dispose();
                if (slot.root) Destroy(slot.root.gameObject);
                slots.Remove(slot);
                return;
            }
            slot.scene = scene;
            if (scene != null)
            {
                slot.stage = new ZumiPanelStage(scene, panel, timeline.Panels[slot.index].start) { TrackEnded = LogAccent };
                return;
            }
            slot.failed = true;
            if (!failedIds.Contains(slot.id)) failedIds.Add(slot.id);
            Debug.LogWarning($"[Zumi] reader: {slot.id} cannot be shown: {why}; a plain card stands in for it and the clock goes on");
        }

        void LogAccent(string line)
        {
            if (accentLog.Count >= AccentLogLength) accentLog.RemoveAt(0);
            accentLog.Add(line);
            Debug.Log($"[Zumi] motion: {line}");
        }

        // the shown panel's windows from the seat: how far they are, and the angles their outer edges span
        bool WindowExtent(out float distance, out float acrossDegrees, out float upDegrees)
        {
            distance = acrossDegrees = upDegrees = 0f;
            if (shownSlot == null) return false;
            var any = false;
            var box = new Bounds();
            var toSeat = transform.worldToLocalMatrix * shownSlot.scene.Root.localToWorldMatrix;
            foreach (var node in shownSlot.scene.Nodes)
            {
                if (node.kind != "window") continue;
                for (var corner = 0; corner < 8; corner++)
                {
                    var e = node.bounds.extents;
                    var p = toSeat.MultiplyPoint3x4(node.bounds.center + new Vector3((corner & 1) == 0 ? -e.x : e.x, (corner & 2) == 0 ? -e.y : e.y, (corner & 4) == 0 ? -e.z : e.z));
                    if (any) box.Encapsulate(p);
                    else box = new Bounds(p, Vector3.zero);
                    any = true;
                }
            }
            if (!any) return false;
            distance = box.center.z;
            acrossDegrees = (Mathf.Atan(box.max.x / distance) - Mathf.Atan(box.min.x / distance)) * Mathf.Rad2Deg;
            upDegrees = (Mathf.Atan(box.max.y / distance) - Mathf.Atan(box.min.y / distance)) * Mathf.Rad2Deg;
            return true;
        }

        void Drop(Slot slot)
        {
            if (slot.dropped) return;
            if (slot.loading != null)
            {
                slot.dropped = true;
                slot.loading.Cancel();
                return;
            }
            if (slot == shownSlot) shownSlot = null;
            slot.scene?.Dispose();
            Destroy(slot.root.gameObject);
            slots.Remove(slot);
        }

        // glTFast holds native buffers until disposed
        void OnDestroy()
        {
            foreach (var slot in slots.ToArray()) Drop(slot);
        }
    }
}
