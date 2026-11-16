using System.Collections.Generic;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json;
using UnityEngine;

namespace Zumi
{
    /// <summary>
    /// The making-of bundle (StreamingAssets/MakingOf/making-of.json and its images): the ten pencil pages, their
    /// coloured pages and mask overlays, and per page its frames and balloons in the page's pixels (x0, y0, x1, y1 from
    /// the top left); the panel that shows depth, the voice line, the sound effect and the music, by their names in
    /// the episode. Pictures are kept at half size on the GPU (PageHeight pixels tall): a page in the grid is a few
    /// hundred pixels tall in the headset.
    /// </summary>
    public sealed class ZumiMakingOfData
    {
        public const string Folder = "MakingOf/";
        public const int PageHeight = 800;

        public sealed class Balloon
        {
            public int[] box;
            public string text, speaker, kind, panel, bubble;
        }

        public sealed class Page
        {
            public int index;
            public string pencil, colour, masks;
            public int[] size;
            public List<int[]> frames = new();
            public List<Balloon> balloons = new();
            /// <summary>Each character's appearance on the page: its cast id, name, box (page pixels), centre.</summary>
            public List<Character> characters = new();
            [JsonIgnore] public Texture pencilTexture, colourTexture, maskTexture;
            public Vector2 Pixels => size is { Length: 2 } ? new Vector2(size[0], size[1]) : new Vector2(1131, 1600);
        }

        public sealed class Character
        {
            public string cast, name, panel, card;
            public int[] box;
            public float[] centre;
        }

        public sealed class CastMember
        {
            public string id, name, colour;
        }

        public sealed class Depth
        {
            public string panel;
            public int page;
            public int[] box;
        }

        public sealed class Sound
        {
            public string panel, bubble, speaker, text, audio;
        }

        public string title;
        public List<Page> pages = new();
        /// <summary>The characters the identity step found, each with its colour ("#RRGGBB"); empty without it.</summary>
        public List<CastMember> cast = new();
        public Depth depth;
        public Sound voice, sfx;
        public string music, place;

        static Task<ZumiMakingOfData> loading;

        // Play without a domain reload keeps statics, and the last session's textures are gone with it
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void Reset() => loading = null;

        /// <summary>The bundle, read once; null when it is missing.</summary>
        public static Task<ZumiMakingOfData> Get() => loading ??= Load();

        static async Task<ZumiMakingOfData> Load()
        {
            var bytes = await ZumiFlowKit.Bytes(Folder + "making-of.json");
            if (bytes == null) return null;
            var data = JsonConvert.DeserializeObject<ZumiMakingOfData>(Encoding.UTF8.GetString(bytes));
            var started = Time.realtimeSinceStartup;
            foreach (var page in data.pages)
            {
                page.pencilTexture = await Half(page.pencil);
                page.colourTexture = await Half(page.colour);
                page.maskTexture = await Half(page.masks);
            }
            Debug.Log($"[Zumi] making-of: {data.pages.Count} pages read in {Time.realtimeSinceStartup - started:F1} s");
            return data;
        }

        static async Task<Texture> Half(string file)
        {
            if (string.IsNullOrEmpty(file)) return null;
            var full = await ZumiFlowKit.Texture(Folder + file);
            if (!full) return null;
            var h = Mathf.Min(PageHeight, full.height);
            var rt = new RenderTexture(Mathf.RoundToInt(full.width * (float)h / full.height), h, 0, RenderTextureFormat.ARGB32)
            {
                name = file, useMipMap = true, autoGenerateMips = true, wrapMode = TextureWrapMode.Clamp, filterMode = FilterMode.Trilinear,
            };
            rt.Create();
            Graphics.Blit(full, rt);
            Object.Destroy(full);
            return rt;
        }

        /// <summary>The page and balloon of a panel's bubble; false when no page has it.</summary>
        public bool Find(string panel, string bubble, out Page page, out Balloon balloon)
        {
            foreach (var p in pages)
                foreach (var b in p.balloons)
                    if (b.panel == panel && b.bubble == bubble)
                    {
                        page = p;
                        balloon = b;
                        return true;
                    }
            page = null;
            balloon = null;
            return false;
        }
    }
}
