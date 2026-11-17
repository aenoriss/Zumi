using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using Zumi.Format;

namespace Zumi
{
    /// <summary>
    /// How a comic was made: a mocked playback, from the making-of bundle, of what the pipeline did to its ten pencil
    /// pages, stage by stage (the constants below), in a grid in front of the reader under a header (the comic's
    /// "How ... was made", the stage's name, its step and a progress bar):
    ///   Scanned     the comic's book comes out of the carousel, opens in front of the grid (ZumiBook.Showcase) and
    ///               its pencil pages fly out of it into the grid; then it closes and fades
    ///   Coloured    each pencil page turns into its coloured page, a wave across the grid
    ///   Panels      frame outlines draw over the pages, the masks fade in, a few balloons per page type their
    ///               transcribed text beside them with the speaker's name
    ///   Depth       one panel (the bundle's depth panel, its scene from the episode) lifts out of its page, turns
    ///               about 60 degrees so its side shows, and its layers slide apart into an exploded multiplane stack
    ///               (DepthGap between consecutive layers, the background farthest, each sheet outlined in soft ink),
    ///               sway, close up, turn back and settle onto the page
    ///   3D world    one place of the episode (the depth panel's setting when it has props, else the first place that
    ///               has them) floats where the depth panel was, seen through a rounded window with the Zumi rim, and
    ///               turns slowly so its depth reads; its props pop in one by one in front of the window with their
    ///               names, then everything shrinks back into the depth panel's page
    ///   Voice       that voice line plays over its balloon with its waveform, then a sound effect; the music swells
    /// then the pages merge in the middle, the Zumi glow (Resources/ZumiGlow.shader) blooms over them and the whole
    /// screen fades out (OutroSeconds), and Finished fires.
    /// (The World stage, the wall opening behind the grid, is cut: the book opens the wall when it is read.)
    /// A pinch or the hand menu skips to the end.
    /// </summary>
    public class ZumiMakingOf : MonoBehaviour
    {
        public const float GatherSeconds = 6.8f, ColourSeconds = 9f, PanelsSeconds = 18f, DepthSeconds = 12f, WorldSeconds = 12f, VoiceSeconds = 12f, OutroSeconds = 3.6f;
        public const float GridDistance = 1.0f, GridDrop = 0.04f, PageHeight = 0.27f, Gap = 0.035f;
        public const int Columns = 5;
        public const int BalloonsPerPage = 3, LabelLines = 2;
        public const float LabelCap = 0.0093f, LabelWidth = 0.2f, TypeCharsPerSecond = 24f, HeaderCap = 0.024f, BarWidth = 0.6f;
        // one page at a time comes near enough to read (the hero in the panels stage, then the voice's and the sound's
        // pages): about 28 degrees tall, between the header's pill and the caption's mascot, left of centre so its
        // labels or the sound card fit on its right
        public static readonly Vector3 Near = new(-0.09f, -0.01f, 0.6f);
        public const float NearScale = 1.13f, HeroIn = 6.2f, HeroOut = 16.4f, LabelFade = 0.35f;
        public const float MusicGain = 0.55f;
        /// <summary>What the mascot says during each stage (StageNames' order), and at the merge.</summary>
        public static readonly string[] StageLines =
        {
            "It all started as pencil pages.",
            "First, I colour the pencils, keeping every line the artist's.",
            "I find each panel, each balloon, and read every word.",
            "I learn who's who, so every character stays the same on every page.",
            "I split each panel into layers and repaint the background hidden behind them.",
            "I build the world around each scene, and the objects in it.",
            "Every character gets a voice, plus sounds and music.",
        };
        /// <summary>The merge line; {0} is the comic's title.</summary>
        public const string DoneLine = "That's how {0} was made. Grab it to read!";
        /// <summary>The header's title; {0} is the comic's title.</summary>
        public const string HeaderTitle = "How {0} was made";
        /// <summary>The open book: metres ahead of the eyes and below them, its height. Its pages fly out one after
        /// another from PagesOut seconds, PageStagger apart, each PageFlight long; it is put away at BookPutAway.</summary>
        public const float BookAhead = 0.6f, BookDrop = 0.13f, BookHeight = 0.24f, PagesOut = 1.9f, PageStagger = 0.24f, PageFlight = 1.3f, BookPutAway = 5.5f;
        /// <summary>The caption sits this far under the eyes here: clear of the grid's bottom row.</summary>
        public const float CaptionBelow = 0.37f;
        public const float CharactersSeconds = 8f;
        public static readonly string[] StageNames = { "Scanned", "Coloured", "Panels and balloons", "Character identification", "Depth", "3D world", "Voice and sound" };
        // the characters' stage takes no time when the bundle has no cast (set in Play)
        static readonly float[] StageSeconds = { GatherSeconds, ColourSeconds, PanelsSeconds, CharactersSeconds, DepthSeconds, WorldSeconds, VoiceSeconds };
        const int StageCharacters = 3, StageDepth = 4, StageWorld = 5, StageVoice = 6;
        /// <summary>The depth panel at its widest: this many times its size on the page, turned this many degrees, its
        /// layers this many metres apart (consecutive, in depth order), their outlines this many metres wide.</summary>
        public const float DepthScale = 2.7f, DepthTurn = 58f, DepthGap = 0.08f, DepthOutline = 0.0025f;
        /// <summary>The 3D world's window (metres), its corner radius, how far ahead it floats, the tallest prop's height
        /// in front of it (the others keep their heights relative to it), and the widest share of the view inside it.</summary>
        public static readonly Vector2 WorldWindow = new(0.5f, 0.35f);
        public const float WorldCorner = 0.05f, WorldDistance = 0.72f, PropTallest = 0.15f, WorldViewHalfDegrees = 32f;
        /// <summary>Tries at loading the depth panel's scene and the 3D world's place before giving up.</summary>
        public const int LoadTries = 3;

        // ---- read-only state for tests and tools -------------------------------------------------------------
        /// <summary>The stage on show (StageNames), "done" at the end, null before.</summary>
        public string PlaybackStage { get; private set; }
        public int StageIndex { get; private set; } = -1;
        public float Elapsed { get; private set; }
        public static float TotalSeconds
        {
            get
            {
                var s = OutroSeconds;
                foreach (var x in StageSeconds) s += x;
                return s;
            }
        }
        public bool Skipped { get; private set; }
        public bool DepthLoaded => depthScene != null;
        /// <summary>The depth panel's layers (nodes at one depth are one layer), and now: the metres from its front
        /// layer to its back one along its own axis, and its turn in degrees.</summary>
        public int DepthLayers => depthLayers.Count;
        public float DepthStackMetres { get; private set; }
        public float DepthTurnDegrees { get; private set; }
        /// <summary>Why the depth scene or the world did not load, after its last try; null when it did or is loading.</summary>
        public string DepthError { get; private set; }
        public string WorldError { get; private set; }
        public bool WorldLoaded => world;
        /// <summary>The place the 3D world shows, and how many of its props have popped in now.</summary>
        public string WorldPlace { get; private set; }
        public int WorldPropsShown { get; private set; }
        public bool VoicePlayed { get; private set; }

        public event Action Finished;

        sealed class Label
        {
            public TextMesh text;
            public Transform plate, leader;
            public string full;
            public float start, width, leaderLength;
        }

        sealed class PageView
        {
            public ZumiMakingOfData.Page data;
            public Transform root;
            public Material picture, mask;
            public MeshRenderer maskRenderer;
            public readonly ZumiDraw.Parts parts = new() { blended = true, queue = 2992 };
            // the balloon labels beside a lifted page fade on their own: gone before it goes back among its neighbours
            public readonly ZumiDraw.Parts labelParts = new() { blended = true, queue = 3013 };
            public readonly List<Label> labels = new();
            public Pose from;
            public Vector2 fromSize;
            public Pose cell;
            public Vector2 size;
        }

        Shader flat;
        ZumiCaption caption;
        ZumiReader reader;
        ZumiMakingOfData data;
        ZumiBook book;
        string comicTitle;
        Pose bookPose;
        bool bookAway;
        Pose anchor;
        readonly List<PageView> pages = new();
        PageView hero;
        Transform header;
        TextMesh stageText, stepText;
        Transform barFill;
        readonly ZumiDraw.Parts headerParts = new() { blended = true, queue = 3400 };
        float startedAt;
        bool running;
        ZumiPinch pinch;
        // depth
        ZumiPanelScene depthScene;
        Transform depthPivot;
        bool scenesLoading;
        // the scene's metres per unit at the pivot's scale 1
        float depthUnit;

        sealed class DepthLayer
        {
            public readonly List<ZumiPanelScene.Node> nodes = new();
            public readonly List<Vector3> homes = new();
            /// <summary>Scene units from the eye (the window's is 1).</summary>
            public float depth;
            public ZumiDraw.Parts outline;
        }

        // far to near
        readonly List<DepthLayer> depthLayers = new();
        // the 3D world
        sealed class WorldProp
        {
            public Transform root, model;
            public Material material;
            public Mesh mesh;
            public Texture2D texture;
            public readonly ZumiDraw.Parts label = new() { blended = true, queue = 3045 };
            public float at;
        }

