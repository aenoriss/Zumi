using System;
using System.Collections.Generic;
using Oculus.Interaction;
using Oculus.Interaction.Surfaces;
using UnityEngine;
using UnityEngine.Rendering;

namespace Zumi
{
    /// <summary>
    /// How the reader draws its own interface, the same in the hand menu and on its cards: a flat cream plate, round
    /// white buttons, ink marks and lettering, amber under a finger or a ray (one light theme, the design tokens'
    /// colours). Everything is a flat mesh in Zumi/Flat; lettering is Unity's built-in font through the same shader.
    /// A shape faces -z: seen from there +x is right and +y up.
    /// </summary>
    public static class ZumiDraw
    {
        // design tokens (packages/design-tokens): cream.300, white, ink.900, ink.600, ink.400, amber.400
        public static readonly Color Plate = Hex(0xF4ECE4), Button = Hex(0xFFFFFF), Ink = Hex(0x222222), SoftInk = Hex(0x6B5E52), FaintInk = Hex(0xB5ADA3), Hover = Hex(0xF0B03A);
        /// <summary>The font's pixel size lettering is rasterised at; its size in the room is set by the scale.</summary>
        public const int FontPixels = 64;

        static readonly int ColorId = Shader.PropertyToID("_Color"), Src = Shader.PropertyToID("_Src"), Dst = Shader.PropertyToID("_Dst"), ZWrite = Shader.PropertyToID("_ZWrite");
        static Font font;

        /// <summary>A round button the other hand pokes, or points at and pinches.</summary>
        public sealed class RoundButton
        {
            public Transform transform;
            public Material disc;
            public IInteractableView[] views;

            public bool Touched
            {
                get
                {
                    foreach (var view in views)
                        if (view.State is InteractableState.Hover or InteractableState.Select) return true;
                    return false;
                }
            }
        }

        /// <summary>What a drawing is made of, so it can be faded as one and destroyed with its owner.</summary>
        public sealed class Parts
        {
            readonly List<(Material material, Color colour)> tinted = new();
            readonly List<UnityEngine.Object> owned = new();
            /// <summary>Alpha blended, drawn after the panel (which a card may overlap): for anything that fades.</summary>
            public bool blended;
            public int queue = -1;

            internal void Add(Material material, Color colour, Mesh mesh)
            {
                tinted.Add((material, colour));
                owned.Add(material);
                if (mesh) owned.Add(mesh);
            }

            /// <summary>Every shape and letter at this share of its own colour's alpha.</summary>
            public void SetAlpha(float alpha)
            {
                foreach (var (material, colour) in tinted)
                    material.SetColor(ColorId, new Color(colour.r, colour.g, colour.b, colour.a * alpha));
            }

            public void Destroy()
            {
                foreach (var o in owned) UnityEngine.Object.Destroy(o);
                owned.Clear();
                tinted.Clear();
            }
        }

        public static Material Flat(Shader shader, string name, Color colour, Parts parts, Mesh mesh = null, int order = 0)
        {
            var material = new Material(shader) { name = name };
            material.SetColor(ColorId, colour);
            if (parts.blended)
            {
                material.SetFloat(Src, (float)BlendMode.SrcAlpha);
                material.SetFloat(Dst, (float)BlendMode.OneMinusSrcAlpha);
                material.SetFloat(ZWrite, 0f);
                material.renderQueue = parts.queue + order;
            }
            parts.Add(material, colour, mesh);
            return material;
        }

