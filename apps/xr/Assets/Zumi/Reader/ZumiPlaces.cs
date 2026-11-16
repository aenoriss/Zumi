using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.Profiling;
using UnityEngine.Rendering;
using Zumi.Format;
using static System.FormattableString;

namespace Zumi
{
    /// <summary>What the place does to the reader's room: everything; no grade of the real room (the place and its
    /// props stay); or nothing in the room at all (no grade, no props: only the place beyond the wall stays).</summary>
    public enum RoomEffects { Full, NoGrade, Off }

    /// <summary>
    /// Shows the place the episode is in (episode.places) through the room, and its props in it. Like the panel, it
    /// reads the clock and never moves it: which place is open and how far, is what the clock's time says.
    ///
    /// The timeline names the place at t; outside it no place is open. A frame without a setting changes nothing: the
    /// timeline alone decides. A change fades the open place out over places.fade seconds from the change, then the
    /// next one in over the same time; the first place, and one after a gap, fades in from its start.
    ///
    /// A place is seen through the room's openings (ZumiRoom.Portals: the walls ahead and the ceiling, never the floor;
    /// without a scanned room one window behind the panel). They mark the stencil, the place's two meshes draw where it
    /// is marked: no render target, a few rectangles and two draws. The meshes are fitted to the room as the format
    /// rules: their origin at the seat's eye, -z to the key wall, then every vertex sent where ZumiPlaceWarp shows it
    /// (the picture's core zoomed to fit the key wall, the rest following the walls, nothing on floor or ceiling),
    /// at a depth that puts 95 % of what shows beyond the room's edge, the back layer kept beyond it, what is still
    /// inside the room not drawn, and the view fading out toward the edges of its measured span. Scanned furniture
    /// hides the place behind it, as boxes.
    ///
    /// When the clock has ended the last place closes over places.fade, on the time since the end
    /// (IEpisodeClock.EndedFor). A place or a prop that does not load is left out and nothing else changes
    /// (FailedPlaceIds, FailedPropNames).
    ///
    /// Places load as panels do: the open one and the next in the timeline, the rest freed. A place's props load with
    /// it, are placed once per fit by ZumiPropPlacer and fade in and out with it.
    /// </summary>
    [RequireComponent(typeof(ZumiRoom), typeof(ZumiSeat))]
    public class ZumiPlaces : MonoBehaviour
    {
        /// <summary>Metres beyond the room's edge the place starts at (the format's rule).</summary>
        public const float WallMargin = 0.25f;
        /// <summary>Metres beyond the room's edge the back layer is kept at (the format's rule).</summary>
        public const float BackMargin = 0.1f;
        /// <summary>The share of the view the scale puts beyond the room's edge: of what shows of it, each direction
        /// counted by how much of it shows (the vignette).</summary>
        public const float BeyondShare = 0.95f;
        /// <summary>The depth factor is worked out on every fifth vertex of the front mesh.</summary>
        public const int ScaleSampleStride = 5;
        /// <summary>Across, the view is whole out to this share of the way to the edge of its span, then fades: its core.</summary>
        public const float VignetteFull = ZumiPlaceWarp.CoreShare;
        /// <summary>Up and down, the view is whole until this many degrees of picture from the edge of its span: the fit
        /// puts that edge on the floor line and on the top of the wall, so the soft edge is short.</summary>
        public const float VignetteVerticalDegrees = 6f;
        /// <summary>The fade reaches nothing this many degrees inside the measured span: the mesh's rim is ragged.</summary>
        public const float VignetteInsetDegrees = 5f;
        /// <summary>Metres an opening floats off its wall, toward the room.</summary>
        public const float OpeningInset = 0.004f;
        /// <summary>Without a scanned room: metres over which the place fades toward the window's edge.</summary>
        public const float WindowEdge = 0.25f;
        /// <summary>Places that exist at once: the open one and the next.</summary>
        public const int MaxLoaded = 2;
        /// <summary>A prop's contact shadow at its darkest, for an occlusion of 0 and of 1.</summary>
        public const float ShadowMin = 0.3f, ShadowMax = 0.8f;
        const int LogLength = 32;

        [SerializeField] Shader portalShader;
        [SerializeField] Shader placeShader;
        [SerializeField] Shader propShader;
        [SerializeField] Shader shadowShader;
        [Tooltip("Full: the place, its props and its light on the real room. NoGrade: the real room keeps its own colours. Off: no props either; only the place beyond the wall stays")]
        [SerializeField] RoomEffects roomEffects = RoomEffects.Full;

        sealed class Prop
        {
            public PlaceProp data;
            public ZumiGlb glb;
            public Mesh mesh;
            public Texture2D texture;
            public Material material, shadowMaterial;
            public Transform root, shadow;
            public Renderer renderer, shadowRenderer;
            public float scale, radius;
            public ZumiPropPlacer.Result placement;
            // read back from where it stands
            public string on;
            public float baseError, outside, panelClearance, seatClearance;
        }

        sealed class Slot
        {
            public PlaceMesh place;
            public CancellationTokenSource loading;
            public bool ready, failed, dropped, fitting;
            public Transform root;
            public ZumiGlb front, back;
            public Mesh frontMesh, backMesh;
            public Texture2D frontTexture, backTexture;
            public Material frontMaterial, backMaterial;
            public int fitSerial = -1;
            public float scale, clipped;
            public readonly List<Prop> props = new();
        }

        static readonly int Opacity = Shader.PropertyToID("_Opacity");
        static readonly int Strength = Shader.PropertyToID("_Strength");
        static readonly IReadOnlyList<string> None = Array.Empty<string>();