        Transform world;
        readonly List<WorldProp> worldProps = new();
        readonly List<Material> worldMaterials = new();
        readonly List<Mesh> worldMeshes = new();
        readonly List<Texture2D> worldTextures = new();
        readonly ZumiDraw.Parts worldParts = new() { blended = true, queue = 3019 };
        Material frameMaterial, worldRimMaterial;
        // sound
        AudioSource voiceSource, sfxSource, musicSource;
        AudioClip voiceClip, sfxClip, musicClip;
        Transform soundCard;
        readonly ZumiDraw.Parts soundParts = new() { blended = true, queue = 3450 };
        readonly List<Transform> waveBars = new();
        bool sfxPlayed;
        int soundCardFor;
        CancellationTokenSource cancel;

        public void Init(Shader flatShader, ZumiCaption caption, ZumiReader reader)
        {
            flat = flatShader;
            this.caption = caption;
            this.reader = reader;
        }

        /// <summary>Starts the playback of how that comic was made: its book comes forward and opens at once, and its
        /// pencil pages fly out of it.</summary>
        public async void Play(ZumiBook comic, string title)
        {
            cancel = new CancellationTokenSource();
            book = comic;
            comicTitle = title;
            bookAway = false;
            anchor = ZumiFlowKit.LevelHead();
            var at = anchor.position + anchor.rotation * new Vector3(0f, -BookDrop, BookAhead);
            // the cover toward the eyes, tipped back a little, like a book held up to show
            bookPose = new Pose(at, Quaternion.LookRotation(anchor.position - at, Vector3.up) * Quaternion.Euler(-12f, 0f, 0f));
            if (book) book.Showcase(bookPose, BookHeight);
            data = await ZumiMakingOfData.Get();
            if (!this) return;
            if (data == null)
            {
                Debug.LogWarning("[Zumi] making-of: the bundle is missing; straight to the end");
                running = true;
                End();
                return;
            }
            StageSeconds[StageCharacters] = data.cast is { Count: > 0 } ? CharactersSeconds : 0f;
            BuildGrid();
            BuildHeader();
            BuildCharacters();
            caption.Show(StageLines[0], CaptionBelow);
            pinch = new ZumiPinch();
            pinch.Arm();
            startedAt = Time.time;
            running = true;
            LoadSounds();
            // from the start: on a fresh install the episode is still being copied out of the APK for a while
            LoadScenes();
            Debug.Log($"[Zumi] making-of: playing, {TotalSeconds:F0} s");
        }

        void Update()
        {
            if (!running) return;
            Elapsed = Time.time - startedAt;
            if (pinch.Closed() && Elapsed > 1f)
            {
                Skip();
                return;
            }
            var t = Elapsed;
            var index = 0;
            while (index < StageSeconds.Length && t >= StageSeconds[index])
            {
                t -= StageSeconds[index];
                index++;
            }
            if (index >= StageSeconds.Length)
            {
                if (t >= OutroSeconds) End();
                else Outro(t);
                return;
            }
            if (index != StageIndex)
            {
                StageIndex = index;
                PlaybackStage = StageNames[index];
                stageText.text = PlaybackStage;
                // steps counted over the stages that play (the characters' may be skipped)
                int step = 0, steps = 0;
                for (var i = 0; i < StageSeconds.Length; i++)
                    if (StageSeconds[i] > 0f)
                    {
                        steps++;
                        if (i <= index) step++;
                    }
                stepText.text = $"Step {step} of {steps}";
                Debug.Log($"[Zumi] making-of: stage {PlaybackStage}");
                if (index is StageDepth or StageWorld)
                    Debug.Log($"[Zumi] making-of: {(index == StageDepth ? $"depth scene {(DepthLoaded ? $"loaded, {DepthLayers} layers" : $"missing ({DepthError ?? "still loading"})")}" : $"world {(WorldLoaded ? $"{WorldPlace}, {worldProps.Count} props" : $"missing ({WorldError ?? "still loading"})")}")}");
                // a load that gave up tries again
                if (!scenesLoading && (!DepthLoaded || !WorldLoaded) && index < StageWorld) LoadScenes();
                // Zumi says what this step does, for the whole step
                caption.Show(StageLines[index], CaptionBelow);
            }
            barFill.localScale = new Vector3(Mathf.Max(0.001f, Elapsed / TotalSeconds), 1f, 1f);
            switch (index)
            {
                case 0: Gather(t); break;
                case 1: Colour(t); break;
                case 2: Panels(t); break;
                case StageCharacters: Characters(t); break;
                case StageDepth: Depth(t); break;
                case StageWorld: World(t); break;
                case StageVoice: Sound(t); break;
            }
            Music();
        }

        // ---- the grid ----------------------------------------------------------------------------------------

        Vector3 GridPoint(float x, float y, float z = 0f) => anchor.position + anchor.rotation * new Vector3(x, y - GridDrop, GridDistance + z);
        Quaternion Facing(Vector3 at) => ZumiFlowKit.Facing(at, anchor.position);

        void BuildGrid()
        {
            var n = data.pages.Count;
            var rows = Mathf.CeilToInt(n / (float)Columns);
            // the hero: the page whose balloons have the most different speakers, not the one the depth stage lifts
            var heroIndex = 0;
            var best = -1;
            for (var i = 0; i < n; i++)
            {
                var score = new HashSet<string>(Labelled(data.pages[i]).ConvertAll(Who)).Count;
                if (data.depth != null && i == data.depth.page - 1 && n > 1) score = -1;
                if (score <= best) continue;
                best = score;
                heroIndex = i;
            }
            for (var i = 0; i < n; i++)
            {
                var page = data.pages[i];
                var isHero = i == heroIndex;
                var aspect = page.Pixels.x / page.Pixels.y;
                var size = new Vector2(PageHeight * aspect, PageHeight);
                var col = i % Columns;
                var row = i / Columns;
                var at = GridPoint((col - (Columns - 1) / 2f) * (size.x + Gap), ((rows - 1) / 2f - row) * (size.y + Gap));
                var view = new PageView { data = page, size = size, cell = new Pose(at, Facing(at)) };
                var tex = page.pencilTexture;
                view.root = new GameObject($"Making-of page {i + 1}").transform;
                // the hero draws after the grid it passes in front of
                if (isHero) view.parts.queue = 3012;
                view.picture = ZumiFlowKit.Picture(tex, Color.white, isHero ? 3010 : 2990);
                ZumiFlowKit.SetSecond(view.picture, page.colourTexture);
                ZumiFlowKit.Card("Picture", view.root, size, view.picture);
                view.mask = ZumiFlowKit.Picture(page.maskTexture, new Color(1f, 1f, 1f, 0f), isHero ? 3011 : 2991);
                view.maskRenderer = ZumiFlowKit.Card("Masks", view.root, size, view.mask);
                view.maskRenderer.transform.localPosition = new Vector3(0f, 0f, -0.0008f);
                view.maskRenderer.enabled = false;
                // out of the open book: a page about its height, just in front of its leaves
                var from = bookPose.position + (anchor.position - bookPose.position).normalized * 0.03f;
                view.from = new Pose(from, Facing(from));
                view.fromSize = size * (BookHeight * 0.85f / size.y);
                view.root.SetPositionAndRotation(view.from.position, view.from.rotation);
                view.root.localScale = new Vector3(view.fromSize.x / size.x, view.fromSize.y / size.y, 1f);
                view.root.gameObject.SetActive(false);
                BuildOverlays(view, isHero);
                pages.Add(view);
                if (isHero) hero = view;
            }
        }

        // page pixels (from the top left) to the page card's local metres
        static Vector3 OnPage(PageView v, float px, float py, float z = -0.0015f) =>
            new((px / v.data.Pixels.x - 0.5f) * v.size.x, (0.5f - py / v.data.Pixels.y) * v.size.y, z);

        static List<ZumiMakingOfData.Balloon> Labelled(ZumiMakingOfData.Page page)
        {
            var list = new List<ZumiMakingOfData.Balloon>();
            foreach (var balloon in page.balloons)
            {
                if (list.Count >= BalloonsPerPage || balloon.box is not { Length: 4 } || string.IsNullOrWhiteSpace(balloon.text)) continue;
                if (balloon.kind == "caption" && page.balloons.Count > BalloonsPerPage) continue;
                list.Add(balloon);
            }
            return list;
        }

        static string Who(ZumiMakingOfData.Balloon balloon) =>
            string.IsNullOrEmpty(balloon.speaker) ? (balloon.kind == "sfx" ? "Sound" : "Caption") : balloon.speaker;

        // words into lines no wider than max, at most LabelLines of them
        static List<string> Wrap(string s, float max)
        {
            var lines = new List<string>();
            var line = "";
            foreach (var word in s.Split(' '))
            {
                var next = line.Length == 0 ? word : line + " " + word;
                if (line.Length > 0 && ZumiDraw.Width(next, LabelCap) > max)
                {
                    lines.Add(line);
                    line = word;
                }
                else line = next;
            }
            if (line.Length > 0) lines.Add(line);
            if (lines.Count > LabelLines)
            {
                lines.RemoveRange(LabelLines, lines.Count - LabelLines);
                var last = lines[^1].TrimEnd('.', ',', ' ');
                while (last.Length > 0 && ZumiDraw.Width(last + "...", LabelCap) > max)
                {
                    var cut = last.LastIndexOf(' ');
                    last = last.Substring(0, cut > 0 ? cut : last.Length - 1);
                }
                lines[^1] = last + "...";
            }
            return lines;
        }

        static float Widest(string s)
        {
            var w = 0f;
            foreach (var line in s.Split('\n')) w = Mathf.Max(w, ZumiDraw.Width(line, LabelCap));
            return w;
        }

