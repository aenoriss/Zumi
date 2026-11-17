using System.Collections.Generic;
using UnityEngine;

namespace Zumi
{
    /// <summary>
    /// The demo's flow, as a state machine over the reader. The episode no longer plays at launch: it opens, held
    /// (ZumiReader.HoldForBook), and reading starts only when a book is opened.
    ///   logo       the Zumi logo moment (ZumiMenu.LogoSeconds)
    ///   home       the carousel (ZumiCarousel): Dan &amp; Buck in the middle, and Create
    ///   invite     Create turned over: creating is invite-only for now; "See how it's made", or "Back" (home again)
    ///   making-of  See how it's made: the carousel folds away, the Dan &amp; Buck book comes forward and opens, its
    ///              pencil pages fly out into the showcase (ZumiMakingOf), which fades out at its end; a pinch or the
    ///              hand menu skips it; then home again, and the book arrives back into its place out of the last glow
    ///   opening    the middle comic was brought close or ray-pinched and opens (ZumiBook)
    ///   reading    the reader has the episode, from its start; the hand menu is the reader's again
    /// While the carousel or a book own the hands, the hand menu stays shut.
    /// </summary>
    [RequireComponent(typeof(ZumiReader))]
    public class ZumiFlow : MonoBehaviour
    {
        /// <summary>Where earlier builds kept "the comic was made" across launches; deleted at start so old installs
        /// forget it.</summary>
        const string StaleCreatedKey = "zumi.demo.created";
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
        /// <summary>"logo", "home", "invite", "making-of", "opening", "reading"; null with the flow off.</summary>
        public string FlowStage { get; private set; }
        public string PlaybackStage => makingOf ? makingOf.PlaybackStage : null;
        /// <summary>The showcase has finished in this run (Dan &amp; Buck arrived out of it).</summary>
        public bool ComicCreated { get; private set; }
        public ZumiCarousel Carousel => carousel;
        public string CarouselState => carousel ? carousel.State : null;
        public string CarouselCentre => carousel ? carousel.CentreTitle : null;
        public string InviteState => carousel ? carousel.Invite : null;
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
            if (PlayerPrefs.HasKey(StaleCreatedKey))
            {
                PlayerPrefs.DeleteKey(StaleCreatedKey);
                PlayerPrefs.Save();
            }
            var flat = handMenu.FlatShader;
            caption = gameObject.AddComponent<ZumiCaption>();
            caption.Init(flat, mascot);
            caption.On = captions;
            menu = gameObject.AddComponent<ZumiMenu>();
            menu.Init(flat, mascot);
            makingOf = gameObject.AddComponent<ZumiMakingOf>();
            makingOf.Init(flat, caption, reader);
            carousel = gameObject.AddComponent<ZumiCarousel>();
            carousel.Init(flat, mascot);
            carousel.InviteOpened += () =>
            {
                if (FlowStage == "home") Enter("invite");
            };
            carousel.InviteClosed += () =>
            {
                if (FlowStage == "invite") Enter("home");
            };
            carousel.SeeHowPressed += SeeHowItsMade;
            menu.LogoDone += ShowHome;
            makingOf.Finished += OnShowcaseDone;
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
            carousel.AddCreate();
            // the bundle and the book load while the logo shows
            _ = ZumiMakingOfData.Get();
            comic = await ZumiBook.Create("Book dan-buck");
            if (!this || !comic) return;
            comic.Opened += () => OnBookOpened(comic);
            carousel.AddComic(comic, ComicTitle, ComicLine);
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

        /// <summary>See how it's made: the book leaves its place for the showcase while the carousel folds away.</summary>
        public void SeeHowItsMade()
        {
            if (FlowStage is not ("home" or "invite") || !comic) return;
            Enter("making-of");
            handMenu.Suppressed = false;
            handMenu.Intercept = _ =>
            {
                makingOf.Skip();
                return true;
            };
            makingOf.Play(comic, ComicTitle);
            carousel.Fold(null);
        }

        /// <summary>Skips the showcase to its end (as a pinch does).</summary>
        public void SkipPlayback() => makingOf.Skip();

        // the showcase faded out: home, and the comic flies out of the glow into its own place (it is on the
        // carousel from launch, so it never shows twice)
        void OnShowcaseDone()
        {
            Enter("home");
            handMenu.Suppressed = true;
            handMenu.Intercept = null;
            if (comic)
            {
                ComicCreated = true;
                carousel.Arrive(comic, ComicTitle, ComicLine, makingOf.EndPoint);
            }
            else carousel.Show();
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
            if (FlowStage is "home" or "invite" && comic && comic.State == "opening")
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