        IEpisodeSource source;
        Places places;
        IEpisodeClock clock;
        ZumiRoom room;
        ZumiSeat seat;
        readonly Dictionary<string, PlaceMesh> known = new();
        readonly List<Slot> slots = new();
        readonly List<string> loadedIds = new(), shownLog = new(), propLines = new(), placedNames = new(), unplacedLines = new(), offKind = new(), unsupported = new();
        readonly List<string> failedPlaces = new(), failedProps = new();
        readonly List<string> wanted = new(MaxLoaded);
        Slot open, described;
        int describedSerial = -1;
        Transform stage, openings;
        Material openingMaterial, farMaterial, occluderMaterial;
        Mesh quad;
        int openingsSerial = -1;
        string lastOpenId;

        // ---- read-only state for tests and tools ---------------------------------------------------------------

        /// <summary>The place the timeline names at the clock's time; null outside the timeline.</summary>
        public string TimelinePlaceId { get; private set; }
        /// <summary>The place the reader sees now; null while none is drawn.</summary>
        public string OpenPlaceId => open?.place.setting;
        /// <summary>How much of it: 0 to 1.</summary>
        public float Fade { get; private set; }
        /// <summary>Every place that exists now, loads in flight included.</summary>
        public IReadOnlyList<string> LoadedPlaceIds => loadedIds;
        /// <summary>Each time the place on show changed: "setting@clock", "none@clock" when it closed (the last 32).</summary>
        public IReadOnlyList<string> ShownLog => shownLog;
        /// <summary>The places that did not load since the episode opened: none of them is shown, the room stays as it is.</summary>
        public IReadOnlyList<string> FailedPlaceIds => failedPlaces;
        /// <summary>The props that did not load, as "place/prop": left out, their place and its other props stand.</summary>
        public IReadOnlyList<string> FailedPropNames => failedProps;
        /// <summary>The factor the open place's meshes are scaled by; 0 while none is drawn.</summary>
        public float Scale => open?.scale ?? 0f;
        /// <summary>The share of the open place's front vertices that fall inside the room and are not drawn.</summary>
        public float ClippedShare => open?.clipped ?? 0f;
        /// <summary>How many of the room's openings are drawn now.</summary>
        public int OpeningsShown => openings && openings.gameObject.activeSelf ? room.PortalCount : 0;
        public RoomEffects RoomEffects
        {
            get => roomEffects;
            set => roomEffects = value;
        }
        public string RoomEffectsName => roomEffects.ToString();
        /// <summary>The open place's light; null while none is drawn or the file gives none.</summary>
        public PlaceLight OpenLight => open?.place.light;

        /// <summary>Triangles of the open place's two meshes and of its props on show.</summary>
        public int Triangles
        {
            get
            {
                if (open == null) return 0;
                var n = (open.front.triangles.Length + (open.back?.triangles.Length ?? 0)) / 3;
                foreach (var prop in open.props) if (prop.renderer.enabled) n += prop.glb.triangles.Length / 3;
                return n;
            }
        }
        /// <summary>Draws the open place adds: its two meshes, two per opening, one per furniture box, two per prop.</summary>
        public int DrawCalls => open == null ? 0 : 2 + 2 * room.PortalCount + room.Boxes.Count + 2 * PropsShown;
        /// <summary>Bytes of the open place's two textures, and of its props' textures.</summary>
        public long PlaceTextureBytes => open == null ? 0 : Profiler.GetRuntimeMemorySizeLong(open.frontTexture) + (open.backTexture ? Profiler.GetRuntimeMemorySizeLong(open.backTexture) : 0);
        /// <summary>The open place's front texture as it is held: "2160x1072 RGB24, 6.9 MB on the GPU" (width times
        /// height times the format's bytes; the profiler's figure above also counts the editor's own copy).</summary>
        public string PlaceTextureInfo
        {
            get
            {
                if (open == null) return null;
                var t = open.frontTexture;
                var bytes = (long)t.width * t.height * (t.format == TextureFormat.RGB24 ? 3 : 4);
                return Invariant($"{t.width}x{t.height} {t.format}, {bytes / 1048576f:F1} MB on the GPU, mips {t.mipmapCount}");
            }
        }
        public long PropTextureBytes
        {
            get
            {
                long n = 0;
                if (open != null) foreach (var prop in open.props) n += Profiler.GetRuntimeMemorySizeLong(prop.texture);
                return n;
            }
        }

        /// <summary>One line per prop of the open place: where it stands, or why it does not.</summary>
        public IReadOnlyList<string> PropLines => open != null ? propLines : None;
        public IReadOnlyList<string> PlacedPropNames => open != null ? placedNames : None;
        public IReadOnlyList<string> UnplacedPropLines => open != null ? unplacedLines : None;
        /// <summary>Placed props that stand on another kind of surface than the file names (a shelf prop on a table top).</summary>
        public IReadOnlyList<string> PropsOffKind => open != null ? offKind : None;
        /// <summary>Placed props with nothing under them, or on a kind of surface above their own (a floor prop on a
        /// table): the rule allows neither.</summary>
        public IReadOnlyList<string> PropsUnsupported => open != null ? unsupported : None;
        /// <summary>How many props are drawn now.</summary>
        public int PropsShown
        {
            get
            {
                var n = 0;
                if (open != null) foreach (var prop in open.props) if (prop.renderer.enabled) n++;
                return n;
            }
        }
        /// <summary>How much of the props shows: the place's fade, 0 with room effects off.</summary>
        public float PropOpacity { get; private set; }
        /// <summary>Over the placed props, read back from where their meshes are: the largest gap between a prop's base
        /// and the surface under it; the furthest a base corner is off that surface; the least distance from a prop's
        /// box to the panel's rectangle and from its footprint to the seat's volume (negative inside it); the least gap
        /// between two props' footprint circles. With no prop placed: 0, 0 and 99.</summary>
        public float PropBaseErrorMax { get; private set; }
        public float PropOutsideMax { get; private set; }
        public float PropPanelClearanceMin { get; private set; } = 99f;
        public float PropSeatClearanceMin { get; private set; } = 99f;
        public float PropGapMin { get; private set; } = 99f;