        void BuildOverlays(PageView v, bool labelled)
        {
            // no frame outlines on the pages (owner, 2026-11-16): the mask overlays show the panels and balloons
            // only the hero's balloons are typed out, one after the other, in a column beside the page (off the art),
            // each at its balloon's height with an amber line from the balloon
            var start = 0f;
            var above = v.size.y / 2f;
            var left = v.size.x / 2f + 0.014f;
            const float pad = 0.007f;
            foreach (var balloon in labelled ? Labelled(v.data) : new List<ZumiMakingOfData.Balloon>())
            {
                var lines = Wrap($"{Who(balloon)}: {Capitalise(balloon.text)}", LabelWidth - 2f * pad);
                var full = string.Join("\n", lines);
                var width = Widest(full) + 2f * pad;
                var height = lines.Count * LabelCap * 1.6f + LabelCap * 1.2f;
                var centre = OnPage(v, balloon.box[2], (balloon.box[1] + balloon.box[3]) / 2f);
                var y = Mathf.Min(centre.y, above - height / 2f - 0.004f);
                y = Mathf.Max(y, -v.size.y / 2f + height / 2f);
                above = y - height / 2f;
                var plate = ZumiDraw.Shape(flat, v.labelParts, "Label plate", v.root, 0f, ZumiDraw.Plate, 3, ZumiDraw.Rounded(width, height, LabelCap * 1.2f).MovedBy(new Vector2(width / 2f, 0f)));
                plate.localPosition = new Vector3(left, y, -0.0035f);
                // the plate grows with the text as it types (no empty pill before)
                plate.localScale = new Vector3(0.0001f, 1f, 1f);
                var leader = ZumiDraw.Shape(flat, v.labelParts, "Label line", v.root, 0f, ZumiDraw.SoftInk, 2, ZumiDraw.Box(0f, -0.0008f, 1f, 0.0016f));
                leader.localPosition = new Vector3(Mathf.Min(centre.x, left), y, -0.0032f);
                leader.localScale = new Vector3(0.0001f, 1f, 1f);
                var label = ZumiDraw.Text(flat, v.labelParts, "Label", v.root, new Vector3(left + pad, y, -0.004f), LabelCap, ZumiDraw.Ink, 4, "");
                label.anchor = TextAnchor.MiddleLeft;
                label.alignment = TextAlignment.Left;
                v.labels.Add(new Label { text = label, plate = plate, leader = leader, leaderLength = left - leader.localPosition.x, full = full, start = start, width = width });
                start += full.Length / TypeCharsPerSecond + 0.5f;
            }
            v.parts.SetAlpha(0f);
            v.labelParts.SetAlpha(0f);
        }

        static string Capitalise(string s)
        {
            // the transcription is in capitals, as lettered; it reads better in sentence case beside the page
            if (string.IsNullOrEmpty(s)) return s;
            var lower = s.ToLowerInvariant();
            var chars = lower.ToCharArray();
            var start = true;
            for (var i = 0; i < chars.Length; i++)
            {
                if (start && char.IsLetter(chars[i]))
                {
                    chars[i] = char.ToUpperInvariant(chars[i]);
                    start = false;
                }
                if (chars[i] is '.' or '!' or '?') start = true;
            }
            return new string(chars).Replace(" i ", " I ").Replace(" i'", " I'");
        }


        void BuildHeader()
        {
            header = new GameObject("Making-of header").transform;
            var rows = Mathf.CeilToInt(pages.Count / (float)Columns);
            var top = rows * (PageHeight + Gap) / 2f + 0.14f;
            var at = GridPoint(0f, top);
            header.SetPositionAndRotation(at, Facing(at));
            var plateWidth = BarWidth + 0.08f;
            ZumiDraw.Shape(flat, headerParts, "Plate", header, 0f, ZumiDraw.Plate, 0, ZumiDraw.Rounded(plateWidth, 0.15f, 0.035f));
            var heading = ZumiDraw.Text(flat, headerParts, "Title", header, new Vector3(0f, 0.046f, -0.002f), 0.015f, ZumiDraw.SoftInk, 2, string.Format(HeaderTitle, comicTitle));
            heading.fontStyle = FontStyle.Bold;
            stageText = ZumiDraw.Text(flat, headerParts, "Stage", header, new Vector3(0f, 0.012f, -0.002f), HeaderCap, ZumiDraw.Ink, 2, StageNames[0]);
            stepText = ZumiDraw.Text(flat, headerParts, "Step", header, new Vector3(0f, -0.022f, -0.002f), 0.014f, ZumiDraw.SoftInk, 2, "");
            ZumiDraw.Shape(flat, headerParts, "Bar", header, -0.001f, ZumiDraw.Hex(0xE2D3C3), 1, ZumiDraw.Rounded(BarWidth, 0.01f, 0.005f).MovedBy(new Vector2(0f, -0.047f)));
            barFill = new GameObject("Fill").transform;
            barFill.SetParent(header, false);
            barFill.localPosition = new Vector3(-BarWidth / 2f, -0.047f, -0.002f);
            ZumiDraw.Shape(flat, headerParts, "Fill", barFill, 0f, ZumiDraw.Hover, 2, ZumiDraw.Box(0f, -0.005f, BarWidth, 0.01f));
        }

        // ---- the stages --------------------------------------------------------------------------------------

        void Gather(float t)
        {
            if (t >= BookPutAway && !bookAway)
            {
                bookAway = true;
                if (book) book.PutAway();
            }
            for (var i = 0; i < pages.Count; i++)
            {
                var v = pages[i];
                var at = t - PagesOut - i * PageStagger;
                var k = ZumiFlowKit.Smooth(at / PageFlight);
                if (v.root.gameObject.activeSelf != at > 0f) v.root.gameObject.SetActive(at > 0f);
                var lift = Mathf.Sin(k * Mathf.PI) * 0.06f;
                v.root.SetPositionAndRotation(Vector3.Lerp(v.from.position, v.cell.position, k) + Vector3.up * lift, Quaternion.Slerp(v.from.rotation, v.cell.rotation, k));
                var s = Vector2.Lerp(new Vector2(v.fromSize.x / v.size.x, v.fromSize.y / v.size.y), Vector2.one, k);
                v.root.localScale = new Vector3(s.x, s.y, 1f);
            }
        }

        void SettleGrid()
        {
            foreach (var v in pages)
            {
                v.root.gameObject.SetActive(true);
                v.root.SetPositionAndRotation(v.cell.position, v.cell.rotation);
                v.root.localScale = Vector3.one;
            }
            // the book is gone by now (put away during Scanned)
            if (book && book.State == "showcase")
            {
                bookAway = true;
                book.Stow();
            }
        }

        void Colour(float t)
        {
            SettleGrid();
            for (var i = 0; i < pages.Count; i++)
            {
                var v = pages[i];
                var wave = i % Columns + (i / Columns) * 0.6f;
                var mix = ZumiFlowKit.Smooth((t - 0.6f - wave * 1.1f) / 1.4f);
                ZumiFlowKit.SetMix(v.picture, mix);
                v.root.localScale = Vector3.one * (1f + 0.05f * Mathf.Sin(mix * Mathf.PI));
            }
        }

        Vector3 NearPoint => anchor.position + anchor.rotation * Near;

        // a page from its cell (k 0) to the reading place (k 1)
        void Bring(PageView v, float k)
        {
            v.root.SetPositionAndRotation(Vector3.Lerp(v.cell.position, NearPoint, k), Quaternion.Slerp(v.cell.rotation, Facing(NearPoint), k));
            v.root.localScale = Vector3.one * Mathf.Lerp(1f, NearScale, k);
        }

        void Panels(float t)
        {
            // the hero comes forward once the grid is outlined, and goes back when its balloons are read
            var near = ZumiFlowKit.Smooth((t - HeroIn) / 1f) * (1f - ZumiFlowKit.Smooth((t - HeroOut) / 1f));
            for (var i = 0; i < pages.Count; i++)
            {
                var v = pages[i];
                ZumiFlowKit.SetMix(v.picture, 1f);
                var isHero = v == hero;
                Bring(v, isHero ? near : 0f);
                var dim = isHero ? 1f : 1f - 0.65f * near;
                ZumiFlowKit.SetTint(v.picture, new Color(1f, 1f, 1f, dim));
                var o = isHero ? 0f : i * 0.4f;
                v.parts.SetAlpha(dim);
                // the labels go before the page moves back (it starts back at HeroOut)
                v.labelParts.SetAlpha(isHero ? 1f - ZumiFlowKit.Smooth((t - HeroOut + LabelFade + 0.05f) / LabelFade) : 0f);
                // the masks fade in over the colour, page after page
                var m = ZumiFlowKit.Smooth((t - o - 0.4f) / 1.2f);
                v.maskRenderer.enabled = m > 0f;
                ZumiFlowKit.SetTint(v.mask, new Color(1f, 1f, 1f, 0.7f * m * dim));
                // the balloons' text types itself, the lines still to come kept as blank lines so the text stays put
                foreach (var label in v.labels)
                {
                    var typed = Mathf.Clamp(Mathf.FloorToInt((t - HeroIn - 1.2f - label.start) * TypeCharsPerSecond), 0, label.full.Length);
                    var s = label.full.Substring(0, typed);
                    var shown = s + new string('\n', label.full.Split('\n').Length - s.Split('\n').Length);
                    if (label.text.text == shown) continue;
                    label.text.text = shown;
                    label.plate.localScale = new Vector3(typed == 0 ? 0.0001f : (Widest(s) + 0.014f) / label.width, 1f, 1f);
                    label.leader.localScale = new Vector3(typed == 0 ? 0.0001f : label.leaderLength, 1f, 1f);
                }
            }
        }