        /// <summary>Flat polygons in one colour, z metres in front (negative) of the parent's plane.</summary>
        public static Transform Shape(Shader shader, Parts parts, string name, Transform parent, float z, Color colour, int order, params Vector2[][] polygons)
        {
            var go = new GameObject(name, typeof(MeshFilter), typeof(MeshRenderer));
            go.transform.SetParent(parent, false);
            go.transform.localPosition = new Vector3(0f, 0f, z);
            var vertices = new List<Vector3>();
            var triangles = new List<int>();
            foreach (var polygon in polygons)
            {
                // a convex outline as a fan; front faces are clockwise for a viewer on -z, where +x is right and +y up
                var area = 0f;
                for (var i = 0; i < polygon.Length; i++)
                {
                    var p = polygon[i];
                    var q = polygon[(i + 1) % polygon.Length];
                    area += p.x * q.y - q.x * p.y;
                }
                var first = vertices.Count;
                foreach (var p in polygon) vertices.Add(p);
                for (var i = 1; i + 1 < polygon.Length; i++)
                {
                    triangles.Add(first);
                    triangles.Add(first + (area > 0f ? i + 1 : i));
                    triangles.Add(first + (area > 0f ? i : i + 1));
                }
            }
            var mesh = new Mesh { name = name };
            mesh.SetVertices(vertices);
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateBounds();
            go.GetComponent<MeshFilter>().sharedMesh = mesh;
            var renderer = go.GetComponent<MeshRenderer>();
            renderer.sharedMaterial = Flat(shader, name, colour, parts, mesh, order);
            renderer.shadowCastingMode = ShadowCastingMode.Off;
            return go.transform;
        }

        /// <summary>One or more lines of lettering, capitals capHeight metres tall, centred on local (x, y).</summary>
        public static TextMesh Text(Shader shader, Parts parts, string name, Transform parent, Vector3 local, float capHeight, Color colour, int order, string text = "")
        {
            if (!font) font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            var go = new GameObject(name, typeof(MeshRenderer), typeof(TextMesh));
            go.transform.SetParent(parent, false);
            go.transform.localPosition = local;
            var label = go.GetComponent<TextMesh>();
            label.font = font;
            label.fontSize = FontPixels;
            label.anchor = TextAnchor.MiddleCenter;
            label.alignment = TextAlignment.Center;
            label.color = Color.white;
            // a capital is about 0.72 of the font's size; TextMesh draws one font pixel a tenth of a unit tall
            label.characterSize = 1f;
            go.transform.localScale = Vector3.one * (capHeight / (0.72f * FontPixels * 0.1f));
            label.text = text;
            var material = Flat(shader, name, colour, parts, null, order);
            material.mainTexture = font.material.mainTexture;
            if (!parts.blended)
            {
                // lettering always blends: its edges are the atlas's alpha
                material.SetFloat(Src, (float)BlendMode.SrcAlpha);
                material.SetFloat(Dst, (float)BlendMode.OneMinusSrcAlpha);
                material.SetFloat(ZWrite, 0f);
                material.renderQueue = (int)RenderQueue.Transparent + order;
            }
            var renderer = go.GetComponent<MeshRenderer>();
            renderer.sharedMaterial = material;
            renderer.shadowCastingMode = ShadowCastingMode.Off;
            return label;
        }

        /// <summary>Metres a line of that lettering is wide.</summary>
        public static float Width(string line, float capHeight)
        {
            if (!font) font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            font.RequestCharactersInTexture(line, FontPixels);
            var pixels = 0f;
            foreach (var c in line)
                if (font.GetCharacterInfo(c, out var info, FontPixels)) pixels += info.advance;
            return pixels * capHeight / (0.72f * FontPixels);
        }

        /// <summary>A ring, or part of one, as flat pieces: from one angle to another in degrees, counted from +x toward +y.</summary>
        public static Vector2[][] Arc(float radius, float thickness, float fromDegrees, float toDegrees, int steps = 12)
        {
            var pieces = new Vector2[steps][];
            for (var i = 0; i < steps; i++)
            {
                float a = Mathf.Lerp(fromDegrees, toDegrees, (float)i / steps) * Mathf.Deg2Rad, b = Mathf.Lerp(fromDegrees, toDegrees, (float)(i + 1) / steps) * Mathf.Deg2Rad;
                Vector2 da = new(Mathf.Cos(a), Mathf.Sin(a)), db = new(Mathf.Cos(b), Mathf.Sin(b));
                pieces[i] = new[] { da * (radius - thickness / 2f), da * (radius + thickness / 2f), db * (radius + thickness / 2f), db * (radius - thickness / 2f) };
            }
            return pieces;
        }