        public void Bind(IEpisodeSource source, ZumiManifest manifest, IEpisodeClock clock)
        {
            this.source = source;
            this.clock = clock;
            places = manifest.episode?.places;
            room = GetComponent<ZumiRoom>();
            seat = GetComponent<ZumiSeat>();
            if (places == null) return;
            foreach (var mesh in places.meshes) known[mesh.setting] = mesh;

            stage = new GameObject("Places").transform;
            openings = new GameObject("Openings").transform;
            openings.SetParent(stage, false);
            openings.gameObject.SetActive(false);
            quad = new Mesh { name = "opening" };
            quad.SetVertices(new[] { new Vector3(-0.5f, -0.5f), new Vector3(0.5f, -0.5f), new Vector3(-0.5f, 0.5f), new Vector3(0.5f, 0.5f) });
            quad.SetUVs(0, new[] { new Vector2(0f, 0f), new Vector2(1f, 0f), new Vector2(0f, 1f), new Vector2(1f, 1f) });
            quad.SetTriangles(new[] { 0, 2, 1, 2, 3, 1 }, 0);
            // the stencil's bits: 6 furniture, 7 the openings (the panel's frames keep 0 to 3)
            occluderMaterial = Marker("occluder", 2890, 64, 255, 64, CompareFunction.Always, StencilOp.Replace, CompareFunction.LessEqual, false, CullMode.Back, false);
            openingMaterial = Marker("opening", 2900, 128, 64, 128, CompareFunction.Equal, StencilOp.Replace, CompareFunction.LessEqual, false, CullMode.Off, false);
            farMaterial = Marker("far", 2901, 128, 128, 0, CompareFunction.Equal, StencilOp.Keep, CompareFunction.Always, true, CullMode.Off, true);
        }

        Material Marker(string name, int queue, int reference, int read, int write, CompareFunction comp, StencilOp pass, CompareFunction depth, bool depthWrite, CullMode cull, bool far)
        {
            var m = new Material(portalShader) { name = name, renderQueue = queue };
            m.SetFloat("_StencilRef", reference);
            m.SetFloat("_StencilRead", read);
            m.SetFloat("_StencilWrite", write);
            m.SetFloat("_StencilComp", (float)comp);
            m.SetFloat("_StencilPass", (float)pass);
            m.SetFloat("_ZTest", (float)depth);
            m.SetFloat("_ZWrite", depthWrite ? 1f : 0f);
            m.SetFloat("_Cull", (float)cull);
            m.SetFloat("_Far", far ? 1f : 0f);
            return m;
        }

        /// <summary>The place at t is drawn-ready, or never will be (the timeline names none, or it does not load):
        /// what the reader waits for before it starts the clock.</summary>
        public bool ReadyAt(double t)
        {
            if (places == null) return true;
            At(t, out var shown, out _);
            if (shown == null) return true;
            foreach (var slot in slots)
                if (slot.place.setting == shown && !slot.dropped) return slot.failed || (slot.ready && slot.fitSerial == room.Serial);
            return false;
        }

        // ---- the timeline --------------------------------------------------------------------------------------

        // the place on show at t and how much of it. A change at T: the one before fades out over [T, T + fade], the
        // next in over [T + fade, T + 2 fade]. Nothing before the first start; after an end with nothing following,
        // the place fades out from that end
        void At(double t, out string shown, out float opacity)
        {
            shown = null;
            opacity = 0f;
            var spans = places.timeline;
            var i = spans.Count - 1;
            while (i >= 0 && spans[i].start > t) i--;
            if (i < 0) return;
            var fade = Mathf.Max(places.fade, 1e-3f);
            var span = spans[i];
            if (t >= span.end)
            {
                var gone = (float)(t - span.end) / fade;
                if (gone >= 1f || !known.ContainsKey(span.setting)) return;
                shown = span.setting;
                opacity = 1f - gone;
                return;
            }
            var before = i > 0 && span.start - spans[i - 1].end < fade && known.ContainsKey(spans[i - 1].setting) ? spans[i - 1] : null;
            var from = (double)span.start;
            if (before != null && before.setting == span.setting) from = double.NegativeInfinity;
            else if (before != null)
            {
                var left = 1f - (float)(t - before.end) / fade;
                if (left > 0f)
                {
                    shown = before.setting;
                    opacity = left;
                    return;
                }
                from = before.end + fade;
            }
            if (!known.ContainsKey(span.setting)) return;
            shown = span.setting;
            opacity = Mathf.Clamp01((float)(t - from) / fade);
        }

        // the place the timeline holds at t (null in a gap), and the next different one after it
        void Spans(double t, out string now, out string next)
        {
            now = next = null;
            var spans = places.timeline;
            var i = 0;
            for (; i < spans.Count; i++)
            {
                if (spans[i].end <= t) continue;
                if (spans[i].start <= t) now = spans[i].setting;
                break;
            }
            for (var j = now != null ? i + 1 : i; j < spans.Count; j++)
                if (spans[j].setting != now && known.ContainsKey(spans[j].setting))
                {
                    next = spans[j].setting;
                    break;
                }
        }