        void Depth(float t)
        {
            Panels(PanelsSeconds + 10f);
            // back in the grid, the hero draws in the grid's order again (the lifted panel passes in front of it)
            if (hero != null)
            {
                hero.picture.renderQueue = 2990;
                hero.mask.renderQueue = 2991;
            }
            // the overlays fade away first; the other pages dim
            // (already gone when the characters' stage played)
            var overlays = StageSeconds[StageCharacters] > 0f ? 0f : 1f - ZumiFlowKit.Smooth(t / 0.8f);
            if (characterRoot) characterRoot.gameObject.SetActive(false);
            var depthPage = data.depth != null ? Mathf.Clamp(data.depth.page - 1, 0, pages.Count - 1) : 0;
            // they stay dimmed into the 3D world when it follows
            var dim = ZumiFlowKit.Smooth(t / 1f) * (WorldLoaded ? 1f : 1f - ZumiFlowKit.Smooth((t - DepthSeconds + 1.2f) / 1f));
            for (var i = 0; i < pages.Count; i++)
            {
                var v = pages[i];
                v.parts.SetAlpha(overlays);
                v.labelParts.SetAlpha(0f);
                ZumiFlowKit.SetTint(v.mask, new Color(1f, 1f, 1f, 0.7f * overlays));
                ZumiFlowKit.SetTint(v.picture, new Color(1f, 1f, 1f, i == depthPage ? 1f : 1f - 0.65f * dim));
            }
            if (depthScene == null || !depthPivot || depthLayers.Count == 0)
            {
                // no scene: the page itself lifts toward the reader and back
                var lift = Mathf.Sin(Mathf.Clamp01(t / DepthSeconds) * Mathf.PI);
                var v = pages[depthPage];
                v.root.position = v.cell.position - (v.cell.position - anchor.position).normalized * 0.35f * lift;
                v.root.localScale = Vector3.one * (1f + 0.8f * lift);
                return;
            }
            // the panel lifts out (0.6 to 2.6 s), turns its side to the reader (2.2 to 4), its layers slide apart (2.6 to
            // 4.2) and sway; they close up (7.6 to 9), it turns back (8.2 to 9.6) and settles onto its page (9.6 to 11.2),
            // where it fades into the same panel printed there
            var home = DepthHome();
            var front = anchor.position + anchor.rotation * new Vector3(0f, -0.065f, 0.66f);
            var lifted = ZumiFlowKit.Smooth((t - 0.6f) / 2f) * (1f - ZumiFlowKit.Smooth((t - 9.6f) / 1.6f));
            var open = ZumiFlowKit.Smooth((t - 2.6f) / 1.6f) * (1f - ZumiFlowKit.Smooth((t - 7.6f) / 1.4f));
            var turned = ZumiFlowKit.Smooth((t - 2.2f) / 1.8f) * (1f - ZumiFlowKit.Smooth((t - 8.2f) / 1.4f));
            var fade = 1f - ZumiFlowKit.Smooth((t - DepthSeconds + 0.6f) / 0.4f);
            depthPivot.gameObject.SetActive(t > 0.5f && fade > 0f);
            var scale = Mathf.Lerp(1f, DepthScale, lifted);
            var yaw = DepthTurn * turned + Mathf.Sin((t - 4f) * 1.4f) * 5f * open;
            DepthTurnDegrees = yaw;
            var facing = Facing(Vector3.Lerp(home, front, lifted));
            var rotation = facing * Quaternion.Euler(0f, yaw, 0f);
            // it turns about the middle of its stack, not about its front
            var middle = (Z(depthLayers[0]) + Z(depthLayers[^1])) / 2f * scale;
            depthPivot.SetPositionAndRotation(Vector3.Lerp(home, front, lifted) + (facing * Vector3.forward - rotation * Vector3.forward) * middle, rotation);
            depthPivot.localScale = Vector3.one * scale;
            // each layer keeps its own place and slides along the panel's axis to its slot in an even stack, the front
            // layer's depth kept, the background farthest, the stack's middle where it was
            var n = depthLayers.Count;
            var gap = DepthGap / DepthScale;
            var near = Z(depthLayers[n - 1]);
            var shift = middle / scale - (near + (n - 1) * gap / 2f);
            var axis = depthPivot.TransformVector(Vector3.forward);
            for (var i = 0; i < n; i++)
            {
                var layer = depthLayers[i];
                var slot = near + (n - 1 - i) * gap + shift;
                // pivot units (metres at scale 1) along +z, away from the reader
                var offset = open * (slot - Z(layer));
                for (var k = 0; k < layer.nodes.Count; k++)
                {
                    var node = layer.nodes[k];
                    node.transform.localPosition = layer.homes[k] + node.transform.parent.InverseTransformVector(axis * offset);
                    depthScene.SetLook(node, new Color(1f, 1f, 1f, fade), 0f);
                }
                layer.outline.SetAlpha(fade * ZumiFlowKit.Smooth(open / 0.4f));
            }
            DepthStackMetres = (Z(depthLayers[0]) - Z(depthLayers[n - 1])) * (1f - open) * scale + (n - 1) * gap * open * scale;
        }

        // a layer's distance behind the panel's window, in pivot units (metres at scale 1)
        float Z(DepthLayer layer) => (layer.depth - 1f) * depthUnit;

        Vector3 DepthHome()
        {
            var page = pages[Mathf.Clamp(data.depth.page - 1, 0, pages.Count - 1)];
            var box = data.depth.box;
            return page.root.TransformPoint(OnPage(page, (box[0] + box[2]) / 2f, (box[1] + box[3]) / 2f, -0.002f));
        }

        // ---- character identification: each character in its colour, its appearances outlined and joined page by
        // page, its name at its first appearance --------------------------------------------------------------

        sealed class Sighting
        {
            public Transform outline, label;
            public float at;
        }

        sealed class Link
        {
            public Transform line, halo;
            public float at, length;
        }

        // One character at a time, the main ones first (most appearances): its boxes and its lines draw page to page
        // in its slot, then it settles to a faint trace while the next one draws. The minor ones (fewer than
        // MinorBelow appearances, or past the first MainMost) only get their boxes, together, at the end. Then all of it fades.
        sealed class Member
        {
            public readonly ZumiDraw.Parts parts = new() { blended = true, queue = 3030 };
            public float start, end;
        }

        Transform characterRoot;
        readonly List<Member> members = new();
        readonly List<Sighting> sightings = new();
        readonly List<Link> links = new();
        public const float CharacterLine = 0.0014f, CharacterSlot = 1.8f, CharactersFade = 0.5f, Trace = 0.15f;
        public const int MinorBelow = 3, MainMost = 3;

        void BuildCharacters()
        {
            if (data.cast is not { Count: > 0 }) return;
            characterRoot = new GameObject("Characters").transform;
            var centre = anchor.position + anchor.rotation * new Vector3(0f, -GridDrop, GridDistance);
            characterRoot.SetPositionAndRotation(centre, Facing(centre));
            // each member's appearances, in page order, on the pages that are on show; the main ones first
            var cast = new List<(ZumiMakingOfData.CastMember member, List<(PageView v, ZumiMakingOfData.Character ch)> seen)>();
            foreach (var member in data.cast)
            {
                var seen = new List<(PageView v, ZumiMakingOfData.Character ch)>();
                foreach (var v in pages)
                    foreach (var ch in v.data.characters ?? new List<ZumiMakingOfData.Character>())
                        if (ch.cast == member.id && ch.box is { Length: 4 }) seen.Add((v, ch));
                if (seen.Count > 0) cast.Add((member, seen));
            }
            cast.Sort((a, b) => b.seen.Count.CompareTo(a.seen.Count));
            var mains = 0;
            foreach (var (_, seen) in cast) if (seen.Count >= MinorBelow && mains < MainMost) mains++;
            var minorsAt = 0.6f + mains * CharacterSlot;
            for (var c = 0; c < cast.Count; c++)
            {
                var (member, seen) = cast[c];
                if (!ColorUtility.TryParseHtmlString(member.colour, out var colour)) colour = ZumiDraw.Hover;
                var main = c < mains;
                var who = new Member { start = main ? 0.6f + c * CharacterSlot : minorsAt, end = main ? 0.6f + (c + 1) * CharacterSlot : 99f };
                members.Add(who);
                var characterParts = who.parts;
                var step = (CharacterSlot - 0.4f) / seen.Count;
                Vector3? last = null;
                for (var i = 0; i < seen.Count; i++)
                {
                    var (v, ch) = seen[i];
                    var at = main ? who.start + i * step : minorsAt + c * 0.12f;
                    // the outline, in the page's frame (cell pose), just in front of it
                    var a = OnPage(v, ch.box[0], ch.box[1]);
                    var b = OnPage(v, ch.box[2], ch.box[3]);
                    float w = b.x - a.x, h = a.y - b.y;
                    var mid = (a + b) / 2f;
                    var outline = new GameObject($"{member.name} {i + 1}").transform;
                    outline.SetParent(characterRoot, false);
                    outline.SetPositionAndRotation(v.cell.position + v.cell.rotation * new Vector3(mid.x, mid.y, -0.004f), v.cell.rotation);
                    const float t = 0.0022f;
                    ZumiDraw.Shape(flat, characterParts, "Box", outline, 0f, colour, 1,
                        ZumiDraw.Box(-w / 2f, h / 2f - t, w, t), ZumiDraw.Box(-w / 2f, -h / 2f, w, t), ZumiDraw.Box(-w / 2f, -h / 2f, t, h), ZumiDraw.Box(w / 2f - t, -h / 2f, t, h));
                    ZumiDraw.Shape(flat, characterParts, "Wash", outline, 0.0002f, new Color(colour.r, colour.g, colour.b, 0.18f), 0, ZumiDraw.Box(-w / 2f, -h / 2f, w, h));
                    outline.gameObject.SetActive(false);
                    Transform label = null;
                    if (i == 0 && main)
                    {
                        // the name, over the first appearance, on a plate with a dot of its colour
                        // about 0.8 degrees at the grid's metre
                        const float cap = 0.014f;
                        var width = ZumiDraw.Width(member.name, cap) + 0.03f;
                        label = new GameObject($"{member.name} name").transform;
                        label.SetParent(outline, false);
                        label.localPosition = new Vector3(0f, h / 2f + 0.014f, -0.002f);
                        ZumiDraw.Shape(flat, characterParts, "Plate", label, 0f, ZumiDraw.Plate, 2, ZumiDraw.Rounded(width, cap * 2.4f, cap * 1.2f));
                        ZumiDraw.Shape(flat, characterParts, "Dot", label, -0.0005f, colour, 3, ZumiDraw.Moved(ZumiDraw.Disc(cap * 0.45f, 16), new Vector2(-width / 2f + 0.009f, 0f)));
                        ZumiDraw.Text(flat, characterParts, "Name", label, new Vector3(0.004f, 0f, -0.001f), cap, ZumiDraw.Ink, 3, member.name);
                    }
                    sightings.Add(new Sighting { outline = outline, label = label, at = at });
                    // the line from the last appearance to this one, drawn as this one comes
                    var here = characterRoot.InverseTransformPoint(outline.position);
                    if (main && last is { } from)
                    {
                        var d = new Vector2(here.x - from.x, here.y - from.y);
                        var angle = Mathf.Atan2(d.y, d.x) * Mathf.Rad2Deg;
                        Transform Line(string name, float width, Color col, int order)
                        {
                            var line = ZumiDraw.Shape(flat, characterParts, name, characterRoot, 0f, col, order, ZumiDraw.Box(0f, -width / 2f, 1f, width));
                            line.localPosition = new Vector3(from.x, from.y, -0.012f);
                            line.localRotation = Quaternion.Euler(0f, 0f, angle);
                            line.localScale = new Vector3(0.0001f, 1f, 1f);
                            return line;
                        }
                        links.Add(new Link
                        {
                            halo = Line("Halo", CharacterLine * 4f, new Color(colour.r, colour.g, colour.b, 0.22f), 1),
                            line = Line("Line", CharacterLine, colour, 2),
                            at = at - step * 0.8f, length = d.magnitude,
                        });
                    }
                    last = here;
                }
                characterParts.SetAlpha(1f);
            }
            characterRoot.gameObject.SetActive(false);
        }

