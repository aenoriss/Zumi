using System;
using System.Collections.Generic;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using GLTFast;
using GLTFast.Materials;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.Rendering;
using Zumi.Format;

namespace Zumi
{
    /// <summary>
    /// A scene3d panel's scene.glb (export_zumi.box_cards), built to be seen from its camera: the camera at the
    /// origin looking down -Z, each frame's window (the frame's shape as alpha) at distance 1, the layers far to near
    /// behind it, lettering in front. Its units are shares of the reading distance, so it is scaled by that distance
    /// and its origin put at the seat's eye: seen from the seat, every surface is where it was built to be seen.
    /// As in the browser viewer, each frame's layers show only through that frame's window (stencil 1 + n, in the
    /// stencil's low four bits: one panel is drawn at a time, and the high bits are the place's), so the gutters stay
    /// empty; lettering is never clipped. Every node says what it is in its glTF extras.
    /// </summary>
    public sealed class ZumiPanelScene : IDisposable
    {
        /// <summary>One layer of the scene. Its mesh carries its place: the node itself rests at the origin, unscaled.</summary>
        public sealed class Node
        {
            /// <summary>window, backdrop, character, object or lettering.</summary>
            public string kind;
            public int? frame;
            public string card;
            public string bubble;
            public Transform transform;
            public readonly List<Renderer> renderers = new();
            public readonly List<Material> materials = new();
            /// <summary>In the scene's own space: +y up, -x the panel's right, -z away from the camera.</summary>
            public Bounds bounds;
            /// <summary>Distance from the camera plane to the node's middle, in scene units (a window's is 1).</summary>
            public float Depth => -bounds.center.z;
            public Color tint = Color.white;
            public float blur;
        }

        public Transform Root { get; private set; }
        public IReadOnlyList<Node> Nodes => nodes;
        /// <summary>The panel's size at the windows' distance, in scene units: 2 tan(fov / 2) on each side.</summary>
        public Vector2 PanelSize { get; private set; }

        GltfImport gltf;
        readonly List<Material> shadowMaterials = new();
        readonly List<Node> nodes = new();
        /// <summary>The frames of one panel the stencil's four bits tell apart (refs 1 to 15); past that two frames
        /// would share a window.</summary>
        public const int MaxFrames = 15;
        static readonly int Stencil = Shader.PropertyToID("_Stencil");
        static readonly int StencilComp = Shader.PropertyToID("_StencilComp");
        static readonly int ZWrite = Shader.PropertyToID("_ZWrite");
        static readonly int Tint = Shader.PropertyToID("_Tint");
        static readonly int Blur = Shader.PropertyToID("_Blur");
        // files before 1.1 have no extras: the node's name says its kind and frame
        static readonly Regex FrameInName = new(@"(?:window: frame |\[frame )(\d+)");

