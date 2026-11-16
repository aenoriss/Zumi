using System;
using System.Collections.Generic;
using System.Text;
using System.Threading.Tasks;
using GLTFast;
using Newtonsoft.Json.Linq;
using Oculus.Interaction;
using UnityEngine;

namespace Zumi
{
    /// <summary>
    /// A 3D book (Book/ZumiBook.glb: BackCover, Spine, PageBlock, FrontCover and Page_01.. hinged on the spine). It
    /// floats in the Explore carousel (ZumiCarousel places it, "shelf"); a hand takes it (Interaction SDK HandGrab, pinch or palm). Brought within
    /// OpenDistance of the head it opens by itself: it leaves the hand and floats there, the front cover swings open
    /// about the spine, the pages fan, and the first panel rises out of it toward where it is read (Opened fires as it
    /// starts to rise: the reader takes its seat then). Then the book fades away.
    /// </summary>
    public class ZumiBook : MonoBehaviour
    {
        public const string File = "Book/ZumiBook.glb";
        /// <summary>Metres from the head within which a held book opens.</summary>
        public const float OpenDistance = 0.36f;
        /// <summary>Seconds a book is held before it may open (a hand brushing past the shelf does not open one).</summary>
        public const float HoldBeforeOpen = 0.3f;
        public const float FloatAhead = 0.45f, FloatDrop = 0.14f;
        public const float SettleSeconds = 0.45f, CoverSeconds = 1.0f, CoverDegrees = 110f, PageDegreesFirst = 100f, PageStagger = 0.07f;
        public const float RiseDelay = 0.7f, RiseSeconds = 1.2f, FadeDelay = 0.6f, FadeSeconds = 1.3f;

        /// <summary>"loading", "shelf", "held", "opening", "gone".</summary>
        public string State { get; private set; } = "loading";
        public bool Grabbed => grabbable && grabbable.SelectingPointsCount > 0;
        /// <summary>How far open the front cover is: 0 closed, 1 at CoverDegrees.</summary>
        public float OpenAmount { get; private set; }
        public Vector3 Size { get; private set; }
        /// <summary>The first panel's picture rising out of the open book; null before.</summary>
        public Transform RisingPanel => rising ? rising.transform : null;

        /// <summary>The book is open and its first panel starts to rise: the reader begins.</summary>
        public event Action Opened;

        Transform model, cover;
        readonly List<Transform> pages = new();
        Quaternion coverRest;
        readonly List<Quaternion> pageRest = new();
        float hingeSign = 1f;
        readonly List<Material> materials = new();
        readonly List<Color> tints = new();
        Grabbable grabbable;
        Behaviour grab;
        GltfImport gltf;
        Pose flyFrom, flyTo;
        float openSince, heldSince;
        Vector3 baseScale = Vector3.one;
        MeshRenderer rising;
        Material risingMaterial;
        Pose risingFrom, risingTo;
        Vector2 risingSize;
        Texture risingTexture;
        Rect risingRect;
        bool openedRaised;

        static byte[] glbBytes;

        /// <summary>A new book, built from the glb; null when it cannot be read.</summary>
        public static async Task<ZumiBook> Create(string name)
        {
            glbBytes ??= await ZumiFlowKit.Bytes(File);
            if (glbBytes == null) return null;
            var go = new GameObject(name);
            go.SetActive(false);
            var book = go.AddComponent<ZumiBook>();
            if (!await book.Build(glbBytes))
            {
                Destroy(go);
                return null;
            }
            return book;
        }

