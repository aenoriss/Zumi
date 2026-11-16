using System.Collections.Generic;
using UnityEngine;

namespace Zumi
{
    /// <summary>
    /// The demo's creation flow, as a state machine over the reader. The episode no longer plays at launch: it opens,
    /// held (ZumiReader.HoldForBook), and reading starts only when a book is opened.
    ///   logo      the Zumi logo moment (ZumiMenu.LogoSeconds)
    ///   menu      the cream card with Explore and Load, the shelf of books beside it
    ///   explore   the card goes; the books on the shelf wait for a hand
    ///   scanner   Load: the page guide on the desk, each page taken when it lies still, then Done (ZumiScanner)
    ///   pipeline  the mocked pipeline playback (ZumiMakingOf), which fades out at its end; a pinch or the hand menu
    ///             skips it; then the menu again, the shelf with its one book
    ///   opening   a book was brought close and opens (ZumiBook)
    ///   reading   the reader has the episode, from its start; the hand menu is the reader's again
    /// While the menu, the scanner or a book own the hands, the hand menu stays shut.
    /// </summary>
    [RequireComponent(typeof(ZumiReader))]
    public class ZumiFlow : MonoBehaviour
    {
        public const float ProcessDelaySeconds = 1.2f;

        [Tooltip("Off: the reader plays the episode at launch, as before")]
        [SerializeField] bool flowEnabled = true;
        [Tooltip("The mascot (Assets/Zumi/Mascot/Zumi.prefab)")]
        [SerializeField] GameObject mascot;
        [Tooltip("The one switch for every mascot caption (an edit may add its own)")]
        [SerializeField] bool captions = true;
        [Tooltip("\"Create. Explore. Share.\" while reading")]
        [SerializeField] bool readingCaption;

        // ---- read-only state for tests and tools -------------------------------------------------------------
        /// <summary>"logo", "menu", "explore", "scanner", "pipeline", "opening", "reading"; null with the flow off.</summary>
        public string FlowStage { get; private set; }
        public int PagesCaptured => scanner ? scanner.PagesCaptured : 0;
        public string ScannerState => scanner ? scanner.State : null;
        public string PlaybackStage => makingOf ? makingOf.PlaybackStage : null;
        public int BooksOnShelf
        {
            get
            {
                var n = 0;
                foreach (var b in books) if (b && b.State is "shelf" or "held") n++;
                return n;
            }
        }
        public string BookState => books.Count > 0 && books[^1] ? books[^1].State : null;
        public string CaptionLine => caption ? caption.Line : null;
        public bool CaptionsOn
        {
            get => captions;
            set
            {
                captions = value;
                if (caption) caption.On = value;
            }
        }

        ZumiReader reader;
        ZumiHandMenu handMenu;
        ZumiMenu menu;
        ZumiScanner scanner;
        ZumiMakingOf makingOf;
        ZumiCaption caption;
        readonly List<ZumiBook> books = new();

        void Awake()
        {
            if (!flowEnabled) return;
            reader = GetComponent<ZumiReader>();
            reader.HoldForBook();
            handMenu = GetComponent<ZumiHandMenu>();
            handMenu.Suppressed = true;
            var flat = handMenu.FlatShader;
            caption = gameObject.AddComponent<ZumiCaption>();
            caption.Init(flat, mascot);
            caption.On = captions;
            menu = gameObject.AddComponent<ZumiMenu>();
            menu.Init(flat, mascot);
            scanner = gameObject.AddComponent<ZumiScanner>();
            scanner.Init(flat, caption);
            makingOf = gameObject.AddComponent<ZumiMakingOf>();
            makingOf.Init(flat, caption, reader);
            menu.LogoDone += OnLogoDone;
            menu.ExplorePressed += Explore;
            menu.LoadPressed += Load;
            scanner.Finished += () => Invoke(nameof(Process), ProcessDelaySeconds);
            makingOf.Finished += OnPipelineDone;
        }