        void Update()
        {
            if (clock == null || places == null || room.Serial == 0) return;
            var t = clock.Time;
            // the clock stops at the episode's end; the last place closes on the time since then
            var at = t + clock.EndedFor;
            At(at, out var shown, out var opacity);
            Spans(at, out var now, out var next);
            TimelinePlaceId = now;

            // what should exist, first things first: the place on show, the one the timeline holds, the next
            wanted.Clear();
            Wanted(shown);
            Wanted(now);
            Wanted(next);
            for (var i = slots.Count - 1; i >= 0; i--)
                if (!wanted.Contains(slots[i].place.setting)) Drop(slots[i]);
            Slot first = null;
            for (var i = 0; i < wanted.Count; i++)
            {
                // the others only once the first is there, so they never compete with it
                if (i > 0 && !(first != null && (first.ready || first.failed))) break;
                var slot = Want(wanted[i]);
                if (i == 0) first = slot;
            }

            loadedIds.Clear();
            open = null;
            foreach (var slot in slots)
            {
                loadedIds.Add(slot.place.setting);
                if (slot.dropped || !slot.ready) continue;
                if (slot.fitSerial != room.Serial && !slot.fitting) Fit(slot);
                var visible = slot.place.setting == shown && slot.fitSerial == room.Serial && opacity > 0.005f;
                if (slot.root.gameObject.activeSelf != visible) slot.root.gameObject.SetActive(visible);
                if (!visible) continue;
                open = slot;
                slot.frontMaterial.SetFloat(Opacity, opacity);
                if (slot.backMaterial) slot.backMaterial.SetFloat(Opacity, opacity);
            }
            Fade = open != null ? opacity : 0f;

            if (openingsSerial != room.Serial) BuildOpenings();
            if (openings.gameObject.activeSelf != (open != null)) openings.gameObject.SetActive(open != null);

            PropOpacity = open != null && roomEffects != RoomEffects.Off ? Fade : 0f;
            foreach (var slot in slots)
                foreach (var prop in slot.props)
                {
                    // a place still loading has props that are not built yet
                    if (!prop.renderer) continue;
                    var visible = slot == open && prop.placement is { placed: true } && PropOpacity > 0.005f;
                    if (prop.renderer.enabled != visible) prop.renderer.enabled = prop.shadowRenderer.enabled = visible;
                    if (!visible) continue;
                    prop.material.SetFloat(Opacity, PropOpacity);
                    prop.shadowMaterial.SetFloat(Strength, PropOpacity * Mathf.Lerp(ShadowMin, ShadowMax, slot.place.light?.occlusion ?? 0.5f));
                }

            if (OpenPlaceId != lastOpenId)
            {
                lastOpenId = OpenPlaceId;
                if (shownLog.Count >= LogLength) shownLog.RemoveAt(0);
                shownLog.Add(Invariant($"{lastOpenId ?? "none"}@{t:F2}"));
                Debug.Log(Invariant($"[Zumi] places: {lastOpenId ?? "none"} on show from {t:F2} s (the timeline holds {now ?? "none"})"));
            }
            if (open != null && (open != described || open.fitSerial != describedSerial)) Describe(open);
        }

        void Wanted(string id)
        {
            if (id != null && known.ContainsKey(id) && !wanted.Contains(id) && wanted.Count < MaxLoaded) wanted.Add(id);
        }

        // ---- loading -------------------------------------------------------------------------------------------

        Slot Want(string setting)
        {
            foreach (var s in slots)
                if (s.place.setting == setting && !s.dropped) return s;
            if (slots.Count >= MaxLoaded) return null;
            var slot = new Slot { place = known[setting], root = new GameObject($"Place {setting}").transform };
            slot.root.SetParent(stage, false);
            slot.root.gameObject.SetActive(false);
            slots.Add(slot);
            Load(slot);
            return slot;
        }

        async void Load(Slot slot)
        {
            slot.loading = new CancellationTokenSource();
            var cancel = slot.loading.Token;
            var place = slot.place;
            var started = Time.realtimeSinceStartupAsDouble;
            try
            {
                var frontFile = await source.Read(place.front, cancel);
                var backFile = string.IsNullOrEmpty(place.back) ? null : await source.Read(place.back, cancel);
                if (frontFile == null) throw new InvalidOperationException($"{place.front} is not in the episode");
                (slot.front, slot.back) = await Task.Run(() => (ZumiGlb.Read(frontFile), backFile != null ? ZumiGlb.Read(backFile) : null), cancel);
                // a prop that does not load is left out; its place and the other props stand
                foreach (var data in place.props)
                {
                    try
                    {
                        var file = await source.Read(data.model, cancel);
                        if (file == null) throw new InvalidOperationException($"{data.model} is not in the episode");
                        var prop = new Prop { data = data, glb = await Task.Run(() => ZumiGlb.Read(file), cancel) };
                        prop.texture = await Picture(prop.glb, data.name, true, cancel);
                        slot.props.Add(prop);
                    }
                    catch (OperationCanceledException)
                    {
                        throw;
                    }
                    catch (Exception e)
                    {
                        var name = $"{place.setting}/{data.name}";
                        if (!failedProps.Contains(name)) failedProps.Add(name);
                        Debug.LogWarning($"[Zumi] places: {name} cannot be shown ({e.Message}); the prop is left out");
                    }
                }
                // the pictures are decoded off the main thread: decoding one is the longest step by far
                slot.frontTexture = await Picture(slot.front, $"{place.setting} front", false, cancel);
                if (slot.back != null) slot.backTexture = await Picture(slot.back, $"{place.setting} back", false, cancel);
                // then the objects, on the main thread, one a frame
                if (this && !cancel.IsCancellationRequested)
                {
                    (slot.frontMesh, slot.frontMaterial) = Layer(slot, slot.front, slot.frontTexture, "front", 2902);
                    await Task.Yield();
                }
                if (this && !cancel.IsCancellationRequested && slot.back != null)
                {
                    (slot.backMesh, slot.backMaterial) = Layer(slot, slot.back, slot.backTexture, "back", 2903);
                    await Task.Yield();
                }
                foreach (var prop in slot.props)
                {
                    if (!this || cancel.IsCancellationRequested) break;
                    Build(prop);
                    await Task.Yield();
                }
                slot.ready = this && !cancel.IsCancellationRequested;
            }
            catch (OperationCanceledException) { }
            catch (Exception e)
            {
                // no place: the room stays as it is, and nothing waits for it
                slot.failed = true;
                if (!failedPlaces.Contains(place.setting)) failedPlaces.Add(place.setting);
                Debug.LogWarning($"[Zumi] places: {place.setting} cannot be shown ({e.Message}); the room stays as it is");
            }
            slot.loading.Dispose();
            slot.loading = null;
            if (slot.dropped || !this)
            {
                Free(slot);
                slots.Remove(slot);
                return;
            }
            if (slot.ready)
                Debug.Log(Invariant($"[Zumi] places: {place.setting} loaded in {Time.realtimeSinceStartupAsDouble - started:F2} s, {(slot.front.triangles.Length + (slot.back?.triangles.Length ?? 0)) / 3} triangles, {slot.props.Count} props"));
        }