        void Characters(float t)
        {
            Panels(PanelsSeconds + 10f);
            // the panels' outlines and masks make way
            var overlays = 1f - ZumiFlowKit.Smooth(t / 0.6f);
            foreach (var v in pages)
            {
                v.parts.SetAlpha(overlays);
                v.labelParts.SetAlpha(0f);
                ZumiFlowKit.SetTint(v.mask, new Color(1f, 1f, 1f, 0.7f * overlays));
            }
            if (!characterRoot) return;
            characterRoot.gameObject.SetActive(true);
            foreach (var s in sightings)
            {
                var k = ZumiFlowKit.OutBack((t - s.at) / 0.35f);
                s.outline.gameObject.SetActive(t >= s.at);
                if (t >= s.at) s.outline.localScale = Vector3.one * Mathf.Lerp(0.85f, 1f, k);
            }
            foreach (var l in links)
            {
                var k = ZumiFlowKit.Smooth((t - l.at) / 0.6f);
                var x = Mathf.Max(0.0001f, l.length * k);
                l.line.localScale = new Vector3(x, 1f, 1f);
                l.halo.localScale = new Vector3(x, 1f, 1f);
            }
            // a character drawn settles to a faint trace while the next one draws; all of it goes before the next stage
            var gone = 1f - ZumiFlowKit.Smooth((t - CharactersSeconds + CharactersFade + 0.1f) / CharactersFade);
            foreach (var m in members)
                m.parts.SetAlpha(gone * Mathf.Lerp(1f, Trace, ZumiFlowKit.Smooth((t - m.end) / 0.4f)));
        }

        // ---- loading the depth panel's scene and the 3D world ---------------------------------------------------

        // The episode is opened by the reader at launch; on a fresh install it is first copied out of the APK (a few
        // hundred MB), and until then it has no manifest. Both loads wait for it, try LoadTries times, and say why
        // they failed.
        async void LoadScenes()
        {
            if (scenesLoading || data == null) return;
            scenesLoading = true;
            try
            {
                if (!DepthLoaded) DepthError = await Tries("depth panel", TryLoadDepth);
                if (this && !WorldLoaded) WorldError = await Tries("3D world", TryLoadWorld);
            }
            finally
            {
                scenesLoading = false;
            }
        }

        async Task<string> Tries(string what, Func<Task<string>> load)
        {
            string why = null;
            for (var attempt = 1; attempt <= LoadTries && this; attempt++)
            {
                try
                {
                    why = await load();
                }
                catch (OperationCanceledException)
                {
                    return "cancelled";
                }
                catch (Exception e)
                {
                    why = $"{e.GetType().Name}: {e.Message}";
                }
                if (why == null) return null;
                Debug.LogWarning($"[Zumi] making-of: the {what} did not load (try {attempt} of {LoadTries}): {why}");
                if (attempt < LoadTries) await Task.Delay(1500);
            }
            return why;
        }

        async Task<ZumiManifest> OpenEpisode()
        {
            // up to two minutes: the first launch's copy of the episode
            for (var i = 0; i < 1200 && this && !cancel.IsCancellationRequested
                            && (reader?.Source == null || reader.Source.State is EpisodeSourceState.Closed or EpisodeSourceState.Opening); i++)
                await Task.Delay(100);
            return this && reader?.Source is { State: EpisodeSourceState.Ready } ? reader.Source.Manifest : null;
        }

        string NotOpen() => $"the episode is not open ({reader?.SourceState ?? "no reader"}{(reader?.SourceError != null ? $": {reader.SourceError}" : "")})";

        async Task<string> TryLoadDepth()
        {
            if (data.depth == null) return "the bundle names no depth panel";
            var manifest = await OpenEpisode();
            if (!this) return "gone";
            if (manifest == null) return NotOpen();
            var panel = manifest.panels.Find(p => p.id == data.depth.panel);
            if (panel == null || string.IsNullOrEmpty(panel.scene)) return $"the panel {data.depth.panel} has no scene in the episode";
            var glb = await reader.Source.Read(panel.scene, cancel.Token);
            if (!this) return "gone";
            if (glb == null) return $"{panel.scene} could not be read";
            var presenter = reader.GetComponent<ZumiPanelPresenter>();
            var pivot = new GameObject("Depth panel").transform;
            pivot.gameObject.SetActive(false);
            var eye = new GameObject("Eye").transform;
            eye.SetParent(pivot, false);
            var page = pages[Mathf.Clamp(data.depth.page - 1, 0, pages.Count - 1)];
            var box = data.depth.box;
            var heightMetres = (box[3] - box[1]) / page.data.Pixels.y * page.size.y;
            // a first load to learn the panel's size, at one metre, then the eye moved back by its unit
            var scene = await ZumiPanelScene.Load(glb, eye, 1f, presenter.WindowShader, presenter.CardShader, null, cancel.Token);
            if (!this || scene == null)
            {
                if (pivot) Destroy(pivot.gameObject);
                return this ? $"{panel.scene} did not build" : "gone";
            }
            depthUnit = heightMetres / Mathf.Max(scene.PanelSize.y, 1e-3f);
            scene.Root.localScale = Vector3.one * depthUnit;
            eye.localPosition = new Vector3(0f, 0f, -depthUnit);
            depthLayers.Clear();
            var layers = new List<ZumiPanelScene.Node>();
            foreach (var node in scene.Nodes)
            {
                if (node.kind == "window")
                {
                    scene.SetLook(node, new Color(1f, 1f, 1f, 0f), 0f);
                    continue;
                }
                // every layer whole, not only through its frame's window
                foreach (var m in node.materials) m.SetFloat("_StencilComp", (float)UnityEngine.Rendering.CompareFunction.Always);
                layers.Add(node);
            }
            // far to near; nodes at one depth (the lettering) are one sheet
            layers.Sort((a, b) => b.Depth.CompareTo(a.Depth));
            foreach (var node in layers)
            {
                if (depthLayers.Count == 0 || depthLayers[^1].depth - node.Depth > 0.01f) depthLayers.Add(new DepthLayer { depth = node.Depth });
                var layer = depthLayers[^1];
                layer.nodes.Add(node);
                layer.homes.Add(node.transform.localPosition);
            }
            foreach (var layer in depthLayers) Outline(layer);
            depthPivot = pivot;
            depthScene = scene;
            Debug.Log($"[Zumi] making-of: depth panel {data.depth.panel} loaded, {scene.Nodes.Count} nodes in {depthLayers.Count} layers");
            return null;
        }