        async void Start()
        {
            if (!flowEnabled) return;
            // everything is placed from the head: wait for its first tracked pose (the origin before it; the rig
            // tracks from the floor, so a head still at floor height is not tracked yet)
            var since = Time.realtimeSinceStartup;
            while (Time.realtimeSinceStartup - since < 3f && (!Camera.main || Camera.main.transform.position.y < 0.3f))
            {
                await System.Threading.Tasks.Task.Yield();
                if (!this) return;
            }
            Enter("logo");
            menu.StartLogo();
            // the bundle and the books load while the logo shows
            _ = ZumiMakingOfData.Get();
            var first = await ZumiBook.Create("Book dan-buck");
            if (!this) return;
            if (first) AddBook(first, 0);
        }

        void AddBook(ZumiBook book, int slot)
        {
            books.Add(book);
            book.Opened += () => OnBookOpened(book);
            if (FlowStage is "menu" or "explore") book.Stand(menu.ShelfSlot(slot));
            else if (FlowStage != "logo") book.gameObject.SetActive(false);
        }

        void Enter(string stage)
        {
            FlowStage = stage;
            Debug.Log($"[Zumi] flow: {stage}");
        }

        void OnLogoDone() => ShowMenu();

        void ShowMenu()
        {
            Enter("menu");
            handMenu.Suppressed = true;
            handMenu.Intercept = null;
            menu.ShowMenu(true);
            for (var i = 0; i < books.Count; i++)
                if (books[i] && books[i].State is "loading" or "shelf") books[i].Stand(menu.ShelfSlot(i));
        }

        /// <summary>Explore: the card goes, the shelf stays: a book is taken from it.</summary>
        public void Explore()
        {
            if (FlowStage != "menu") return;
            Enter("explore");
            menu.ShowMenu(false);
        }

        /// <summary>Load: the scanner.</summary>
        public void Load()
        {
            if (FlowStage != "menu") return;
            Enter("scanner");
            menu.ShowMenu(false);
            foreach (var b in books) if (b) b.SetGrabbable(false);
            scanner.Begin();
        }

        /// <summary>Takes every page left (tools, tests, and a rehearsal of the video).</summary>
        public void FillScan() => scanner.FillRemaining();

        void Process()
        {
            if (FlowStage != "scanner") return;
            Enter("pipeline");
            var captures = new List<ZumiScanner.Capture>(scanner.Captures);
            scanner.Close();
            handMenu.Suppressed = false;
            handMenu.Intercept = _ =>
            {
                makingOf.Skip();
                return true;
            };
            makingOf.Play(captures);
        }

        /// <summary>Skips the pipeline playback to its end (as a pinch does).</summary>
        public void SkipPlayback() => makingOf.Skip();

        // the playback faded out: back at the menu, the shelf with its one book
        void OnPipelineDone() => ShowMenu();

        static void SetRising(ZumiBook book, ZumiMakingOfData data)
        {
            var page = data.pages[0];
            if (!page.colourTexture || page.frames.Count == 0) return;
            var f = page.frames[0];
            var px = page.Pixels;
            book.SetRisingPicture(page.colourTexture, new Rect(f[0] / px.x, 1f - f[3] / px.y, (f[2] - f[0]) / px.x, (f[3] - f[1]) / px.y));
        }

        void Update()
        {
            if (!flowEnabled) return;
            // a book taken from the shelf: the others wait, and the first one brought close opens
            if (FlowStage is "menu" or "explore")
                foreach (var b in books)
                    if (b && b.State == "opening")
                    {
                        Enter("opening");
                        menu.ShowMenu(false);
                        foreach (var other in books) if (other && other != b) other.gameObject.SetActive(false);
                        break;
                    }
        }

        void OnBookOpened(ZumiBook book)
        {
            Enter("reading");
            menu.HideAll();
            reader.Begin();
            handMenu.Suppressed = false;
            handMenu.Intercept = null;
            if (readingCaption) caption.Show("Create. Explore. Share.");
        }

        void LateUpdate()
        {
            // the first book's rising picture, once the bundle is read
            if (!flowEnabled) return;
            foreach (var b in books)
                if (b && !risingSet.Contains(b))
                {
                    var data = ZumiMakingOfData.Get();
                    if (!data.IsCompleted || data.Result == null) return;
                    SetRising(b, data.Result);
                    var colour = new List<Texture>();
                    foreach (var p in data.Result.pages) colour.Add(p.colourTexture);
                    b.SetPagePictures(colour);
                    risingSet.Add(b);
                }
        }

        readonly HashSet<ZumiBook> risingSet = new();
    }
}