        (Mesh, Material) Layer(Slot slot, ZumiGlb glb, Texture2D texture, string name, int queue)
        {
            var mesh = new Mesh { name = $"{slot.place.setting} {name}", indexFormat = glb.positions.Length > 65535 ? IndexFormat.UInt32 : IndexFormat.UInt16 };
            mesh.SetVertices(glb.positions);
            mesh.SetUVs(0, glb.uvs);
            mesh.SetTriangles(glb.triangles, 0, false);
            var material = new Material(placeShader) { name = mesh.name, mainTexture = texture, renderQueue = queue };
            material.SetFloat(Opacity, 0f);
            var go = new GameObject(name, typeof(MeshFilter), typeof(MeshRenderer));
            go.transform.SetParent(slot.root, false);
            go.GetComponent<MeshFilter>().sharedMesh = mesh;
            var renderer = go.GetComponent<MeshRenderer>();
            renderer.sharedMaterial = material;
            renderer.shadowCastingMode = ShadowCastingMode.Off;
            return (mesh, material);
        }

        // A model's picture as a texture. Texture2D.LoadImage decodes on the main thread (a 2160 x 1072 PNG stalls a
        // frame for tens of milliseconds, a place with five props seven times over), so the file goes through a
        // texture request instead, which decodes on a worker: written to the cache folder, read back, deleted.
        // A place's pictures get no mip chain: they are magnified on screen (about 15 texels a degree), and it is a
        // third less memory; a prop's get one.
        static async Task<Texture2D> Picture(ZumiGlb glb, string name, bool mips, CancellationToken cancel)
        {
            var image = glb.image;
            glb.image = null;
            if (image == null) return new Texture2D(1, 1, TextureFormat.RGB24, false) { name = name };
            var file = Path.Combine(Application.temporaryCachePath, $"zumi-{Guid.NewGuid():N}.img");
            try
            {
                await Task.Run(() => File.WriteAllBytes(file, image), cancel);
                var how = DownloadedTextureParams.Default;
                how.readable = false;
                how.mipmapChain = mips;
                how.linearColorSpace = false;
                using var request = UnityWebRequestTexture.GetTexture(new Uri(file), how);
                var sent = request.SendWebRequest();
                while (!sent.isDone) await Task.Yield();
                if (request.result != UnityWebRequest.Result.Success) throw new IOException($"{name}: {request.error}");
                var texture = DownloadHandlerTexture.GetContent(request);
                texture.name = name;
                texture.wrapMode = TextureWrapMode.Clamp;
                return texture;
            }
            finally
            {
                try { File.Delete(file); }
                catch (IOException) { }
            }
        }

        void Build(Prop prop)
        {
            var glb = prop.glb;
            prop.mesh = new Mesh { name = prop.data.name, indexFormat = glb.positions.Length > 65535 ? IndexFormat.UInt32 : IndexFormat.UInt16 };
            prop.mesh.SetVertices(glb.positions);
            prop.mesh.SetUVs(0, glb.uvs);
            prop.mesh.SetTriangles(glb.triangles, 0);
            // the models carry no normals; lit without them they come out black
            prop.mesh.RecalculateNormals();
            prop.material = new Material(propShader) { name = prop.data.name, mainTexture = prop.texture };
            prop.shadowMaterial = new Material(shadowShader) { name = $"{prop.data.name} shadow" };

            // its real height over the height of its box (the file's, which is the model's)
            var box = glb.bounds;
            var height = prop.data.bounds is { min: { Length: 3 }, max: { Length: 3 } } b ? b.max[1] - b.min[1] : box.size.y;
            prop.scale = prop.data.heightM / Mathf.Max(height, 1e-4f);
            prop.radius = prop.scale * Mathf.Max(box.extents.x, box.extents.z);

            var go = new GameObject($"Prop {prop.data.name}", typeof(MeshFilter), typeof(MeshRenderer));
            prop.root = go.transform;
            prop.root.SetParent(stage, false);
            prop.root.localScale = Vector3.one * prop.scale;
            go.GetComponent<MeshFilter>().sharedMesh = prop.mesh;
            prop.renderer = go.GetComponent<MeshRenderer>();
            prop.renderer.sharedMaterial = prop.material;
            prop.renderer.shadowCastingMode = ShadowCastingMode.Off;
            prop.renderer.enabled = false;

            var shadow = new GameObject($"Prop {prop.data.name} shadow", typeof(MeshFilter), typeof(MeshRenderer));
            prop.shadow = shadow.transform;
            prop.shadow.SetParent(stage, false);
            shadow.GetComponent<MeshFilter>().sharedMesh = quad;
            prop.shadowRenderer = shadow.GetComponent<MeshRenderer>();
            prop.shadowRenderer.sharedMaterial = prop.shadowMaterial;
            prop.shadowRenderer.shadowCastingMode = ShadowCastingMode.Off;
            prop.shadowRenderer.enabled = false;
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
            if (slot == open) open = null;
            Free(slot);
            slots.Remove(slot);
        }

        static void Free(Slot slot)
        {
            if (slot.root) Destroy(slot.root.gameObject);
            foreach (var o in new UnityEngine.Object[] { slot.frontMesh, slot.backMesh, slot.frontTexture, slot.backTexture, slot.frontMaterial, slot.backMaterial })
                if (o) Destroy(o);
            foreach (var prop in slot.props)
            {
                if (prop.root) Destroy(prop.root.gameObject);
                if (prop.shadow) Destroy(prop.shadow.gameObject);
                foreach (var o in new UnityEngine.Object[] { prop.mesh, prop.texture, prop.material, prop.shadowMaterial })
                    if (o) Destroy(o);
            }
            slot.props.Clear();
        }