        // a thin soft-ink rectangle round a layer's art, on its own plane, so the stack reads as sheets
        void Outline(DepthLayer layer)
        {
            var b = layer.nodes[0].bounds;
            foreach (var node in layer.nodes) b.Encapsulate(node.bounds);
            var queue = layer.nodes[^1].materials.Count > 0 ? layer.nodes[^1].materials[0].renderQueue : 3000;
            layer.outline = new ZumiDraw.Parts { blended = true, queue = queue };
            var holder = new GameObject("Sheet outline").transform;
            holder.SetParent(layer.nodes[0].transform, false);
            // the scene looks down its -z: turned round, the outline's front faces the reader
            holder.SetLocalPositionAndRotation(b.center, Quaternion.Euler(0f, 180f, 0f));
            float w = b.size.x, h = b.size.y, th = DepthOutline / (depthUnit * DepthScale);
            ZumiDraw.Shape(flat, layer.outline, "Outline", holder, 0f, new Color(ZumiDraw.SoftInk.r, ZumiDraw.SoftInk.g, ZumiDraw.SoftInk.b, 0.85f), 0,
                ZumiDraw.Box(-w / 2f, h / 2f - th, w, th), ZumiDraw.Box(-w / 2f, -h / 2f, w, th), ZumiDraw.Box(-w / 2f, -h / 2f, th, h), ZumiDraw.Box(w / 2f - th, -h / 2f, th, h));
            layer.outline.SetAlpha(0f);
        }

        async Task<string> TryLoadWorld()
        {
            var manifest = await OpenEpisode();
            if (!this) return "gone";
            if (manifest == null) return NotOpen();
            var meshes = manifest.episode?.places?.meshes;
            if (meshes is not { Count: > 0 }) return "the episode has no places";
            // the depth panel's place when it has props, else the first place that has them
            var panel = data.depth != null ? manifest.panels.Find(p => p.id == data.depth.panel) : null;
            var setting = panel?.frames?.Find(f => !string.IsNullOrEmpty(f.setting))?.setting;
            var place = meshes.Find(m => m.setting == setting && m.props is { Count: > 0 }) ?? meshes.Find(m => m.props is { Count: > 0 })
                        ?? meshes.Find(m => m.setting == setting) ?? meshes[0];
            var source = reader.Source;
            var token = cancel.Token;
            var frontFile = await source.Read(place.front, token);
            if (frontFile == null) return $"{place.front} could not be read";
            var backFile = string.IsNullOrEmpty(place.back) ? null : await source.Read(place.back, token);
            var (front, back) = await Task.Run(() => (ZumiGlb.Read(frontFile), backFile != null ? ZumiGlb.Read(backFile) : null), token);
            var textures = new List<Texture2D>();
            var props = new List<(PlaceProp data, ZumiGlb glb, Texture2D texture)>();
            try
            {
                var frontTexture = await ZumiPlaces.Picture(front, $"{place.setting} front", false, token);
                textures.Add(frontTexture);
                var backTexture = back != null ? await ZumiPlaces.Picture(back, $"{place.setting} back", false, token) : null;
                if (backTexture) textures.Add(backTexture);
                foreach (var prop in place.props ?? new List<PlaceProp>())
                {
                    try
                    {
                        var file = await source.Read(prop.model, token);
                        if (file == null) throw new InvalidOperationException($"{prop.model} could not be read");
                        var glb = await Task.Run(() => ZumiGlb.Read(file), token);
                        var texture = await ZumiPlaces.Picture(glb, prop.name, true, token);
                        textures.Add(texture);
                        props.Add((prop, glb, texture));
                    }
                    catch (OperationCanceledException)
                    {
                        throw;
                    }
                    catch (Exception e)
                    {
                        Debug.LogWarning($"[Zumi] making-of: the prop {place.setting}/{prop.name} is left out ({e.Message})");
                    }
                }
                if (!this) throw new OperationCanceledException();
                BuildWorld(place, front, frontTexture, back, backTexture, props);
            }
            catch
            {
                foreach (var tex in textures)
                    if (tex) Destroy(tex);
                throw;
            }
            WorldPlace = place.setting;
            Debug.Log($"[Zumi] making-of: 3D world {place.setting} loaded, {(front.triangles.Length + (back?.triangles.Length ?? 0)) / 3} triangles, {worldProps.Count} props");
            return null;
        }

        Material WorldMaterial(string name, Texture texture, int queue, bool masked, float shade)
        {
            var m = new Material(ZumiFlowKit.DioramaShader) { name = name, mainTexture = texture, renderQueue = queue };
            m.SetFloat("_Masked", masked ? 1f : 0f);
            m.SetVector("_Half", new Vector4(WorldWindow.x / 2f, WorldWindow.y / 2f, WorldCorner, 0f));
            m.SetFloat("_Shade", shade);
            worldMaterials.Add(m);
            return m;
        }

        Mesh WorldMesh(string name, ZumiGlb glb, bool normals)
        {
            var mesh = new Mesh { name = name, indexFormat = glb.positions.Length > 65535 ? UnityEngine.Rendering.IndexFormat.UInt32 : UnityEngine.Rendering.IndexFormat.UInt16 };
            mesh.SetVertices(glb.positions);
            mesh.SetUVs(0, glb.uvs);
            mesh.SetTriangles(glb.triangles, 0);
            if (normals) mesh.RecalculateNormals();
            worldMeshes.Add(mesh);
            return mesh;
        }

        static Transform Model(string name, Transform parent, Mesh mesh, Material material)
        {
            var go = new GameObject(name, typeof(MeshFilter), typeof(MeshRenderer));
            go.transform.SetParent(parent, false);
            go.GetComponent<MeshFilter>().sharedMesh = mesh;
            var renderer = go.GetComponent<MeshRenderer>();
            renderer.sharedMaterial = material;
            renderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            return go.transform;
        }

        // The window's frame: its origin the opening's middle, +z into the place. The place's eye stands in front of the
        // opening where the opening spans WorldViewHalfDegrees either side, and the place is scaled about that eye so
        // its near distance lands just behind the opening (and its far one no more than 0.6 m beyond it).
        void BuildWorld(PlaceMesh place, ZumiGlb front, Texture2D frontTexture, ZumiGlb back, Texture2D backTexture,
                        List<(PlaceProp data, ZumiGlb glb, Texture2D texture)> props)
        {
            world = new GameObject("3D world").transform;
            world.gameObject.SetActive(false);
            worldTextures.Add(frontTexture);
            if (backTexture) worldTextures.Add(backTexture);
            var half = Mathf.Min(WorldViewHalfDegrees, place.hDeg / 2f - 12f);
            var eye = WorldWindow.x / 2f / Mathf.Tan(Mathf.Max(half, 15f) * Mathf.Deg2Rad);
            var nearM = place.nearM ?? (place.medianM ?? 1f) * 0.5f;
            var farM = place.farM ?? (place.medianM ?? 1f) * 2f;
            var scale = Mathf.Min(eye * 1.12f / Mathf.Max(nearM, 0.05f), (eye + 0.6f) / Mathf.Max(farM, 0.1f));
            var view = new GameObject("Place").transform;
            view.SetParent(world, false);
            view.localPosition = new Vector3(0f, 0f, -eye);
            view.localScale = Vector3.one * scale;
            Model("front", view, WorldMesh($"{place.setting} front", front, false), WorldMaterial($"{place.setting} front", frontTexture, 3020, true, 0f));
            if (back != null && backTexture)
                Model("back", view, WorldMesh($"{place.setting} back", back, false), WorldMaterial($"{place.setting} back", backTexture, 3021, true, 0f));
            // a cream sheet in the opening, behind the place, shows where its mesh has holes; the frame and the rim round it
            ZumiDraw.Shape(flat, worldParts, "Opening", world, 0.001f, ZumiDraw.Plate, 0, ZumiDraw.Rounded(WorldWindow.x, WorldWindow.y, WorldCorner));
            frameMaterial = ZumiFlowKit.Picture(Texture2D.whiteTexture, ZumiDraw.Plate, 3030);
            const float frame = 0.012f, rim = 0.0055f;
            var band = Model("Frame", world, ZumiFlowKit.RoundedBand(WorldWindow + Vector2.one * (2f * frame), WorldCorner + frame, frame), frameMaterial);
            band.localPosition = new Vector3(0f, 0f, -0.001f);
            worldRimMaterial = new Material(ZumiFlowKit.RimShader) { name = "World rim", renderQueue = 3031 };
            var ring = Model("Rim", world, ZumiFlowKit.RoundedBand(WorldWindow + Vector2.one * (2f * (frame + rim)), WorldCorner + frame + rim, rim), worldRimMaterial);
            ring.localPosition = new Vector3(0f, 0f, -0.0015f);
            worldMeshes.Add(band.GetComponent<MeshFilter>().sharedMesh);
            worldMeshes.Add(ring.GetComponent<MeshFilter>().sharedMesh);

            // the props in a row on the opening's sill, a little in front of it, their heights relative to the tallest
            var tallest = 0f;
            foreach (var p in props) tallest = Mathf.Max(tallest, p.data.heightM);
            var k = PropTallest / Mathf.Max(tallest, 0.01f);
            var widths = new List<float>();
            var scales = new List<float>();
            var total = 0f;
            foreach (var p in props)
            {
                var box = p.glb.bounds;
                var height = p.data.bounds is { min: { Length: 3 }, max: { Length: 3 } } b ? b.max[1] - b.min[1] : box.size.y;
                var s = p.data.heightM * k / Mathf.Max(height, 1e-4f);
                scales.Add(s);
                widths.Add(Mathf.Max(box.size.x * s, 0.07f));
                total += widths[^1];
            }
            const float spacing = 0.03f;
            total += spacing * Mathf.Max(props.Count - 1, 0);
            var fit = Mathf.Min(1f, (WorldWindow.x + 0.1f) / Mathf.Max(total, 1e-3f));
            var x = -total * fit / 2f;
            for (var i = 0; i < props.Count; i++)
            {
                var (data, glb, texture) = props[i];
                worldTextures.Add(texture);
                var s = scales[i] * fit;
                var w = widths[i] * fit;
                var prop = new WorldProp { texture = texture, at = 3.4f + i * 0.85f };
                prop.root = new GameObject($"Prop {data.name}").transform;
                prop.root.SetParent(world, false);
                prop.root.localPosition = new Vector3(x + w / 2f, -WorldWindow.y / 2f - 0.01f, -0.07f);
                x += w + spacing * fit;
                prop.mesh = WorldMesh(data.name, glb, true);
                prop.material = WorldMaterial(data.name, texture, 3022, false, 1f);
                prop.model = Model("Model", prop.root, prop.mesh, prop.material);
                prop.model.localScale = Vector3.one * s;
                prop.model.localPosition = new Vector3(-glb.bounds.center.x * s, -glb.bounds.min.y * s, -glb.bounds.center.z * s);
                // its name on a small cream label under it
                var name = PropName(data.name);
                const float cap = 0.0095f;
                var labelWidth = ZumiDraw.Width(name, cap) + 0.018f;
                var label = new GameObject("Label").transform;
                label.SetParent(prop.root, false);
                label.localPosition = new Vector3(0f, -0.022f, -0.02f);
                ZumiDraw.Shape(flat, prop.label, "Plate", label, 0f, ZumiDraw.Plate, 0, ZumiDraw.Rounded(labelWidth, cap * 2.4f, cap * 1.2f));
                ZumiDraw.Text(flat, prop.label, "Name", label, new Vector3(0f, 0f, -0.001f), cap, ZumiDraw.Ink, 1, name);
                prop.label.SetAlpha(0f);
                prop.root.gameObject.SetActive(false);
                worldProps.Add(prop);
            }
        }

