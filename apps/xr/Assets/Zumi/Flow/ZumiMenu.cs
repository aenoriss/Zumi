using System;
using UnityEngine;

namespace Zumi
{
    /// <summary>
    /// The app's front door. First the logo moment (the mascot over the word "Zumi", LogoSeconds), then a floating
    /// cream card MenuDistance ahead with the mascot on it and two round buttons, Explore and Load, and beside it, low
    /// and within reach, a small shelf of books (ZumiBook stands on it, ShelfSlot). Everything is placed once from where
    /// the head was when the logo came (Anchor), level.
    /// </summary>
    public class ZumiMenu : MonoBehaviour
    {
        public const float LogoSeconds = 2.2f, LogoFadeSeconds = 0.45f, LogoDistance = 1.0f, LogoCap = 0.06f, LogoMascot = 0.22f;
        public const float MenuDistance = 0.8f, MenuDrop = 0.06f, MenuSide = -0.1f;
        public const float CardWidth = 0.34f, CardHeight = 0.24f, ButtonRadius = 0.036f, ButtonPitch = 0.13f, TitleCap = 0.032f, LabelCap = 0.016f;
        /// <summary>The shelf: metres ahead of the eye, to its right and below it; its width and depth.</summary>
        public const float ShelfAhead = 0.5f, ShelfSide = 0.27f, ShelfDrop = 0.36f, ShelfWidth = 0.34f, ShelfDepth = 0.13f, SlotPitch = 0.25f;
        public const float FadeSeconds = 0.3f;

        public event Action ExplorePressed, LoadPressed;

        /// <summary>"logo", "menu", "hidden".</summary>
        public string State { get; private set; } = "hidden";
        public Pose Anchor { get; private set; }
        public bool ShelfShown => shelf && shelf.gameObject.activeSelf;

        Shader flat;
        GameObject mascotPrefab;
        Transform logo, card, shelf;
        readonly ZumiDraw.Parts logoParts = new() { blended = true, queue = 3500 };
        readonly ZumiDraw.Parts cardParts = new() { blended = true, queue = 3500 };
        readonly ZumiDraw.Parts shelfParts = new();
        ZumiDraw.RoundButton explore, load;
        float logoSince = -1f, cardAlpha;
        bool cardWanted;
        public event Action LogoDone;

        public void Init(Shader flatShader, GameObject mascot)
        {
            flat = flatShader;
            mascotPrefab = mascot;
        }

        /// <summary>The logo, then (LogoDone) the menu.</summary>
        public void StartLogo()
        {
            Anchor = ZumiFlowKit.LevelHead();
            BuildLogo();
            logoSince = Time.time;
            State = "logo";
        }

        public void ShowMenu(bool on)
        {
            if (!card) BuildCard();
            if (!shelf) BuildShelf();
            cardWanted = on;
            shelf.gameObject.SetActive(true);
            if (on) State = "menu";
        }

        public void HideAll()
        {
            cardWanted = false;
            if (shelf) shelf.gameObject.SetActive(false);
            State = "hidden";
        }

        public void ShowShelf(bool on)
        {
            if (!shelf) BuildShelf();
            shelf.gameObject.SetActive(on);
        }

        /// <summary>Where a book stands on the shelf: the middle of its foot, and its rotation (cover toward the eye).</summary>
        public Pose ShelfSlot(int i)
        {
            if (!shelf) BuildShelf();
            // the one book in the middle (a second would stand to its right)
            var p = shelf.TransformPoint(new Vector3(i * SlotPitch, 0f, 0f));
            // leaning back a little against the shelf's back
            return new Pose(p, shelf.rotation * Quaternion.Euler(8f, 0f, 0f));
        }