        // ---- fitting a place to the room -----------------------------------------------------------------------

        sealed class Fitted
        {
            public float scale, clipped;
            public string warp;
            /// <summary>Per vertex: x how much of it shows by its direction, y metres beyond the room's edge.</summary>
            public Vector2[] front, back;
            /// <summary>Per vertex: where it is shown, in metres, in the place's frame at the seat's eye.</summary>
            public Vector3[] frontPositions, backPositions;
            /// <summary>Per vertex: degrees from the eye's level up to the wall's top and down to the floor line where it lands.</summary>
            public Vector2[] frontEdges, backEdges;
        }

        async void Fit(Slot slot)
        {
            slot.fitting = true;
            var shape = room.Shape;
            var place = slot.place;
            Fitted fit = null;
            try
            {
                fit = await Task.Run(() => Compute(shape, slot.front, slot.back, place));
            }
            catch (Exception e)
            {
                Debug.LogError($"[Zumi] places: {place.setting}: {e.Message}");
            }
            slot.fitting = false;
            // gone meanwhile, or the room changed again: the next frame fits it to the room as it is now
            if (!this || !slot.root || slot.dropped || fit == null || shape.serial != room.Serial) return;
            slot.root.SetPositionAndRotation(shape.eye, Quaternion.LookRotation(shape.forward));
            // the meshes are rebuilt in metres: each vertex where the warp shows it
            slot.root.localScale = Vector3.one;
            slot.frontMesh.SetVertices(fit.frontPositions);
            slot.frontMesh.SetUVs(1, fit.front);
            slot.frontMesh.SetUVs(2, fit.frontEdges);
            slot.frontMesh.RecalculateBounds();
            if (slot.backMesh)
            {
                slot.backMesh.SetVertices(fit.backPositions);
                slot.backMesh.SetUVs(1, fit.back);
                slot.backMesh.SetUVs(2, fit.backEdges);
                slot.backMesh.RecalculateBounds();
            }
            var window = shape.mode == RoomMode.None && room.Portals.Count > 0;
            foreach (var material in new[] { slot.frontMaterial, slot.backMaterial })
            {
                if (!material) continue;
                material.SetFloat("_Window", window ? 1f : 0f);
                if (!window) continue;
                var w = room.Portals[0];
                material.SetVector("_WindowCentre", w.centre);
                material.SetVector("_WindowRight", w.right);
                material.SetVector("_WindowUp", w.up);
                material.SetVector("_WindowSize", new Vector4(w.size.x / 2f, w.size.y / 2f, WindowEdge, 0f));
            }
            slot.scale = fit.scale;
            slot.clipped = fit.clipped;
            slot.fitSerial = shape.serial;
            Stand(slot);
            Debug.Log(Invariant($"[Zumi] places: {place.setting} fitted to the room ({shape.mode}): {fit.warp}; depth factor {fit.scale:F2}, {fit.clipped:P1} of the view inside the room and not drawn"));
        }

        // a point or direction of the place's own frame (x right, y up, z to the key wall) in the room's
        static Vector3 ToRoom(RoomShape shape, Vector3 local) => shape.right * local.x + Vector3.up * local.y + shape.forward * local.z;

        /// <summary>How much of the view shows in the direction of a point of its mesh (the place's own frame, the
        /// eye at the origin), by its measured span (hDeg by vDeg, less VignetteInsetDegrees). Across: all of it out to
        /// VignetteFull of the way from the view's centre to the edge, then smoothly less, nothing at the edge. Up and
        /// down: all of it until VignetteVerticalDegrees from the edge, nothing at the edge.</summary>
        public static float Vignette(Vector3 p, float hDeg, float vDeg)
        {
            var d = p.magnitude;
            if (d < 1e-6f) return 0f;
            float hMax = Mathf.Max(hDeg / 2f - VignetteInsetDegrees, 0.5f), vMax = Mathf.Max(vDeg / 2f - VignetteInsetDegrees, 0.5f);
            var across = Mathf.Clamp01((1f - Mathf.Abs(Mathf.Atan2(p.x, p.z)) * Mathf.Rad2Deg / hMax) / (1f - VignetteFull));
            var upright = Mathf.Clamp01((vMax - Mathf.Abs(Mathf.Asin(Mathf.Clamp(p.y / d, -1f, 1f))) * Mathf.Rad2Deg) / VignetteVerticalDegrees);
            return Smooth(across) * Smooth(upright);

            static float Smooth(float u) => u * u * u * (u * (u * 6f - 15f) + 10f);
        }

        // One layer of a place as it is shown in a room: every vertex sent where the warp puts it.
        sealed class Warped
        {
            /// <summary>Unit directions in the place's frame; the depth along each in the mesh's own units, already
            /// divided by the local zoom (what is shown smaller is farther); how much shows; metres to the room's edge.</summary>
            public Vector3[] direction;
            public float[] depth, shows, edge;
            public bool[] through;
            public Vector2[] wallEdges;

            public Warped(ZumiGlb glb, ZumiPlaceWarp warp, RoomShape shape, PlaceMesh place)
            {
                var n = glb.positions.Length;
                direction = new Vector3[n];
                depth = new float[n];
                shows = new float[n];
                edge = new float[n];
                through = new bool[n];
                wallEdges = new Vector2[n];
                for (var i = 0; i < n; i++)
                {
                    var p = glb.positions[i];
                    warp.Map(p, out direction[i], out var zoom, out var span, out wallEdges[i]);
                    depth[i] = p.magnitude / zoom;
                    var world = ToRoom(shape, direction[i]);
                    edge[i] = shape.Distance(world, out var wall);
                    through[i] = wall && shape.Through(world);
                    // the picture's own soft edge and the end of what the room can show across; the floor and the
                    // ceiling are cut per pixel by the shader, from wallEdges
                    shows[i] = Vignette(p, place.hDeg, place.vDeg) * span;
                }
            }
        }

