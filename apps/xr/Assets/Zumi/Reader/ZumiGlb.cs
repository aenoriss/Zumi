using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace Zumi
{
    /// <summary>
    /// The geometry of a place or prop GLB as the pipeline writes them: triangles with positions and one set of texture
    /// coordinates, one embedded image, no node transform. Read without Unity objects, so off the main thread, and
    /// already in Unity's axes: glTF's (x right, y up, -z ahead) becomes (x, y, z ahead), which turns every triangle
    /// over, so the winding is swapped back; v counts from the bottom as Unity's textures do.
    /// </summary>
    public sealed class ZumiGlb
    {
        public Vector3[] positions;
        public Vector2[] uvs;
        public int[] triangles;
        /// <summary>The first image's file (PNG or JPEG); null when the model has none.</summary>
        public byte[] image;
        /// <summary>The positions' box, in Unity's axes.</summary>
        public Bounds bounds;

        public static ZumiGlb Read(byte[] glb)
        {
            if (glb == null || glb.Length < 28 || BitConverter.ToUInt32(glb, 0) != 0x46546C67) throw new InvalidDataException("not a GLB");
            var jsonLength = BitConverter.ToInt32(glb, 12);
            var json = JObject.Parse(Encoding.UTF8.GetString(glb, 20, jsonLength));
            var bin = 20 + jsonLength + 8;
            var accessors = (JArray)json["accessors"];
            var views = (JArray)json["bufferViews"];

            foreach (var node in (JArray)json["nodes"] ?? new JArray())
                if (node["matrix"] != null || node["translation"] != null || node["rotation"] != null || node["scale"] != null)
                    throw new InvalidDataException("a node with a transform (the pipeline writes none)");

            var positions = new List<Vector3>();
            var uvs = new List<Vector2>();
            var triangles = new List<int>();
            foreach (var mesh in (JArray)json["meshes"])
                foreach (var primitive in (JArray)mesh["primitives"])
                {
                    if (((int?)primitive["mode"] ?? 4) != 4) throw new InvalidDataException("a primitive that is not triangles");
                    var first = positions.Count;
                    var at = Accessor(accessors, views, (int)primitive["attributes"]["POSITION"], bin, 5126, out var count, out var stride, 12);
                    for (var i = 0; i < count; i++, at += stride)
                        positions.Add(new Vector3(BitConverter.ToSingle(glb, at), BitConverter.ToSingle(glb, at + 4), -BitConverter.ToSingle(glb, at + 8)));
                    var uv = primitive["attributes"]["TEXCOORD_0"];
                    if (uv != null)
                    {
                        at = Accessor(accessors, views, (int)uv, bin, 5126, out var uvCount, out stride, 8);
                        for (var i = 0; i < uvCount; i++, at += stride)
                            uvs.Add(new Vector2(BitConverter.ToSingle(glb, at), 1f - BitConverter.ToSingle(glb, at + 4)));
                    }
                    while (uvs.Count < positions.Count) uvs.Add(Vector2.zero);
                    if (primitive["indices"] == null)
                    {
                        for (var i = 0; i + 2 < count; i += 3) { triangles.Add(first + i); triangles.Add(first + i + 2); triangles.Add(first + i + 1); }
                        continue;
                    }
                    var type = (int)accessors[(int)primitive["indices"]]["componentType"];
                    var size = type == 5125 ? 4 : type == 5123 ? 2 : 1;
                    at = Accessor(accessors, views, (int)primitive["indices"], bin, type, out var indexCount, out stride, size);
                    for (var i = 0; i + 2 < indexCount; i += 3, at += 3 * stride)
                    {
                        triangles.Add(first + Index(glb, at, size));
                        triangles.Add(first + Index(glb, at + 2 * stride, size));
                        triangles.Add(first + Index(glb, at + stride, size));
                    }
                }
            if (positions.Count == 0) throw new InvalidDataException("no geometry");

            var read = new ZumiGlb { positions = positions.ToArray(), uvs = uvs.ToArray(), triangles = triangles.ToArray() };
            Vector3 min = read.positions[0], max = min;
            foreach (var p in read.positions) { min = Vector3.Min(min, p); max = Vector3.Max(max, p); }
            read.bounds = new Bounds((min + max) / 2f, max - min);
            if (json["images"] is JArray images && images.Count > 0 && images[0]["bufferView"] != null)
            {
                var view = views[(int)images[0]["bufferView"]];
                read.image = new byte[(int)view["byteLength"]];
                Buffer.BlockCopy(glb, bin + ((int?)view["byteOffset"] ?? 0), read.image, 0, read.image.Length);
            }
            return read;
        }

        static int Index(byte[] glb, int at, int size) =>
            size == 4 ? (int)BitConverter.ToUInt32(glb, at) : size == 2 ? BitConverter.ToUInt16(glb, at) : glb[at];

        // where an accessor's first element is in the file, how many it has and how far apart they are
        static int Accessor(JArray accessors, JArray views, int index, int bin, int componentType, out int count, out int stride, int elementSize)
        {
            var accessor = accessors[index];
            if ((int)accessor["componentType"] != componentType) throw new InvalidDataException($"accessor {index}: component type {accessor["componentType"]}");
            var view = views[(int)accessor["bufferView"]];
            count = (int)accessor["count"];
            stride = (int?)view["byteStride"] ?? elementSize;
            return bin + ((int?)view["byteOffset"] ?? 0) + ((int?)accessor["byteOffset"] ?? 0);
        }
    }
}