        static string PropName(string id)
        {
            var s = (id ?? "").Replace('-', ' ').Replace('_', ' ').Trim();
            return s.Length == 0 ? s : char.ToUpperInvariant(s[0]) + s.Substring(1);
        }

        // ---- 3D world: the place grows out of the depth panel's page into a window, turns slowly, its props pop in
        // one by one with their names, then it shrinks back into the page --------------------------------------

        void World(float t)
        {
            Panels(PanelsSeconds + 10f);
            if (hero != null)
            {
                hero.picture.renderQueue = 2990;
                hero.mask.renderQueue = 2991;
            }
            if (characterRoot) characterRoot.gameObject.SetActive(false);
            if (depthPivot) depthPivot.gameObject.SetActive(false);
            var depthPage = data.depth != null ? Mathf.Clamp(data.depth.page - 1, 0, pages.Count - 1) : 0;
            for (var i = 0; i < pages.Count; i++)
            {
                var v = pages[i];
                v.parts.SetAlpha(0f);
                v.labelParts.SetAlpha(0f);
                ZumiFlowKit.SetTint(v.mask, new Color(1f, 1f, 1f, 0f));
                // still dimmed from the depth stage; they come back at the end
                var dim = 1f - ZumiFlowKit.Smooth((t - WorldSeconds + 1.2f) / 1f);
                ZumiFlowKit.SetTint(v.picture, new Color(1f, 1f, 1f, i == depthPage ? 1f : 1f - 0.65f * dim));
            }
            if (!world) return;
            var home = data.depth != null ? DepthHome() : anchor.position + anchor.rotation * new Vector3(0f, -GridDrop, GridDistance);
            var front = anchor.position + anchor.rotation * new Vector3(0f, 0.0f, WorldDistance);
            var grown = ZumiFlowKit.Smooth((t - 0.1f) / 1.5f) * (1f - ZumiFlowKit.Smooth((t - 10f) / 1.5f));
            var shown = ZumiFlowKit.Smooth(t / 0.5f) * (1f - ZumiFlowKit.Smooth((t - 11.1f) / 0.5f));
            world.gameObject.SetActive(shown > 0f);
            var at = Vector3.Lerp(home, front, grown);
            // a slow turn, about 18 degrees either way, so the place's depth reads
            var yaw = 18f * Mathf.Sin((t - 1f) / 7f * Mathf.PI * 2f) * ZumiFlowKit.Smooth((t - 1f) / 1f) * grown;
            world.SetPositionAndRotation(at, Facing(at) * Quaternion.Euler(0f, yaw, 0f));
            world.localScale = Vector3.one * Mathf.Lerp(0.18f, 1f, grown);
            foreach (var m in worldMaterials)
            {
                m.SetMatrix("_Window", world.worldToLocalMatrix);
                m.SetFloat("_Opacity", shown);
            }
            worldParts.SetAlpha(shown);
            ZumiFlowKit.SetTint(frameMaterial, new Color(ZumiDraw.Plate.r, ZumiDraw.Plate.g, ZumiDraw.Plate.b, shown));
            worldRimMaterial.SetFloat("_Turn", -t * 0.9f);
            worldRimMaterial.SetColor("_Color", new Color(1f, 1f, 1f, 0.9f * shown));
            var popped = 0;
            for (var i = 0; i < worldProps.Count; i++)
            {
                var p = worldProps[i];
                var on = t >= p.at;
                p.root.gameObject.SetActive(on && shown > 0f);
                if (!on) continue;
                popped++;
                p.root.localScale = Vector3.one * Mathf.Max(0.001f, ZumiFlowKit.OutBack((t - p.at) / 0.5f));
                p.model.localRotation = Quaternion.Euler(0f, 22f * Mathf.Sin((t - p.at) * 0.8f + i), 0f);
                p.label.SetAlpha(ZumiFlowKit.Smooth((t - p.at - 0.25f) / 0.35f) * shown);
            }
            WorldPropsShown = popped;
        }

        // ---- voice, sound and music --------------------------------------------------------------------------

        async void LoadSounds()
        {
            // the episode may still be opening
            if (data == null || await OpenEpisode() == null || !this)
            {
                if (this) Debug.LogWarning($"[Zumi] making-of: no sounds, {NotOpen()}");
                return;
            }
            voiceSource = Source("Voice");
            sfxSource = Source("Sound effect");
            musicSource = Source("Music");
            musicSource.loop = true;
            voiceClip = await Clip(data.voice?.audio);
            sfxClip = await Clip(data.sfx?.audio);
            var track = reader.Source.Manifest?.episode?.music?.Find(m => m.id == data.music);
            musicClip = await Clip(track?.file);
            if (musicClip)
            {
                musicSource.clip = musicClip;
                musicSource.volume = 0f;
            }
        }

        AudioSource Source(string name)
        {
            var go = new GameObject(name);
            go.transform.SetParent(transform, false);
            var s = go.AddComponent<AudioSource>();
            s.playOnAwake = false;
            s.spatialBlend = 0f;
            return s;
        }

        async Task<AudioClip> Clip(string file)
        {
            if (string.IsNullOrEmpty(file) || reader.Source == null) return null;
            var bytes = await reader.Source.Read(file, cancel.Token);
            if (bytes == null || !this) return null;
            var wav = await Task.Run(() => ZumiWav.Read(bytes));
            if (wav == null) return null;
            var clip = AudioClip.Create(file, wav.frames, 1, wav.sampleRate, false);
            clip.SetData(wav.samples[0], 0);
            return clip;
        }

        void Music()
        {
            if (!musicSource || !musicClip) return;
            // silent until the voice stage, then it swells, and it goes with the end
            var swell = StageIndex >= StageVoice ? ZumiFlowKit.Smooth((Elapsed - StageStart(StageVoice)) / 6f) : 0f;
            var outro = 1f - ZumiFlowKit.Smooth((Elapsed - (TotalSeconds - 2.5f)) / 2.5f);
            musicSource.volume = MusicGain * swell * outro;
            if (swell > 0f && !musicSource.isPlaying) musicSource.Play();
        }

        static float StageStart(int index)
        {
            var s = 0f;
            for (var i = 0; i < index; i++) s += StageSeconds[i];
            return s;
        }

        void Sound(float t)
        {
            // the voice's page comes forward, then the sound effect's
            ZumiMakingOfData.Page voicePage = null, sfxPage = null;
            ZumiMakingOfData.Balloon voiceBalloon = null, sfxBalloon = null;
            if (data.voice != null) data.Find(data.voice.panel, data.voice.bubble, out voicePage, out voiceBalloon);
            if (data.sfx != null) data.Find(data.sfx.panel, data.sfx.bubble, out sfxPage, out sfxBalloon);
            var half = VoiceSeconds / 2f;
            var first = t < half;
            var local = first ? t : t - half;
            var page = first ? voicePage : sfxPage;
            var balloon = first ? voiceBalloon : sfxBalloon;
            var line = first ? data.voice : data.sfx;
            var forward = ZumiFlowKit.Smooth(local / 0.8f) * (1f - ZumiFlowKit.Smooth((local - half + 0.8f) / 0.8f));
            foreach (var v in pages)
            {
                var chosen = v.data == page;
                ZumiFlowKit.SetTint(v.picture, new Color(1f, 1f, 1f, chosen ? 1f : 1f - 0.65f * forward));
                Bring(v, chosen ? forward : 0f);
            }
            if (soundCardFor != (first ? 1 : 2))
            {
                soundCardFor = first ? 1 : 2;
                BuildSoundCard(first, line, page, balloon);
            }
            // the card fades in with the page and is gone before the page goes back (at half - 0.8)
            soundParts.SetAlpha(ZumiFlowKit.Smooth(local / 0.8f) * (1f - ZumiFlowKit.Smooth((local - half + 0.8f + LabelFade + 0.05f) / LabelFade)));
            if (first && local > 1f && !VoicePlayed && voiceSource)
            {
                VoicePlayed = true;
                if (voiceClip) voiceSource.PlayOneShot(voiceClip);
                Debug.Log($"[Zumi] making-of: voice {data.voice.speaker}: {data.voice.text}{(voiceClip ? "" : " (no audio)")}");
            }
            if (!first && local > 1f && !sfxPlayed && sfxSource)
            {
                sfxPlayed = true;
                if (sfxClip) sfxSource.PlayOneShot(sfxClip);
            }
            Wave(first ? voiceClip : sfxClip, local - 1f);
        }

