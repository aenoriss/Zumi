using System.Collections.Generic;
using UnityEngine;

namespace Zumi
{
    /// <summary>
    /// The demo's creation flow, as a state machine over the reader. The episode no longer plays at launch: it opens,
    /// held (ZumiReader.HoldForBook), and reading starts only when a book is opened.
    ///   logo      the Zumi logo moment (ZumiMenu.LogoSeconds)
    ///   home      the carousel (ZumiCarousel): the comics made so far and "New comic"
    ///   scanner   New comic: the carousel folds away, the reader touches the table, the page guide lies there, each
    ///             page is taken when it lies still, then Done (ZumiScanner)
    ///   pipeline  the mocked pipeline playback (ZumiMakingOf), which fades out at its end; a pinch or the hand menu
    ///             skips it; then home again, and the new comic (Dan &amp; Buck) arrives out of the last glow
    ///   opening   the middle comic was brought close or ray-pinched and opens (ZumiBook)
    ///   reading   the reader has the episode, from its start; the hand menu is the reader's again
    /// Whether Dan &amp; Buck was made is kept across launches (CreatedKey); the hand menu's "Reset demo" forgets it.
    /// While the carousel, the scanner or a book own the hands, the hand menu stays shut.
    /// </summary>
    [RequireComponent(typeof(ZumiReader))]
    public class ZumiFlow : MonoBehaviour
    {
        public const float ProcessDelaySeconds = 1.2f;
        public const string CreatedKey = "zumi.demo.created";
        public const string ComicTitle = "Dan & Buck", ComicLine = "Episode 1 · 28 panels · voiced";

        [Tooltip("Off: the reader plays the episode at launch, as before")]
        [SerializeField] bool flowEnabled = true;
        [Tooltip("The mascot (Assets/Zumi/Mascot/Zumi.prefab)")]
        [SerializeField] GameObject mascot;
        [Tooltip("The one switch for every mascot caption (an edit may add its own)")]
        [SerializeField] bool captions = true;
        [Tooltip("\"Create. Explore. Share.\" while reading")]
        [SerializeField] bool readingCaption;

        // ---- read-only state for tests and tools -------------------------------------------------------------
        /// <summary>"logo", "home", "scanner", "pipeline", "opening", "reading"; null with the flow off.</summary>
        public string FlowStage { get; private set; }
        public int PagesCaptured => scanner ? scanner.PagesCaptured : 0;
        public string ScannerState => scanner ? scanner.State : null;
        public string PlaybackStage => makingOf ? makingOf.PlaybackStage : null;
        /// <summary>Dan &amp; Buck has been made (kept across launches).</summary>
        public bool ComicCreated => PlayerPrefs.GetInt(CreatedKey, 0) == 1;
        public ZumiCarousel Carousel => carousel;
        public ZumiScanner Scanner => scanner;
        public string CarouselState => carousel ? carousel.State : null;
        public string CarouselCentre => carousel ? carousel.CentreTitle : null;
        public string GuideSource => scanner ? scanner.GuideSource : null;
        public string BookState => comic ? comic.State : null;
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
        ZumiCarousel carousel;
        ZumiBook comic;

        void Awake()
        {
            if (!flowEnabled) return;
            reader = GetComponent<ZumiReader>();
            reader.HoldForBook();
            handMenu = GetComponent<ZumiHandMenu>();
            handMenu.Suppressed = true;
            handMenu.ResetDemo = ResetDemo;
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
            carousel = gameObject.AddComponent<ZumiCarousel>();
            carousel.Init(flat, mascot);
            carousel.CreatePressed += Create;
            menu.LogoDone += ShowHome;
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
            carousel.AddNewComic();
            // the bundle and the book load while the logo shows
            _ = ZumiMakingOfData.Get();
            comic = await ZumiBook.Create("Book dan-buck");
            if (!this || !comic) return;
            comic.Opened += () => OnBookOpened(comic);
            if (ComicCreated) carousel.AddComic(comic, ComicTitle, ComicLine);
        }

        void Enter(string stage)
        {
            FlowStage = stage;
            Debug.Log($"[Zumi] flow: {stage}");
        }

        void ShowHome()
        {
            Enter("home");
            handMenu.Suppressed = true;
            handMenu.Intercept = null;
            carousel.Show();
        }

        /// <summary>New comic: the carousel folds away, then the scanner asks for a touch on the table.</summary>
        public void Create()
        {
            if (FlowStage != "home") return;
            Enter("scanner");
            carousel.Fold(scanner.Begin);
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

        // the playback faded out: home, and the comic just made flies in out of the glow, the first time
        void OnPipelineDone()
        {
            Enter("home");
            handMenu.Suppressed = true;
            handMenu.Intercept = null;
            if (comic && !carousel.Has(comic))
            {
                PlayerPrefs.SetInt(CreatedKey, 1);
                PlayerPrefs.Save();
                carousel.Arrive(comic, ComicTitle, ComicLine, makingOf.EndPoint);
            }
            else carousel.Show();
        }

        /// <summary>Forgets that the comic was made (the hand menu's "Reset demo"): the next home has only New comic.</summary>
        public void ResetDemo()
        {
            PlayerPrefs.DeleteKey(CreatedKey);
            PlayerPrefs.Save();
            if (comic) carousel.RemoveComic(comic);
            Debug.Log("[Zumi] flow: demo reset, no comic made yet");
        }

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
            // the comic opening (brought close, or a ray pinch on the carousel's middle): the carousel goes
            if (FlowStage == "home" && comic && comic.State == "opening")
            {
                Enter("opening");
                carousel.Hide();
            }
        }

        void OnBookOpened(ZumiBook book)
        {
            Enter("reading");
            reader.Begin();
            handMenu.Suppressed = false;
            handMenu.Intercept = null;
            if (readingCaption) caption.Show("Create. Explore. Share.");
        }

        void LateUpdate()
        {
            // the comic's rising picture and printed pages, once the bundle is read
            if (!flowEnabled || !comic || risingSet) return;
            var data = ZumiMakingOfData.Get();
            if (!data.IsCompleted || data.Result == null) return;
            SetRising(comic, data.Result);
            var colour = new List<Texture>();
            foreach (var p in data.Result.pages) colour.Add(p.colourTexture);
            comic.SetPagePictures(colour);
            risingSet = true;
        }

        bool risingSet;
    }
}