        async Task<bool> Build(byte[] glb)
        {
            var json = JObject.Parse(Encoding.UTF8.GetString(glb, 20, BitConverter.ToInt32(glb, 12)));
            model = new GameObject("Model").transform;
            model.SetParent(transform, false);
            gltf = new GltfImport(materialGenerator: ZumiPanelScene.NoMaterials.Instance);
            var nodes = new Dictionary<uint, GameObject>();
            if (!await gltf.Load(glb)) return false;
            var instantiator = new GameObjectInstantiator(gltf, model, null, new InstantiationSettings { Mask = ComponentType.Mesh });
            instantiator.NodeCreated += (index, o) => nodes[index] = o;
            if (!await gltf.InstantiateMainSceneAsync(instantiator)) return false;
            var nodeObjects = new HashSet<GameObject>(nodes.Values);
            var described = json["nodes"] as JArray;
            foreach (var (index, node) in nodes)
            {
                var name = (string)described?[(int)index]?["name"] ?? node.name;
                if (name == "FrontCover") cover = node.transform;
                if (name.StartsWith("Page_")) pages.Add(node.transform);
                // the renderers of this node, not of the nodes under it
                foreach (var r in node.GetComponentsInChildren<MeshRenderer>(true))
                {
                    var owner = r.transform;
                    while (owner != node.transform && !nodeObjects.Contains(owner.gameObject)) owner = owner.parent;
                    if (owner != node.transform) continue;
                    var subs = r.GetComponent<MeshFilter>().sharedMesh.subMeshCount;
                    var mats = new Material[subs];
                    for (var s = 0; s < subs; s++)
                    {
                        var tex = ZumiPanelScene.BaseColour(json, gltf, (int)index, s);
                        var tint = BaseColourFactor(json, (int)index, s);
                        // the inside of the front cover is board, nearly black: as the cover swings open it would
                        // be a black sail beside the pages, so it is a light endpaper instead
                        if (name == "FrontCover" && s == 1) tint = ZumiDraw.Hex(0xEADFCF);
                        var m = ZumiFlowKit.Picture(tex ? tex : Texture2D.whiteTexture, tint, 2450, depth: true);
                        materials.Add(m);
                        tints.Add(tint);
                        mats[s] = m;
                    }
                    r.sharedMaterials = mats;
                    r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                }
            }
            pages.Sort((a, b) => string.CompareOrdinal(a.name, b.name));
            if (cover) coverRest = cover.localRotation;
            foreach (var p in pages) pageRest.Add(p.localRotation);

            // the closed book's box, in the book's own frame
            var bounds = new Bounds();
            var any = false;
            foreach (var r in GetComponentsInChildren<MeshFilter>(true))
            {
                // from the meshes: a renderer that is not active yet has no bounds
                var b = r.sharedMesh.bounds;
                for (var c = 0; c < 8; c++)
                {
                    var p = transform.InverseTransformPoint(r.transform.TransformPoint(b.center + Vector3.Scale(b.extents, new Vector3((c & 1) == 0 ? -1 : 1, (c & 2) == 0 ? -1 : 1, (c & 4) == 0 ? -1 : 1))));
                    if (any) bounds.Encapsulate(p);
                    else bounds = new Bounds(p, Vector3.zero);
                    any = true;
                }
            }
            Size = bounds.size;
            centreOffset = bounds.center;
            // the cover opens away from the pages: toward the book's front (+z, where its art faces)
            if (cover) hingeSign = OpensForward(+1f) >= OpensForward(-1f) ? 1f : -1f;
            grabbable = ZumiGrabbableProp.MakeGrabbable(gameObject, bounds);
            grab = GetComponent<Oculus.Interaction.HandGrab.HandGrabInteractable>();
            Debug.Log($"[Zumi] book: built, {pages.Count} pages, size {Size.x:F3} x {Size.y:F3} x {Size.z:F3} m, cover opens {(hingeSign > 0 ? "+" : "-")}{CoverDegrees} about its hinge");
            return true;
        }

        internal static Color BaseColourFactor(JObject json, int node, int primitive)
        {
            var mesh = json["nodes"]?[node]?["mesh"];
            if (mesh == null || json["meshes"]?[(int)mesh]?["primitives"] is not JArray prims || prims.Count == 0) return Color.white;
            var material = prims[Mathf.Min(primitive, prims.Count - 1)]["material"];
            if (material == null || json["materials"]?[(int)material]?["pbrMetallicRoughness"]?["baseColorFactor"] is not JArray f || f.Count < 4) return Color.white;
            return new Color((float)f[0], (float)f[1], (float)f[2], 1f);
        }

        // where the cover's middle goes along the book's +z when turned a quarter one way
        float OpensForward(float sign)
        {
            var r = cover.GetComponentInChildren<MeshFilter>();
            if (!r) return 0f;
            var centre = r.sharedMesh.bounds.center;
            var before = transform.InverseTransformPoint(r.transform.TransformPoint(centre)).z;
            cover.localRotation = coverRest * Quaternion.Euler(0f, 90f * sign, 0f);
            var after = transform.InverseTransformPoint(r.transform.TransformPoint(centre)).z;
            cover.localRotation = coverRest;
            return after - before;
        }