        void BuildSoundCard(bool voice, ZumiMakingOfData.Sound line, ZumiMakingOfData.Page page, ZumiMakingOfData.Balloon balloon)
        {
            if (soundCard) Destroy(soundCard.gameObject);
            soundParts.Destroy();
            waveBars.Clear();
            if (line == null) return;
            soundCard = new GameObject(voice ? "voice" : "sfx").transform;
            var at = anchor.position + anchor.rotation * new Vector3(0.22f, 0.04f, 0.66f);
            soundCard.SetPositionAndRotation(at, ZumiFlowKit.Facing(at, anchor.position));
            var title = voice ? $"{line.speaker ?? "Voice"}" : "Sound effect";
            var text = Capitalise(line.text ?? "");
            const float cap = 0.012f;
            var width = Mathf.Max(ZumiDraw.Width(text, cap), 0.2f) + 0.05f;
            ZumiDraw.Shape(flat, soundParts, "Plate", soundCard, 0f, ZumiDraw.Plate, 0, ZumiDraw.Rounded(width, 0.12f, 0.03f));
            ZumiDraw.Text(flat, soundParts, "Who", soundCard, new Vector3(0f, 0.035f, -0.002f), cap * 0.9f, ZumiDraw.SoftInk, 2, title);
            ZumiDraw.Text(flat, soundParts, "Line", soundCard, new Vector3(0f, 0.01f, -0.002f), cap, ZumiDraw.Ink, 2, text);
            const int n = 36;
            var pitch = (width - 0.06f) / n;
            for (var i = 0; i < n; i++)
            {
                var bar = ZumiDraw.Shape(flat, soundParts, "Wave", soundCard, -0.002f, ZumiDraw.Hover, 1, ZumiDraw.Box(-pitch * 0.3f, -0.5f, pitch * 0.6f, 1f));
                bar.localPosition = new Vector3(-(width - 0.06f) / 2f + (i + 0.5f) * pitch, -0.028f, -0.002f);
                bar.localScale = new Vector3(1f, 0.003f, 1f);
                waveBars.Add(bar);
            }
            soundParts.SetAlpha(0f);
        }

        readonly float[] window = new float[256];

        // the bars follow the sound under the playhead: each bar a slice of the clip's next half second
        void Wave(AudioClip clip, float playing)
        {
            for (var i = 0; i < waveBars.Count; i++)
            {
                var level = 0.1f;
                if (clip && playing >= 0f && playing < clip.length)
                {
                    var at = Mathf.FloorToInt((playing + i * 0.5f / waveBars.Count) * clip.frequency);
                    if (at + window.Length < clip.samples)
                    {
                        clip.GetData(window, at);
                        var sum = 0f;
                        foreach (var s in window) sum += s * s;
                        level = Mathf.Sqrt(sum / window.Length) * 4f;
                    }
                }
                else if (!clip && playing >= 0f && playing < 2f) level = 0.3f + 0.3f * Mathf.Abs(Mathf.Sin(playing * 9f + i * 0.7f));
                waveBars[i].localScale = new Vector3(1f, Mathf.Clamp(level, 0.003f, 1f) * 0.035f + 0.002f, 1f);
            }
        }

        // the pages come together in the middle, the Zumi glow blooms from there and swallows them, holds, and the
        // whole screen fades out
        void Outro(float t)
        {
            var centre = anchor.position + anchor.rotation * new Vector3(0f, -GridDrop, GridDistance);
            var a = 1f - ZumiFlowKit.Smooth((t - OutroSeconds + FadeSeconds) / FadeSeconds);
            for (var i = 0; i < pages.Count; i++)
            {
                var v = pages[i];
                var k = ZumiFlowKit.Smooth((t - i * 0.05f) / MergeSeconds);
                // a breath toward the reader per page, so the pile never z-fights
                var target = centre + (anchor.position - centre).normalized * (0.002f * i);
                v.root.SetPositionAndRotation(Vector3.Lerp(v.cell.position, target, k), v.cell.rotation);
                v.root.localScale = Vector3.one * Mathf.Lerp(1f, 0.6f, k);
                // under the glow they go
                var under = 1f - ZumiFlowKit.Smooth((t - MergeSeconds - 0.1f) / 0.5f);
                ZumiFlowKit.SetTint(v.picture, new Color(1f, 1f, 1f, Mathf.Min(a, under)));
                v.parts.SetAlpha(0f);
                v.labelParts.SetAlpha(0f);
                v.maskRenderer.enabled = false;
            }
            headerParts.SetAlpha(a);
            // the header closes: the last step is done
            if (stageText.text != "Done")
            {
                stageText.text = "Done";
                stepText.text = "Ready to read";
            }
            barFill.localScale = Vector3.one;
            soundParts.SetAlpha(0f);
            if (depthPivot) depthPivot.gameObject.SetActive(false);
            if (world) world.gameObject.SetActive(false);
            if (t < OutroSeconds - FadeSeconds) caption.Show(string.Format(DoneLine, comicTitle), CaptionBelow);
            else caption.Hide();
            // the glow, in front of the pile, facing the reader
            if (!glow)
            {
                glowMaterial = new Material(ZumiFlowKit.GlowShader) { renderQueue = 3020 };
                glow = ZumiFlowKit.Card("Zumi glow", null, Vector2.one, glowMaterial).transform;
            }
            var bloom = ZumiFlowKit.Smooth((t - MergeSeconds + 0.4f) / 0.9f);
            var at = centre + (anchor.position - centre).normalized * 0.03f;
            glow.SetPositionAndRotation(at, Facing(at));
            glow.localScale = Vector3.one * Mathf.Lerp(0.05f, GlowSize, bloom);
            glowMaterial.SetFloat("_Turn", t * 0.6f);
            glowMaterial.SetColor("_Color", new Color(1f, 1f, 1f, 0.9f * Mathf.Min(bloom, a)));
        }

        /// <summary>Where the pages merge and the last glow blooms (the comic flies out of it to its place).</summary>
        public Vector3 EndPoint => anchor.position + anchor.rotation * new Vector3(0f, -GridDrop, GridDistance - 0.03f);

        /// <summary>The outro: the pages merge, the glow blooms and holds, then everything fades.</summary>
        public const float MergeSeconds = 1.3f, GlowSize = 0.75f, FadeSeconds = 0.8f;
        Transform glow;
        Material glowMaterial;

        // ---- the end -----------------------------------------------------------------------------------------

        /// <summary>Straight to the end.</summary>
        public void Skip()
        {
            if (!running) return;
            Skipped = true;
            Debug.Log("[Zumi] making-of: skipped to the end");
            End();
        }

        void End()
        {
            running = false;
            PlaybackStage = "done";
            caption.Hide();
            if (musicSource) musicSource.Stop();
            if (book) book.Stow();
            Clear();
            Finished?.Invoke();
        }

        void Clear()
        {
            foreach (var v in pages)
            {
                if (v.root) Destroy(v.root.gameObject);
                Destroy(v.picture);
                Destroy(v.mask);
                v.parts.Destroy();
                v.labelParts.Destroy();
            }
            pages.Clear();
            if (glow) Destroy(glow.gameObject);
            if (glowMaterial) Destroy(glowMaterial);
            if (characterRoot) Destroy(characterRoot.gameObject);
            foreach (var m in members) m.parts.Destroy();
            members.Clear();
            sightings.Clear();
            links.Clear();
            if (header) Destroy(header.gameObject);
            headerParts.Destroy();
            if (soundCard) Destroy(soundCard.gameObject);
            soundParts.Destroy();
            depthScene?.Dispose();
            depthScene = null;
            foreach (var layer in depthLayers) layer.outline?.Destroy();
            depthLayers.Clear();
            if (depthPivot) Destroy(depthPivot.gameObject);
            foreach (var p in worldProps) p.label.Destroy();
            worldProps.Clear();
            worldParts.Destroy();
            foreach (var m in worldMaterials) Destroy(m);
            worldMaterials.Clear();
            foreach (var m in worldMeshes) Destroy(m);
            worldMeshes.Clear();
            foreach (var tex in worldTextures)
                if (tex) Destroy(tex);
            worldTextures.Clear();
            if (frameMaterial) Destroy(frameMaterial);
            if (worldRimMaterial) Destroy(worldRimMaterial);
            if (world) Destroy(world.gameObject);
        }

        void OnDestroy()
        {
            cancel?.Cancel();
            Clear();
        }
    }

    static class ZumiOutlineExtensions
    {
        public static Vector2[] MovedBy(this Vector2[] outline, Vector2 by) => ZumiDraw.Moved(outline, by);
    }
}