        void Update()
        {
            if (logo)
            {
                var t = Time.time - logoSince;
                var a = Mathf.Min(Mathf.Clamp01(t / LogoFadeSeconds), Mathf.Clamp01((LogoSeconds - t) / LogoFadeSeconds));
                logoParts.SetAlpha(a);
                logo.localScale = Vector3.one * Mathf.Lerp(0.92f, 1f, ZumiFlowKit.Smooth(t / LogoSeconds));
                if (t >= LogoSeconds)
                {
                    Destroy(logo.gameObject);
                    logoParts.Destroy();
                    logo = null;
                    LogoDone?.Invoke();
                }
            }
            if (card)
            {
                cardAlpha = Mathf.MoveTowards(cardAlpha, cardWanted ? 1f : 0f, Time.deltaTime / FadeSeconds);
                var visible = cardAlpha > 0.001f;
                if (card.gameObject.activeSelf != visible) card.gameObject.SetActive(visible);
                if (visible)
                {
                    cardParts.SetAlpha(cardAlpha);
                    foreach (var b in new[] { explore, load })
                        b.disc.SetColor("_Color", WithAlpha(b.Touched ? ZumiDraw.Hover : ZumiDraw.Button, cardAlpha));
                }
            }
        }

        static Color WithAlpha(Color c, float a) => new(c.r, c.g, c.b, a);

        Vector3 At(Vector3 local) => Anchor.position + Anchor.rotation * local;

        void BuildLogo()
        {
            logo = new GameObject("Logo").transform;
            var at = At(new Vector3(0f, 0f, LogoDistance));
            logo.SetPositionAndRotation(at, ZumiFlowKit.Facing(at, Anchor.position));
            var stand = new GameObject("Mascot stand").transform;
            stand.SetParent(logo, false);
            stand.localPosition = new Vector3(0f, -0.02f, 0f);
            ZumiFlowKit.Mascot(mascotPrefab, stand, LogoMascot, "happy");
            var width = ZumiDraw.Width("Zumi", LogoCap) + 0.08f;
            ZumiDraw.Shape(flat, logoParts, "Plate", logo, 0.02f, ZumiDraw.Plate, 0, Moved(ZumiDraw.Rounded(width, LogoCap * 2.2f, LogoCap * 1.1f), new Vector2(0f, -0.07f)));
            ZumiDraw.Text(flat, logoParts, "Word", logo, new Vector3(0f, -0.07f, 0.018f), LogoCap, ZumiDraw.Ink, 2, "Zumi");
            logoParts.SetAlpha(0f);
        }

        void BuildCard()
        {
            card = new GameObject("Menu").transform;
            var at = At(new Vector3(MenuSide, -MenuDrop, MenuDistance));
            card.SetPositionAndRotation(at, ZumiFlowKit.Facing(at, Anchor.position));
            ZumiDraw.Shape(flat, cardParts, "Plate", card, 0f, ZumiDraw.Plate, 0, ZumiDraw.Rounded(CardWidth, CardHeight, 0.03f));
            // the mascot sits on the card's top edge, to the left of the title
            var stand = new GameObject("Mascot stand").transform;
            stand.SetParent(card, false);
            stand.localPosition = new Vector3(-CardWidth / 2f + 0.055f, CardHeight / 2f - 0.012f, -0.01f);
            ZumiFlowKit.Mascot(mascotPrefab, stand, 0.09f, "happy");
            ZumiDraw.Text(flat, cardParts, "Title", card, new Vector3(0f, CardHeight / 2f - 0.045f, -0.002f), TitleCap, ZumiDraw.Ink, 2, "Zumi");
            ZumiDraw.Text(flat, cardParts, "Subtitle", card, new Vector3(0f, CardHeight / 2f - 0.084f, -0.002f), LabelCap, ZumiDraw.SoftInk, 2, "Comics you can step into");
            var row = -0.03f;
            explore = ZumiDraw.Round(flat, cardParts, "Explore", card, new Vector2(-ButtonPitch / 2f, row), ButtonRadius, 1, () => Press("explore"));
            load = ZumiDraw.Round(flat, cardParts, "Load", card, new Vector2(ButtonPitch / 2f, row), ButtonRadius, 1, () => Press("load"));
            // Explore: an open book; Load: a page with an arrow up into it
            ZumiDraw.Shape(flat, cardParts, "Icon", explore.transform, -0.002f, ZumiDraw.Ink, 2,
                new[] { new Vector2(-0.019f, -0.011f), new Vector2(-0.019f, 0.011f), new Vector2(-0.002f, 0.008f), new Vector2(-0.002f, -0.014f) },
                new[] { new Vector2(0.002f, -0.014f), new Vector2(0.002f, 0.008f), new Vector2(0.019f, 0.011f), new Vector2(0.019f, -0.011f) });
            ZumiDraw.Shape(flat, cardParts, "Icon", load.transform, -0.002f, ZumiDraw.Ink, 2,
                ZumiDraw.Box(-0.013f, -0.016f, 0.026f, 0.003f), ZumiDraw.Box(-0.013f, -0.016f, 0.003f, 0.012f), ZumiDraw.Box(0.010f, -0.016f, 0.003f, 0.012f),
                ZumiDraw.Box(-0.0018f, -0.008f, 0.0036f, 0.014f), new[] { new Vector2(-0.008f, 0.005f), new Vector2(0f, 0.016f), new Vector2(0.008f, 0.005f) });
            ZumiDraw.Text(flat, cardParts, "Explore label", card, new Vector3(-ButtonPitch / 2f, row - ButtonRadius - 0.02f, -0.002f), LabelCap, ZumiDraw.Ink, 2, "Explore");
            ZumiDraw.Text(flat, cardParts, "Load label", card, new Vector3(ButtonPitch / 2f, row - ButtonRadius - 0.02f, -0.002f), LabelCap, ZumiDraw.Ink, 2, "Load");
            card.gameObject.SetActive(false);
        }