        // off the main thread: only numbers
        static Fitted Compute(RoomShape shape, ZumiGlb front, ZumiGlb back, PlaceMesh place)
        {
            var warp = new ZumiPlaceWarp(shape, place.hDeg, place.vDeg);
            var layer = new Warped(front, warp, shape, place);

            // the depth: one factor on the warped depths that puts BeyondShare of what shows beyond the room's edge
            var samples = new List<(float ratio, float weight)>();
            var total = 0f;
            for (var i = 0; i < layer.depth.Length; i += ScaleSampleStride)
            {
                if (!layer.through[i] || layer.shows[i] <= 0f || layer.depth[i] < 1e-4f || float.IsInfinity(layer.edge[i])) continue;
                samples.Add(((layer.edge[i] + WallMargin) / layer.depth[i], layer.shows[i]));
                total += layer.shows[i];
            }
            samples.Sort((a, b) => a.ratio.CompareTo(b.ratio));
            // a view with nothing to show in any opening: the short rule for one wall straight ahead
            var scale = (shape.wallDistance + WallMargin) * warp.m0 / Mathf.Max(place.nearM ?? Percentile(front.positions, 1f - BeyondShare), 1e-3f);
            var reached = 0f;
            foreach (var (ratio, weight) in samples)
            {
                reached += weight;
                scale = ratio;
                if (reached >= BeyondShare * total) break;
            }

            var fit = new Fitted { scale = scale, warp = warp.Summary };
            int seen = 0, inside = 0;
            Place(layer, 0f, out fit.frontPositions, out fit.front);
            fit.frontEdges = layer.wallEdges;
            for (var i = 0; i < fit.front.Length; i++)
            {
                if (!layer.through[i]) continue;
                seen++;
                if (fit.front[i].y < 0f) inside++;
            }
            fit.clipped = (float)inside / Mathf.Max(seen, 1);
            // the back layer goes through the same warp, so the two stay aligned, and never comes inside the room
            if (back != null)
            {
                var backLayer = new Warped(back, warp, shape, place);
                Place(backLayer, BackMargin, out fit.backPositions, out fit.back);
                fit.backEdges = backLayer.wallEdges;
            }
            return fit;

            void Place(Warped l, float keepBeyond, out Vector3[] positions, out Vector2[] shown)
            {
                positions = new Vector3[l.depth.Length];
                shown = new Vector2[l.depth.Length];
                for (var i = 0; i < positions.Length; i++)
                {
                    var metres = scale * l.depth[i];
                    var known = !float.IsInfinity(l.edge[i]);
                    if (known && keepBeyond > 0f) metres = Mathf.Max(metres, l.edge[i] + keepBeyond);
                    positions[i] = l.direction[i] * metres;
                    shown[i] = new Vector2(l.shows[i], known ? Mathf.Clamp(metres - l.edge[i], -10f, 10f) : -1f);
                }
            }
        }

        static float Percentile(Vector3[] points, float share)
        {
            var distances = new List<float>();
            for (var i = 0; i < points.Length; i += 5) distances.Add(points[i].magnitude);
            distances.Sort();
            return distances.Count > 0 ? distances[Mathf.Min(distances.Count - 1, Mathf.FloorToInt(distances.Count * share))] : 1f;
        }

        // ---- the openings --------------------------------------------------------------------------------------

        void BuildOpenings()
        {
            openingsSerial = room.Serial;
            for (var i = openings.childCount - 1; i >= 0; i--) Destroy(openings.GetChild(i).gameObject);
            foreach (var q in room.Portals)
            {
                foreach (var material in new[] { openingMaterial, farMaterial })
                {
                    var go = Marked($"{material.name} {q.name}", quad, material);
                    go.transform.SetPositionAndRotation(q.centre + q.normal * OpeningInset, Quaternion.LookRotation(-q.normal, q.up));
                    go.transform.localScale = new Vector3(q.size.x, q.size.y, 1f);
                }
            }
            var cube = Resources.GetBuiltinResource<Mesh>("Cube.fbx");
            foreach (var box in room.Boxes)
            {
                var go = Marked($"occluder {box.label}", cube, occluderMaterial);
                go.transform.SetPositionAndRotation(box.centre, box.rotation);
                go.transform.localScale = box.size;
            }
        }

        GameObject Marked(string name, Mesh mesh, Material material)
        {
            var go = new GameObject(name, typeof(MeshFilter), typeof(MeshRenderer));
            go.transform.SetParent(openings, false);
            go.GetComponent<MeshFilter>().sharedMesh = mesh;
            var renderer = go.GetComponent<MeshRenderer>();
            renderer.sharedMaterial = material;
            renderer.shadowCastingMode = ShadowCastingMode.Off;
            return go;
        }

        // ---- props ---------------------------------------------------------------------------------------------

        // once per fit: the same room and seat give the same places
        void Stand(Slot slot)
        {
            var requests = new List<ZumiPropPlacer.Request>();
            foreach (var prop in slot.props)
                requests.Add(new ZumiPropPlacer.Request
                {
                    name = prop.data.name, kind = Kind(prop.data.surface), radius = prop.radius, height = prop.data.heightM,
                    half = new Vector2(prop.glb.bounds.extents.x, prop.glb.bounds.extents.z) * prop.scale,
                });
            var results = ZumiPropPlacer.Place(room, seat.Position, seat.Forward, requests);
            for (var i = 0; i < slot.props.Count; i++)
            {
                var prop = slot.props[i];
                prop.placement = results[i];
                if (!results[i].placed) continue;
                var box = prop.glb.bounds;
                // the point under its middle rests on the surface
                var rest = new Vector3(box.center.x, box.min.y, box.center.z) * prop.scale;
                prop.root.SetPositionAndRotation(results[i].position - results[i].rotation * rest, results[i].rotation);
                var across = 2f * Mathf.Max(box.extents.x, box.extents.z) * prop.scale * 1.5f;
                prop.shadow.SetPositionAndRotation(results[i].position + Vector3.up * 0.003f, Quaternion.Euler(90f, 0f, 0f));
                prop.shadow.localScale = new Vector3(across, across, 1f);
            }
            foreach (var prop in slot.props) Measure(prop);
        }