        /// <summary>Null when the scene does not load or the load is cancelled; nothing is left behind then.</summary>
        /// <param name="eye">Where the scene's camera goes: its position the eye, its +z the view.</param>
        /// <param name="unitMetres">Metres of one scene unit: the distance from the eye to the windows.</param>
        public static async Task<ZumiPanelScene> Load(byte[] glb, Transform eye, float unitMetres, Shader windowShader,
                                                      Shader cardShader, Shader shadowShader, CancellationToken cancel)
        {
            var json = JObject.Parse(Encoding.UTF8.GetString(glb, 20, BitConverter.ToInt32(glb, 12)));
            var scene = new ZumiPanelScene { Root = new GameObject("scene").transform, gltf = new GltfImport(materialGenerator: NoMaterials.Instance) };
            scene.Root.SetParent(eye, false);
            // glTFast keeps -Z as the camera's view; turning it 180 points it the way the eye looks
            scene.Root.SetLocalPositionAndRotation(Vector3.zero, Quaternion.Euler(0f, 180f, 0f));
            scene.Root.localScale = Vector3.one * unitMetres;
            var perspective = json["cameras"]?[0]?["perspective"];
            var yfov = (float?)perspective?["yfov"] ?? Mathf.Deg2Rad * 30f;
            var height = 2f * Mathf.Tan(yfov / 2f);
            scene.PanelSize = new Vector2(height * ((float?)perspective?["aspectRatio"] ?? 1f), height);

            var objects = new Dictionary<uint, GameObject>();
            var ok = false;
            try
            {
                ok = await scene.gltf.Load(glb, cancellationToken: cancel);
                if (ok && scene.Root)
                {
                    var only = new InstantiationSettings { Mask = ComponentType.Mesh };
                    var instantiator = new GameObjectInstantiator(scene.gltf, scene.Root, null, only);
                    instantiator.NodeCreated += (index, go) => objects[index] = go;
                    ok = await scene.gltf.InstantiateMainSceneAsync(instantiator, cancel);
                }
            }
            catch (OperationCanceledException)
            {
                ok = false;
            }
            if (!ok || !scene.Root || cancel.IsCancellationRequested)
            {
                scene.Dispose();
                return null;
            }

            var order = 0;
            var described = json["nodes"] as JArray;
            // in the file's order, which is far to near: the render queue follows it
            for (uint i = 0; described != null && i < described.Count; i++)
            {
                if (!objects.TryGetValue(i, out var go)) continue;
                var renderers = go.GetComponentsInChildren<MeshRenderer>(true);
                if (renderers.Length == 0) continue;
                var extras = described[(int)i]["extras"]?.ToObject<NodeExtras>() ?? new NodeExtras();
                var name = (string)described[(int)i]["name"] ?? go.name;
                var inName = FrameInName.Match(name);
                var node = new Node
                {
                    kind = extras.kind ?? (name.Contains(':') ? name.Substring(0, name.IndexOf(':')) : "object"),
                    frame = extras.frame ?? (inName.Success ? int.Parse(inName.Groups[1].Value) : null),
                    card = extras.card,
                    bubble = extras.bubble,
                    transform = go.transform,
                };
                var first = true;
                var k = 0;
                foreach (var r in renderers)
                {
                    var tex = BaseColour(json, scene.gltf, (int)i, k++);
                    Material m;
                    if (node.kind == "window")
                        m = new Material(windowShader) { name = name, mainTexture = tex };
                    else
                    {
                        m = new Material(cardShader) { name = name, mainTexture = tex, renderQueue = 3000 + order++ };
                        m.SetFloat(StencilComp, (float)(node.frame.HasValue ? CompareFunction.Equal : CompareFunction.Always));
                        m.SetFloat(ZWrite, node.kind == "backdrop" ? 1f : 0f);
                    }
                    if (node.frame.HasValue) m.SetFloat(Stencil, 1 + node.frame.Value % MaxFrames);
                    r.sharedMaterial = m;
                    node.renderers.Add(r);
                    node.materials.Add(m);
                    // a primitive's object sits unmoved under its node, so the mesh's bounds are the scene's
                    var b = r.GetComponent<MeshFilter>().sharedMesh.bounds;
                    if (first) node.bounds = b;
                    else node.bounds.Encapsulate(b);
                    first = false;
                }
                scene.nodes.Add(node);
            }
            if (shadowShader)
                foreach (var node in scene.nodes)
                    if (node.kind == "window") scene.AddShadow(node, shadowShader);
            return scene;
        }

        /// <summary>A frame's soft shadow: how far it reaches past the frame and how dark it is at the frame's edge, in
        /// scene units (metres at the reading distance).</summary>
        public const float ShadowFeather = 0.035f, ShadowStrength = 0.5f;