        void BuildShelf()
        {
            shelf = new GameObject("Shelf").transform;
            var at = At(new Vector3(ShelfSide, -ShelfDrop, ShelfAhead));
            var toward = Anchor.position - at;
            toward.y = 0f;
            // the shelf's +z points away from the reader, like a card
            shelf.SetPositionAndRotation(at, Quaternion.LookRotation(-toward.normalized, Vector3.up));
            // its top, lying flat, and its front lip
            var top = ZumiDraw.Shape(flat, shelfParts, "Top", shelf, 0f, ZumiDraw.Plate, 0, ZumiDraw.Rounded(ShelfWidth, ShelfDepth, 0.012f));
            top.localRotation = Quaternion.Euler(90f, 0f, 0f);
            var lip = ZumiDraw.Shape(flat, shelfParts, "Lip", shelf, 0f, ZumiDraw.Hex(0xE2D3C3), 0, ZumiDraw.Rounded(ShelfWidth, 0.022f, 0.008f));
            lip.localPosition = new Vector3(0f, -0.011f, -ShelfDepth / 2f);
            var under = ZumiDraw.Shape(flat, shelfParts, "Under", shelf, 0f, ZumiDraw.Hex(0xE2D3C3), 0, ZumiDraw.Rounded(ShelfWidth, ShelfDepth, 0.012f));
            under.localRotation = Quaternion.Euler(-90f, 0f, 0f);
            under.localPosition = new Vector3(0f, -0.022f, 0f);
            var label = ZumiDraw.Text(flat, shelfParts, "Label", shelf, new Vector3(0f, -0.045f, -ShelfDepth / 2f), 0.014f, ZumiDraw.Ink, 2, "Your books");
            label.transform.localRotation = Quaternion.identity;
            shelf.gameObject.SetActive(false);
        }

        static Vector2[] Moved(Vector2[] outline, Vector2 by) => ZumiDraw.Moved(outline, by);

        void Press(string what)
        {
            if (cardAlpha < 0.9f || !cardWanted) return;
            Debug.Log($"[Zumi] flow menu: {what}");
            if (what == "explore") ExplorePressed?.Invoke();
            else LoadPressed?.Invoke();
        }

        void OnDestroy()
        {
            logoParts.Destroy();
            cardParts.Destroy();
            shelfParts.Destroy();
        }
    }
}