        public void SetGrabbable(bool on)
        {
            if (!grab || grab.enabled == on) return;
            grab.enabled = on;
            // the SDK's transformer holds a grabbed object at the scale it had when it woke (relative 1..1); the
            // carousel scales its books, so it is told the scale the book has now each time it becomes takeable
            if (on && grabbable && GetComponent<GrabFreeTransformer>() is { } transformer) transformer.Initialize(grabbable);
        }

        /// <summary>Waiting in the carousel ("shelf"), shown, not yet grabbable.</summary>
        public void Shelve()
        {
            gameObject.SetActive(true);
            State = "shelf";
            SetGrabbable(false);
        }

        /// <summary>Places a waiting book (not one in a hand or opening): its middle, its rotation (cover toward its
        /// +z) and its scale.</summary>
        public void Place(Vector3 centre, Quaternion rotation, float scale)
        {
            if (State != "shelf" || Grabbed) return;
            transform.SetPositionAndRotation(centre - rotation * (centreOffset * scale), rotation);
            transform.localScale = Vector3.one * scale;
        }

        /// <summary>The book's colours times brightness, at that alpha (the carousel dims its ends).</summary>
        public void SetShade(float brightness, float alpha)
        {
            if (State is "opening" or "gone") return;
            for (var i = 0; i < materials.Count; i++)
                ZumiFlowKit.SetTint(materials[i], new Color(tints[i].r * brightness, tints[i].g * brightness, tints[i].b * brightness, tints[i].a * alpha));
        }

        /// <summary>Pencil: the whole book in graphite on cream (1) or in colour (0), with the line of a colour sweep:
        /// beyond the plane (world axis xyz, place w) it is still pencil.</summary>
        public void SetGraphite(float amount, Vector4 sweepPlane)
        {
            foreach (var m in materials)
            {
                m.SetFloat(GraphiteId, amount);
                m.SetVector(SweepId, sweepPlane);
            }
        }

        static readonly int GraphiteId = Shader.PropertyToID("_Graphite"), SweepId = Shader.PropertyToID("_SweepPlane");
        Vector3 centreOffset;

        /// <summary>Opens the book where it is, as bringing it close does (a ray pinch on the carousel's middle book).</summary>
        public void Open()
        {
            if (State is not ("shelf" or "held")) return;
            BeginOpen();
        }

        /// <summary>Coloured comic pages printed on the book's leaves, in reading order: Page_01's front, its back,
        /// Page_02's front, and so on (wrapping round when there are fewer pictures than faces). Each picture is a card
        /// a breath off its leaf, fitted inside it.</summary>
        public void SetPagePictures(IReadOnlyList<Texture> pictures)
        {
            if (pictures == null || pictures.Count == 0 || printed) return;
            printed = true;
            const float margin = 0.006f, off = 0.0004f;
            for (var i = 0; i < pages.Count; i++)
            {
                var mesh = pages[i].GetComponentInChildren<MeshFilter>();
                if (!mesh) continue;
                var b = mesh.sharedMesh.bounds;
                var leaf = mesh.transform;
                for (var face = 0; face < 2; face++)
                {
                    var tex = pictures[(2 * i + face) % pictures.Count];
                    if (!tex) continue;
                    var aspect = (float)tex.width / tex.height;
                    var h = b.size.y - 2f * margin;
                    var w = Mathf.Min(h * aspect, b.size.x - 2f * margin);
                    h = w / aspect;
                    var m = ZumiFlowKit.Picture(tex, Color.white, 2451, depth: true);
                    materials.Add(m);
                    tints.Add(Color.white);
                    var card = ZumiFlowKit.Card(face == 0 ? "Print front" : "Print back", leaf, new Vector2(w, h), m).transform;
                    // the front faces the book's +z; a card reads from its -z, so the front one is turned round
                    var z = face == 0 ? b.max.z + off : b.min.z - off;
                    card.localPosition = new Vector3(b.center.x, b.center.y, z);
                    card.localRotation = face == 0 ? Quaternion.Euler(0f, 180f, 0f) : Quaternion.identity;
                }
            }
        }

        bool printed;

        /// <summary>The picture that rises out of the book when it opens: a part of a page (uv rect).</summary>
        public void SetRisingPicture(Texture texture, Rect uv)
        {
            risingTexture = texture;
            risingRect = uv;
        }

        void Update()
        {
            switch (State)
            {
                case "shelf":
                    if (Grabbed)
                    {
                        State = "held";
                        heldSince = Time.time;
                        Debug.Log($"[Zumi] book: {name} taken");
                    }
                    break;
                case "held":
                    var cam = Camera.main;
                    if (cam && Time.time - heldSince > HoldBeforeOpen && Vector3.Distance(cam.transform.position, transform.position) < OpenDistance) BeginOpen();
                    else if (!Grabbed) State = "shelf";
                    break;
                case "opening":
                    Animate(Time.time - openSince);
                    break;
            }
        }