        static SurfaceKind Kind(PropSurface surface) =>
            surface == PropSurface.table ? SurfaceKind.Table : surface == PropSurface.shelf ? SurfaceKind.Shelf : SurfaceKind.Floor;

        // where the prop's mesh really is, against the room, the panel and the seat
        void Measure(Prop prop)
        {
            prop.on = null;
            if (prop.placement is not { placed: true }) return;
            var box = prop.glb.bounds;
            var t = prop.root;
            var lowest = float.PositiveInfinity;
            for (var c = 0; c < 8; c++)
                lowest = Mathf.Min(lowest, t.TransformPoint(box.center + Vector3.Scale(box.extents, new Vector3((c & 1) == 0 ? -1 : 1, (c & 2) == 0 ? -1 : 1, (c & 4) == 0 ? -1 : 1))).y);
            var under = t.TransformPoint(new Vector3(box.center.x, box.min.y, box.center.z));
            var support = room.SupportAt(under);
            prop.on = support?.name;
            prop.baseError = support != null ? lowest - support.height : float.PositiveInfinity;
            prop.outside = 0f;
            for (var c = 0; c < 4 && support != null; c++)
            {
                var corner = t.TransformPoint(box.center + Vector3.Scale(box.extents, new Vector3((c & 1) == 0 ? -1 : 1, -1, (c & 2) == 0 ? -1 : 1)));
                prop.outside = Mathf.Max(prop.outside, support.Outside(ZumiRoom.Flat(corner)));
            }

            float BoxDistance(Vector3 world)
            {
                var local = t.InverseTransformPoint(world);
                return t.TransformVector(local - box.ClosestPoint(local)).magnitude;
            }
            // the panel: 55 degrees square at the reading distance, across the seat's forward
            var half = Mathf.Tan(27.5f * Mathf.Deg2Rad) * ZumiPanelPresenter.ReadingDistance;
            var centre = seat.Position + seat.Forward * ZumiPanelPresenter.ReadingDistance;
            var right = Vector3.Cross(Vector3.up, seat.Forward);
            prop.panelClearance = float.PositiveInfinity;
            for (var x = -4; x <= 4; x++)
                for (var y = -4; y <= 4; y++)
                    prop.panelClearance = Mathf.Min(prop.panelClearance, BoxDistance(centre + right * (half * x / 4f) + Vector3.up * (half * y / 4f)));
            // the seat: an upright cylinder from the floor to above the head
            var axis = seat.Position;
            axis.y = Mathf.Clamp(under.y + prop.data.heightM / 2f, room.FloorY, seat.Position.y + 0.2f);
            var level = t.InverseTransformPoint(axis);
            var nearest = t.TransformPoint(box.ClosestPoint(level));
            prop.seatClearance = (ZumiRoom.Flat(nearest) - ZumiRoom.Flat(axis)).magnitude - ZumiPropPlacer.SeatRadius;
        }

        // the open place's props as tests and tools read them
        void Describe(Slot slot)
        {
            described = slot;
            describedSerial = slot.fitSerial;
            propLines.Clear();
            placedNames.Clear();
            unplacedLines.Clear();
            offKind.Clear();
            unsupported.Clear();
            PropBaseErrorMax = PropOutsideMax = 0f;
            PropPanelClearanceMin = PropSeatClearanceMin = PropGapMin = 99f;
            foreach (var prop in slot.props)
            {
                var p = prop.placement;
                if (p is not { placed: true })
                {
                    unplacedLines.Add($"{prop.data.name}: {p?.reason ?? "not placed yet"}");
                    propLines.Add($"{prop.data.name} ({prop.data.surface}): not shown, {p?.reason ?? "not placed yet"}");
                    continue;
                }
                placedNames.Add(prop.data.name);
                var support = room.SupportAt(p.position + Vector3.up * 0.01f);
                if (support == null || support.kind != Kind(prop.data.surface)) offKind.Add(prop.data.name);
                if (support == null || support.kind > Kind(prop.data.surface)) unsupported.Add(prop.data.name);
                propLines.Add(Invariant($"{prop.data.name} ({prop.data.surface}, {prop.data.heightM:F2} m): on {prop.on ?? "nothing"} at ({p.position.x:F2}, {p.position.y:F2}, {p.position.z:F2}), base {prop.baseError:+0.000;-0.000} m, {prop.panelClearance:F2} m from the panel, {prop.seatClearance:F2} m from the seat"));
                PropBaseErrorMax = Mathf.Max(PropBaseErrorMax, Mathf.Abs(prop.baseError));
                PropOutsideMax = Mathf.Max(PropOutsideMax, prop.outside);
                PropPanelClearanceMin = Mathf.Min(PropPanelClearanceMin, prop.panelClearance);
                PropSeatClearanceMin = Mathf.Min(PropSeatClearanceMin, prop.seatClearance);
                foreach (var other in slot.props)
                    if (other != prop && other.placement is { placed: true })
                        PropGapMin = Mathf.Min(PropGapMin, (ZumiRoom.Flat(other.placement.position) - ZumiRoom.Flat(p.position)).magnitude - prop.radius - other.radius);
            }
            foreach (var line in propLines) Debug.Log($"[Zumi] props: {line}");
        }

        void OnDestroy()
        {
            foreach (var slot in slots.ToArray()) Drop(slot);
            if (stage) Destroy(stage.gameObject);
            foreach (var o in new UnityEngine.Object[] { quad, openingMaterial, farMaterial, occluderMaterial })
                if (o) Destroy(o);
        }
    }
}