        /// <summary>The same outline somewhere else.</summary>
        public static Vector2[] Moved(Vector2[] outline, Vector2 by)
        {
            var moved = new Vector2[outline.Length];
            for (var k = 0; k < outline.Length; k++) moved[k] = outline[k] + by;
            return moved;
        }

        /// <summary>A round button on the parent's plane. The Interaction SDK parts read their fields in Awake, so the
        /// object is built inactive, wired, then switched on.</summary>
        public static RoundButton Round(Shader shader, Parts parts, string name, Transform parent, Vector2 at, float radius, int order, Action pressed)
        {
            var go = new GameObject(name);
            go.SetActive(false);
            go.transform.SetParent(parent, false);
            go.transform.localPosition = new Vector3(at.x, at.y, -0.001f);
            var plane = go.AddComponent<PlaneSurface>();
            var circle = go.AddComponent<CircleSurface>();
            circle.InjectAllCircleSurface(plane);
            circle.InjectOptionalRadius(radius);
            var poke = go.AddComponent<PokeInteractable>();
            poke.InjectAllPokeInteractable(circle);
            var ray = go.AddComponent<RayInteractable>();
            ray.InjectAllRayInteractable(circle);
            var button = new RoundButton { transform = go.transform, views = new IInteractableView[] { poke, ray } };
            button.disc = Shape(shader, parts, "Disc", go.transform, 0f, Button, order, Disc(radius)).GetComponent<MeshRenderer>().sharedMaterial;
            foreach (var view in button.views)
                view.WhenStateChanged += change =>
                {
                    if (change.NewState == InteractableState.Select) pressed();
                };
            go.SetActive(true);
            return button;
        }

        public static Vector2[] Disc(float radius, int points = 40)
        {
            var outline = new Vector2[points];
            for (var i = 0; i < points; i++)
            {
                var a = i * 2f * Mathf.PI / points;
                outline[i] = new Vector2(Mathf.Cos(a), Mathf.Sin(a)) * radius;
            }
            return outline;
        }

        /// <summary>A rectangle centred on the origin whose corners are rounded with that radius.</summary>
        public static Vector2[] Rounded(float width, float height, float radius)
        {
            const int steps = 8;
            radius = Mathf.Min(radius, Mathf.Min(width, height) / 2f);
            var outline = new Vector2[4 * (steps + 1)];
            for (var corner = 0; corner < 4; corner++)
            {
                var centre = new Vector2((corner == 0 || corner == 3 ? 1f : -1f) * (width / 2f - radius), (corner < 2 ? 1f : -1f) * (height / 2f - radius));
                for (var i = 0; i <= steps; i++)
                {
                    var a = (corner + (float)i / steps) * Mathf.PI / 2f;
                    outline[corner * (steps + 1) + i] = centre + new Vector2(Mathf.Cos(a), Mathf.Sin(a)) * radius;
                }
            }
            return outline;
        }

        public static Vector2[] Box(float x, float y, float width, float height) =>
            new[] { new Vector2(x, y), new Vector2(x, y + height), new Vector2(x + width, y + height), new Vector2(x + width, y) };

        /// <summary>An upright bar 13 mm tall whose left edge is at x.</summary>
        public static Vector2[] Bars(float x, float width) => Box(x, -0.0065f, width, 0.013f);

        /// <summary>A triangle 13 mm tall from its base at x to its point at x + length (a negative length points left).</summary>
        public static Vector2[] Triangle(float x, float length) =>
            new[] { new Vector2(x, -0.0065f), new Vector2(x, 0.0065f), new Vector2(x + length, 0f) };

        public static Color Hex(int rgb) => new(((rgb >> 16) & 255) / 255f, ((rgb >> 8) & 255) / 255f, (rgb & 255) / 255f, 1f);
    }
}