        void BeginOpen()
        {
            State = "opening";
            openSince = Time.time;
            SetGrabbable(false);
            flyFrom = new Pose(transform.position, transform.rotation);
            var head = ZumiFlowKit.LevelHead();
            var at = head.position + head.rotation * new Vector3(0f, -FloatDrop, FloatAhead);
            // the cover toward the eyes, tipped back like a book held to read
            flyTo = new Pose(at, Quaternion.LookRotation(head.position - at, Vector3.up) * Quaternion.Euler(-20f, 0f, 0f));
            baseScale = transform.localScale;
            Debug.Log("[Zumi] book: brought close, opening");
        }

        void Animate(float t)
        {
            // it leaves the hand and settles in front of the eyes
            var k = ZumiFlowKit.Smooth(t / SettleSeconds);
            transform.SetPositionAndRotation(Vector3.Lerp(flyFrom.position, flyTo.position, k), Quaternion.Slerp(flyFrom.rotation, flyTo.rotation, k));
            // the cover swings open about the spine; the pages follow, one after another
            var open = t - SettleSeconds * 0.6f;
            OpenAmount = ZumiFlowKit.Smooth(open / CoverSeconds);
            if (cover) cover.localRotation = coverRest * Quaternion.Euler(0f, hingeSign * CoverDegrees * OpenAmount, 0f);
            for (var i = 0; i < pages.Count; i++)
            {
                var share = 1f - (i + 1f) / (pages.Count + 1f);
                var a = ZumiFlowKit.Smooth((open - 0.15f - i * PageStagger) / CoverSeconds) * PageDegreesFirst * share;
                pages[i].localRotation = pageRest[i] * Quaternion.Euler(0f, hingeSign * a, 0f);
            }
            // once the pages have fanned, the book dissolves into the Zumi colours, its crumbs drifting up
            var fade = t - SettleSeconds - RiseDelay - FadeDelay;
            if (fade > 0f)
            {
                var f = Mathf.Clamp01(fade / FadeSeconds);
                if (!dust) Burst();
                foreach (var m in materials) m.SetFloat(DissolveId, f);
            }
            // only when it has fully gone (the dissolve and the crumbs), and a beat after, the first panel appears
            // where the book was and rises to where it is read; the reader takes over when it lands
            var rise = fade - Mathf.Max(FadeSeconds, DustSeconds) - Beat;
            if (rise >= 0f && !rising && !openedRaised) StartRise();
            if (rise >= (risingTexture ? RiseSeconds : 0f) && !openedRaised)
            {
                openedRaised = true;
                Opened?.Invoke();
            }
            if (rising)
            {
                var r = Mathf.Clamp01(rise / RiseSeconds);
                var e = ZumiFlowKit.Smooth(r);
                var p = Vector3.Lerp(risingFrom.position, risingTo.position, e);
                rising.transform.SetPositionAndRotation(p, Quaternion.Slerp(risingFrom.rotation, risingTo.rotation, e));
                rising.transform.localScale = new Vector3(risingSize.x, risingSize.y, 1f) * Mathf.Lerp(0.3f, 1f, e);
                ZumiFlowKit.SetTint(risingMaterial, new Color(1f, 1f, 1f, Mathf.Min(Mathf.Clamp01(rise / 0.25f), Mathf.Clamp01(1f - (rise - RiseSeconds) / 0.6f))));
            }
            if (openedRaised && (!rising || rise > RiseSeconds + 0.6f))
            {
                State = "gone";
                if (rising) Destroy(rising.gameObject);
                gameObject.SetActive(false);
                Debug.Log("[Zumi] book: gone, the reader has the episode");
            }
        }

        /// <summary>The crumbs' whole life (the last burst plus the longest lifetime) and the beat before the panel.</summary>
        public const float DustSeconds = 1.5f, Beat = 0.3f;

        static readonly int DissolveId = Shader.PropertyToID("_Dissolve");
        static readonly Color[] ZumiHues =
        {
            ZumiDraw.Hex(0xC7A8FF), ZumiDraw.Hex(0x9CCBFF), ZumiDraw.Hex(0xFFA8CF), ZumiDraw.Hex(0x9EE5C8), ZumiDraw.Hex(0xFFE89A), ZumiDraw.Hex(0xFFC3A0),
        };
        ParticleSystem dust;
        Material dustMaterial;

