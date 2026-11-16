using System;
using System.Collections.Generic;
using System.IO;
using System.Threading.Tasks;
using Oculus.Interaction.Input;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.Rendering;

namespace Zumi
{
    /// <summary>
    /// What the creation flow's pieces share: the picture shader, a picture card, files under StreamingAssets (read
    /// with a web request, so the same code reads them inside the APK), the mascot, easing and the pinch.
    /// </summary>
    public static class ZumiFlowKit
    {
        static Shader picture, warp;
        static readonly int MainTex = Shader.PropertyToID("_MainTex"), SecondTex = Shader.PropertyToID("_SecondTex"),
            Mix = Shader.PropertyToID("_Mix"), Tint = Shader.PropertyToID("_Color"), ZWrite = Shader.PropertyToID("_ZWrite");

        public static Shader PictureShader => picture ? picture : picture = Resources.Load<Shader>("ZumiPicture");
        public static Shader WarpShader => warp ? warp : warp = Resources.Load<Shader>("ZumiWarp");
        static Shader glowShader;
        public static Shader GlowShader => glowShader ? glowShader : glowShader = Resources.Load<Shader>("ZumiGlow");

        public static Material Picture(Texture texture, Color tint, int queue = 3000, bool depth = false)
        {
            var m = new Material(PictureShader) { name = texture ? texture.name : "picture", renderQueue = queue };
            m.SetTexture(MainTex, texture);
            m.SetColor(Tint, tint);
            m.SetFloat(ZWrite, depth ? 1f : 0f);
            return m;
        }

        public static void SetSecond(Material m, Texture texture) => m.SetTexture(SecondTex, texture);
        public static void SetMix(Material m, float mix) => m.SetFloat(Mix, mix);
        public static void SetTint(Material m, Color tint) => m.SetColor(Tint, tint);

        static Mesh quad;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void Reset() => quad = null;

        /// <summary>A unit quad on the xy plane, uv (0, 0) at its lower left; seen from -z, +x is right.</summary>
        public static Mesh Quad
        {
            get
            {
                if (quad) return quad;
                quad = new Mesh { name = "zumi quad" };
                quad.SetVertices(new[] { new Vector3(-0.5f, -0.5f), new Vector3(0.5f, -0.5f), new Vector3(0.5f, 0.5f), new Vector3(-0.5f, 0.5f) });
                quad.SetUVs(0, new[] { new Vector2(0, 0), new Vector2(1, 0), new Vector2(1, 1), new Vector2(0, 1) });
                quad.SetTriangles(new[] { 0, 2, 1, 0, 3, 2 }, 0);
                quad.RecalculateBounds();
                return quad;
            }
        }

        /// <summary>A card width x height metres showing that material.</summary>
        public static MeshRenderer Card(string name, Transform parent, Vector2 size, Material material)
        {
            var go = new GameObject(name, typeof(MeshFilter), typeof(MeshRenderer));
            go.transform.SetParent(parent, false);
            go.transform.localScale = new Vector3(size.x, size.y, 1f);
            go.GetComponent<MeshFilter>().sharedMesh = Quad;
            var r = go.GetComponent<MeshRenderer>();
            r.sharedMaterial = material;
            r.shadowCastingMode = ShadowCastingMode.Off;
            return r;
        }

        // ---- StreamingAssets ------------------------------------------------------------------------------------

        static string Url(string relative)
        {
            var path = Path.Combine(Application.streamingAssetsPath, relative).Replace('\\', '/');
            return path.Contains("://") ? path : "file:///" + path.TrimStart('/');
        }

        public static async Task<byte[]> Bytes(string relative)
        {
            using var request = UnityWebRequest.Get(Url(relative));
            var sent = request.SendWebRequest();
            while (!sent.isDone) await Task.Yield();
            if (request.result != UnityWebRequest.Result.Success)
            {
                Debug.LogWarning($"[Zumi] flow: {relative} cannot be read: {request.error}");
                return null;
            }
            return request.downloadHandler.data;
        }

        public static async Task<Texture2D> Texture(string relative)
        {
            var bytes = await Bytes(relative);
            if (bytes == null) return null;
            var t = new Texture2D(2, 2, TextureFormat.RGBA32, true) { name = Path.GetFileNameWithoutExtension(relative), wrapMode = TextureWrapMode.Clamp };
            if (!t.LoadImage(bytes, true))
            {
                UnityEngine.Object.Destroy(t);
                return null;
            }
            return t;
        }