        // the frame window's quad again, grown about its middle in the panel's plane, with Zumi/FrameShadow
        void AddShadow(Node window, Shader shadowShader)
        {
            for (var i = 0; i < window.renderers.Count; i++)
            {
                var mesh = window.renderers[i].GetComponent<MeshFilter>().sharedMesh;
                var b = mesh.bounds;
                var size = new Vector2(Mathf.Max(b.size.x, 1e-4f), Mathf.Max(b.size.y, 1e-4f));
                var grow = new Vector2((size.x + 2.4f * ShadowFeather) / size.x, (size.y + 2.4f * ShadowFeather) / size.y);
                var m = new Material(shadowShader) { name = $"{window.materials[i].name} shadow", mainTexture = window.materials[i].mainTexture };
                m.SetVector("_Grow", grow);
                m.SetVector("_Radius", new Vector4(ShadowFeather / size.x, ShadowFeather / size.y, 0f, 0f));
                m.SetFloat("_Strength", ShadowStrength);
                shadowMaterials.Add(m);
                var go = new GameObject($"{window.renderers[i].name} shadow", typeof(MeshFilter), typeof(MeshRenderer));
                go.transform.SetParent(Root, false);
                go.transform.SetLocalPositionAndRotation(new Vector3(b.center.x * (1f - grow.x), b.center.y * (1f - grow.y), 0f), Quaternion.identity);
                go.transform.localScale = new Vector3(grow.x, grow.y, 1f);
                go.GetComponent<MeshFilter>().sharedMesh = mesh;
                var renderer = go.GetComponent<MeshRenderer>();
                renderer.sharedMaterial = m;
                renderer.shadowCastingMode = ShadowCastingMode.Off;
            }
        }

        // A node's art, by the file's own indices (node -> mesh -> primitive -> material -> baseColorTexture -> texture),
        // from the textures glTFast decoded. Never through glTFast's materials: their shaders are in no scene, so a
        // build strips them, and on the headset the lookup came back empty and every card drew white.
        static Texture2D BaseColour(JObject json, GltfImport gltf, int node, int primitive)
        {
            var mesh = json["nodes"]?[node]?["mesh"];
            if (mesh == null || json["meshes"]?[(int)mesh]?["primitives"] is not JArray primitives || primitives.Count == 0) return null;
            var material = primitives[Mathf.Min(primitive, primitives.Count - 1)]["material"];
            var texture = material == null ? null : json["materials"]?[(int)material]?["pbrMetallicRoughness"]?["baseColorTexture"]?["index"];
            return texture == null ? null : gltf.GetTexture((int)texture);
        }

        // glTFast builds no materials: the reader makes its own from Zumi/Window and Zumi/Card
        sealed class NoMaterials : IMaterialGenerator
        {
            public static readonly NoMaterials Instance = new();
            public Material GetDefaultMaterial(bool pointsSupport = false) => null;
            public Material GenerateMaterial(GLTFast.Schema.MaterialBase gltfMaterial, IGltfReadable gltf, bool pointsSupport = false) => null;
            public void SetLogger(GLTFast.Logging.ICodeLogger logger) { }
        }

        /// <summary>A layer's look: its art times rgb, drawn at alpha (0 is not drawn at all), blurred by that many
        /// texels (0 sharp).</summary>
        public void SetLook(Node node, Color tint, float blur)
        {
            if (node.tint == tint && node.blur == blur) return;
            node.tint = tint;
            node.blur = blur;
            foreach (var m in node.materials)
            {
                m.SetColor(Tint, tint);
                m.SetFloat(Blur, blur);
            }
            foreach (var r in node.renderers) r.enabled = tint.a > 0f;
        }

        /// <summary>Destroys the scene's objects and materials, and through glTFast its meshes and textures.</summary>
        public void Dispose()
        {
            if (Root) UnityEngine.Object.Destroy(Root.gameObject);
            foreach (var node in nodes)
                foreach (var m in node.materials) UnityEngine.Object.Destroy(m);
            nodes.Clear();
            foreach (var m in shadowMaterials) UnityEngine.Object.Destroy(m);
            shadowMaterials.Clear();
            gltf?.Dispose();
            gltf = null;
        }
    }
}