        // a modest burst of small soft specks in the Zumi hues from the book's volume, rising and fading over ~1.4 s
        void Burst()
        {
            var go = new GameObject("Book dust");
            go.transform.SetPositionAndRotation(transform.position, transform.rotation);
            dust = go.AddComponent<ParticleSystem>();
            dust.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
            var main = dust.main;
            main.duration = FadeSeconds;
            main.loop = false;
            main.startLifetime = new ParticleSystem.MinMaxCurve(0.6f, 1.1f);
            main.startSpeed = new ParticleSystem.MinMaxCurve(0.02f, 0.08f);
            main.startSize = new ParticleSystem.MinMaxCurve(0.008f, 0.02f);
            main.gravityModifier = -0.04f;
            main.simulationSpace = ParticleSystemSimulationSpace.World;
            main.maxParticles = 220;
            var grad = new Gradient();
            var keys = new GradientColorKey[ZumiHues.Length];
            for (var i = 0; i < keys.Length; i++) keys[i] = new GradientColorKey(ZumiHues[i], i / (keys.Length - 1f));
            grad.SetKeys(keys, new[] { new GradientAlphaKey(1f, 0f), new GradientAlphaKey(1f, 1f) });
            main.startColor = new ParticleSystem.MinMaxGradient(grad) { mode = ParticleSystemGradientMode.RandomColor };
            var emission = dust.emission;
            emission.rateOverTime = 0f;
            emission.SetBursts(new[] { new ParticleSystem.Burst(0f, 90), new ParticleSystem.Burst(0.2f, 70), new ParticleSystem.Burst(0.4f, 50) });
            var shape = dust.shape;
            shape.shapeType = ParticleSystemShapeType.Box;
            shape.scale = new Vector3(Size.x * 1.6f, Size.y, 0.04f);
            var fadeOut = dust.colorOverLifetime;
            fadeOut.enabled = true;
            var alpha = new Gradient();
            alpha.SetKeys(new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(Color.white, 1f) },
                new[] { new GradientAlphaKey(0f, 0f), new GradientAlphaKey(0.95f, 0.15f), new GradientAlphaKey(0f, 1f) });
            fadeOut.color = alpha;
            var r = go.GetComponent<ParticleSystemRenderer>();
            dustMaterial = new Material(ZumiFlowKit.GlowShader) { renderQueue = 3150 };
            dustMaterial.SetFloat("_Solid", 1f);
            r.sharedMaterial = dustMaterial;
            r.renderMode = ParticleSystemRenderMode.Billboard;
            dust.Play();
        }

        void StartRise()
        {
            if (!risingTexture) return;
            risingMaterial = ZumiFlowKit.Picture(risingTexture, Color.white, 3100);
            risingMaterial.mainTextureScale = risingRect.size;
            risingMaterial.mainTextureOffset = risingRect.position;
            var aspect = risingRect.width * risingTexture.width / Mathf.Max(1f, risingRect.height * risingTexture.height);
            // the panel's long side spans 55 degrees at the reading distance, as the reader shows it
            var longSide = 2f * Mathf.Tan(27.5f * Mathf.Deg2Rad) * ZumiPanelPresenter.ReadingDistance;
            risingSize = aspect >= 1f ? new Vector2(longSide, longSide / aspect) : new Vector2(longSide * aspect, longSide);
            rising = ZumiFlowKit.Card("Rising panel", null, risingSize * 0.18f, risingMaterial);
            var head = ZumiFlowKit.LevelHead();
            risingFrom = new Pose(transform.position + transform.up * 0.05f, ZumiFlowKit.Facing(transform.position, head.position));
            var to = head.position + head.rotation * new Vector3(0f, 0f, ZumiPanelPresenter.ReadingDistance + 0.02f);
            risingTo = new Pose(to, ZumiFlowKit.Facing(to, head.position));
            rising.transform.SetPositionAndRotation(risingFrom.position, risingFrom.rotation);
        }

        void OnDestroy()
        {
            foreach (var m in materials) Destroy(m);
            if (risingMaterial) Destroy(risingMaterial);
            if (rising) Destroy(rising.gameObject);
            if (dust) Destroy(dust.gameObject);
            if (dustMaterial) Destroy(dustMaterial);
            gltf?.Dispose();
        }
    }
}
