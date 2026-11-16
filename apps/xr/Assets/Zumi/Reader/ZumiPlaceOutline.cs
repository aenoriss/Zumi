using System.Collections.Generic;
using UnityEngine;

namespace Zumi
{
    /// <summary>
    /// The edge of the place on the walls, drawn as a comic frame's ink line (Zumi/Ink). The place ends across where its
    /// fit stops showing it (ZumiPlaceWarp.EndLeft, EndRight) and up and down at the floor line and the wall's top
    /// (without a scanned room: the window's edges). That boundary is a rectangle on the walls laid flat: s, metres
    /// along the room's outline from where the left end meets it, by world height y; on each wall it lies exactly on
    /// the wall's plane (the outline's corners are MRUK's wall corners) and it bends on the real corner lines. The mesh
    /// is a band round that rectangle whose first texture coordinates are (s, y); the shader draws the line inside the
    /// boundary, so nothing is drawn on the wall outside it.
    /// </summary>
    public static class ZumiPlaceOutline
    {
        /// <summary>The ink line's width in metres (the default for a comic frame's border at 2 to 4 m: the panel
        /// pictures come without their drawn border, so the artist's weight could not be measured), how far it wobbles
        /// to either side as a share of its width, and its colour as shown.</summary>
        public const float LineMetres = 0.014f, WobbleShare = 0.25f;
        public static readonly Color Ink = new(0.08f, 0.075f, 0.07f, 1f);

        /// <summary>Fills the mesh with the band round the boundary from azimuth left to right (degrees from the key
        /// wall's direction) and gives the line's rectangle on the walls laid flat, inset by half the line: s from, s
        /// to, bottom, top. False when there is no boundary to draw.</summary>
        public static bool Build(RoomShape shape, float left, float right, Mesh mesh, out Vector4 rect)
        {
            rect = default;
            var points = new List<Vector2>();
            float bottom, top;
            if (shape.mode == RoomMode.Scanned && shape.outline is { Length: >= 3 })
            {
                if (!Walk(shape, left, right, points)) return false;
                bottom = shape.floorY;
                top = shape.ceilingY;
            }
            else
            {
                Vector3 a = shape.windowCentre - shape.right * shape.windowHalf.x, b = shape.windowCentre + shape.right * shape.windowHalf.x;
                points.Add(new Vector2(a.x, a.z));
                points.Add(new Vector2(b.x, b.z));
                bottom = shape.windowCentre.y - shape.windowHalf.y;
                top = shape.windowCentre.y + shape.windowHalf.y;
            }
            var along = new float[points.Count];
            for (var i = 1; i < points.Count; i++) along[i] = along[i - 1] + (points[i] - points[i - 1]).magnitude;
            var length = along[^1];
            if (length < 4f * LineMetres || top - bottom < 4f * LineMetres) return false;
            var half = LineMetres / 2f;
            rect = new Vector4(half, length - half, bottom + half, top - half);

            var vertices = new List<Vector3>();
            var uvs = new List<Vector2>();
            var triangles = new List<int>();
            var band = LineMetres * (0.65f + WobbleShare) + 0.004f;
            // the level sides: along the outline, the full length
            foreach (var y in new[] { rect.z, rect.w })
                for (var i = 0; i + 1 < points.Count; i++)
                    Quad(points[i], points[i + 1], along[i], along[i + 1], Mathf.Max(y - band, bottom), Mathf.Min(y + band, top), vertices, uvs, triangles);
            // the upright sides, on the first and the last wall
            foreach (var (s, i) in new[] { (rect.x, 0), (rect.y, points.Count - 2) })
            {
                float from = Mathf.Max(s - band, along[i]), to = Mathf.Min(s + band, along[i + 1]);
                Vector2 p = At(points[i], points[i + 1], along[i], along[i + 1], from), q = At(points[i], points[i + 1], along[i], along[i + 1], to);
                Quad(p, q, from, to, rect.z + band, rect.w - band, vertices, uvs, triangles);
            }
            mesh.Clear();
            mesh.SetVertices(vertices);
            mesh.SetUVs(0, uvs);
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateBounds();
            return true;
        }

        static Vector2 At(Vector2 a, Vector2 b, float sa, float sb, float s) => Vector2.Lerp(a, b, Mathf.InverseLerp(sa, sb, s));

        static void Quad(Vector2 a, Vector2 b, float sa, float sb, float low, float high, List<Vector3> vertices, List<Vector2> uvs, List<int> triangles)
        {
            if (high <= low || sb <= sa) return;
            var first = vertices.Count;
            foreach (var (p, s, y) in new[] { (a, sa, low), (b, sb, low), (a, sa, high), (b, sb, high) })
            {
                vertices.Add(new Vector3(p.x, y, p.y));
                uvs.Add(new Vector2(s, y));
            }
            triangles.AddRange(new[] { first, first + 2, first + 1, first + 2, first + 3, first + 1 });
        }

        // the room's outline from where the level line of sight at azimuth left meets it to where right does, through
        // the corners between, in the order the seat sees them from left to right
        static bool Walk(RoomShape shape, float left, float right, List<Vector2> points)
        {
            var outline = shape.outline;
            var eye = new Vector2(shape.eye.x, shape.eye.z);
            if (!Hit(shape, left, out var start, out var edgeStart) || !Hit(shape, right, out var end, out var edgeEnd)) return false;
            // which way round the outline runs left to right as seen from the eye
            var n = outline.Length;
            var forwardOrder = Mathf.DeltaAngle(Azimuth(shape, start), Azimuth(shape, outline[(edgeStart + 1) % n])) > 0f;
            points.Add(start);
            var edge = edgeStart;
            for (var guard = 0; edge != edgeEnd && guard < n; guard++)
            {
                if (forwardOrder)
                {
                    points.Add(outline[(edge + 1) % n]);
                    edge = (edge + 1) % n;
                }
                else
                {
                    points.Add(outline[edge]);
                    edge = (edge - 1 + n) % n;
                }
            }
            points.Add(end);
            return edge == edgeEnd && points.Count >= 2;
        }

        static float Azimuth(RoomShape shape, Vector2 p)
        {
            var v = new Vector3(p.x - shape.eye.x, 0f, p.y - shape.eye.z);
            return Mathf.Atan2(Vector3.Dot(v, shape.right), Vector3.Dot(v, shape.forward)) * Mathf.Rad2Deg;
        }

        // where the level line of sight at that azimuth meets the outline first, and on which edge (from vertex i to i + 1)
        static bool Hit(RoomShape shape, float azimuth, out Vector2 at, out int edge)
        {
            at = default;
            edge = -1;
            var r = azimuth * Mathf.Deg2Rad;
            var d3 = shape.forward * Mathf.Cos(r) + shape.right * Mathf.Sin(r);
            Vector2 o = new(shape.eye.x, shape.eye.z), d = new(d3.x, d3.z);
            var best = float.PositiveInfinity;
            var outline = shape.outline;
            for (var i = 0; i < outline.Length; i++)
            {
                Vector2 a = outline[i], e = outline[(i + 1) % outline.Length] - a;
                var den = d.x * e.y - d.y * e.x;
                if (Mathf.Abs(den) < 1e-6f) continue;
                var w = a - o;
                var t = (w.x * e.y - w.y * e.x) / den;
                var u = (w.x * d.y - w.y * d.x) / den;
                if (t <= 0f || u < -1e-4f || u > 1f + 1e-4f || t >= best) continue;
                best = t;
                at = o + d * t;
                edge = i;
            }
            return edge >= 0;
        }
    }
}