        // ---- the mascot -----------------------------------------------------------------------------------------

        /// <summary>The mascot, heightMetres tall, its feet on its parent's origin, facing the parent's -z (the viewer);
        /// nothing of it can be grabbed or collided with.</summary>
        public static GameObject Mascot(GameObject prefab, Transform parent, float heightMetres, string expression = "happy")
        {
            if (!prefab) return null;
            var go = UnityEngine.Object.Instantiate(prefab, parent, false);
            go.name = "Mascot";
            foreach (var c in go.GetComponentsInChildren<Collider>(true)) UnityEngine.Object.Destroy(c);
            foreach (var b in go.GetComponentsInChildren<MonoBehaviour>(true))
                if (b is not ZumiMascot && b.GetType().Namespace != null && b.GetType().Namespace.StartsWith("Oculus.Interaction")) UnityEngine.Object.Destroy(b);
            foreach (var rb in go.GetComponentsInChildren<Rigidbody>(true)) UnityEngine.Object.Destroy(rb);
            go.transform.localRotation = Quaternion.Euler(0f, 180f, 0f);
            // its size from its meshes as built, before anything animates
            var bounds = new Bounds();
            var any = false;
            foreach (var r in go.GetComponentsInChildren<Renderer>(true))
            {
                if (any) bounds.Encapsulate(r.bounds);
                else bounds = r.bounds;
                any = true;
            }
            var h = any ? bounds.size.y / Mathf.Max(go.transform.lossyScale.y, 1e-5f) : 1f;
            go.transform.localScale = Vector3.one * (heightMetres / Mathf.Max(h, 1e-4f));
            var mascot = go.GetComponent<ZumiMascot>();
            if (mascot) mascot.expression = expression;
            return go;
        }

        // ---- motion ---------------------------------------------------------------------------------------------

        public static float Smooth(float t)
        {
            t = Mathf.Clamp01(t);
            return t * t * (3f - 2f * t);
        }

        public static float OutBack(float t)
        {
            t = Mathf.Clamp01(t);
            const float c = 1.4f;
            var u = t - 1f;
            return 1f + (c + 1f) * u * u * u + c * u * u;
        }

        /// <summary>The head's pose made level: its position, and its forward on the floor's plane.</summary>
        public static Pose LevelHead()
        {
            var cam = Camera.main;
            if (!cam) return new Pose(new Vector3(0f, 1.5f, 0f), Quaternion.identity);
            var f = Vector3.ProjectOnPlane(cam.transform.forward, Vector3.up);
            return new Pose(cam.transform.position, Quaternion.LookRotation(f.sqrMagnitude > 1e-4f ? f : Vector3.forward));
        }

        /// <summary>Faces a card at `at` toward the eye: its +z points away from the viewer.</summary>
        public static Quaternion Facing(Vector3 at, Vector3 eye) => Quaternion.LookRotation(at - eye, Vector3.up);
    }

    /// <summary>A pinch of either hand, counted once, when it closes. A hand already pinching when it is armed must
    /// open first.</summary>
    public sealed class ZumiPinch
    {
        Hand[] hands = Array.Empty<Hand>();
        readonly Dictionary<Hand, bool> was = new();
        public Vector3 Where { get; private set; }

        public void Arm()
        {
            Find();
            was.Clear();
            foreach (var h in hands) was[h] = true;
        }

        void Find()
        {
            if (hands.Length == 0) hands = UnityEngine.Object.FindObjectsByType<Hand>(FindObjectsInactive.Include);
        }

        public bool Closed()
        {
            Find();
            var any = false;
            foreach (var h in hands)
            {
                if (!h) continue;
                var now = h.isActiveAndEnabled && h.IsTrackedDataValid && h.GetIndexFingerIsPinching();
                was.TryGetValue(h, out var before);
                if (now && !before && !any)
                {
                    any = true;
                    if (h.GetJointPose(HandJointId.HandIndexTip, out var tip)) Where = tip.position;
                }
                was[h] = now;
            }
            return any;
        }

        /// <summary>Every tracked hand's index fingertip.</summary>
        public IEnumerable<Vector3> Tips()
        {
            Find();
            foreach (var h in hands)
                if (h && h.isActiveAndEnabled && h.IsTrackedDataValid && h.GetJointPose(HandJointId.HandIndexTip, out var tip)) yield return tip.position;
        }
    }
}
