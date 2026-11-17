using System;
using System.Collections.Generic;
using Oculus.Interaction;
using Oculus.Interaction.Surfaces;
using UnityEngine;

namespace Zumi
{
    /// <summary>
    /// The home screen: the reader's comics (newest first) and, last, a "Create" card, floating in an arc at chest
    /// height, five places in view; places the shelf has no item for show an empty grey frame (room for more). The
    /// middle item is larger, nearer and alive: a soft ring of the Zumi hues blooms behind it with a thin turning rim,
    /// it lifts a little toward the reader, and on a comic the mascot hops onto its top right corner. Under it a cream
    /// pill names a comic (Create names itself on its card and has none), a chip says what a hand does ("Grab to
    /// read"), and dots say where it is in the row.
    ///
    /// Every item is reached by a hand ray and a pinch from afar, or by a poke: on a side item it brings that item to
    /// the middle; on the middle comic a ray pinch opens it (a hand grab and bringing it close does too, ZumiBook); on
    /// "Create" either (or grabbing it) turns the card over into the invite panel: creating is invite-only for now,
    /// with "See how it's made" (SeeHowPressed) and "Back" (turns it back). Swiping the arc closes the panel too. A
    /// ray pinched and drawn sideways (beyond DragDegrees) turns the arc instead, as an open hand swept through it
    /// does; let go, it runs on, slows and settles on the nearest item. A ray hovering an item enlarges it a little
    /// and brightens the middle's ring.
    ///
    /// A comic arrives (Arrive): out of the showcase's last glow it flies to its place in the middle in pencil, then
    /// its colour sweeps across it left to right behind a thin line of the Zumi hues, once; then it comes alive.
    /// The look is <see cref="Style"/>; the mechanics do not depend on its values.
    /// </summary>
    public class ZumiCarousel : MonoBehaviour
    {
        /// <summary>Every visual parameter, in one place.</summary>
        [Serializable]
        public sealed class Look
        {
            /// <summary>Metres from the eye (level) to the arc's middle, and below the eye (chest height).</summary>
            public float distance = 0.8f, drop = 0.15f;
            /// <summary>The middle item's size (a book is scaled to its height).</summary>
            public Vector2 cardSize = new(0.21f, 0.29f);
            public float cardCorner = 0.012f;
            /// <summary>By places from the middle (0, 1, 2, 3): metres sideways, metres farther (the middle nearer),
            /// scale, degrees turned toward the middle, opacity. Between places they blend.</summary>
            public float[] side = { 0f, 0.2f, 0.36f, 0.48f };
            public float[] back = { -0.04f, 0f, 0.035f, 0.07f };
            public float[] scale = { 1f, 0.72f, 0.6f, 0.5f };
            public float[] turn = { 0f, 22f, 36f, 45f };
            public float[] opacity = { 1f, 0.85f, 0.72f, 0f };
            /// <summary>A comic away from the middle is dimmed to this brightness (still in colour).</summary>
            public float offBrightness = 0.85f;
            /// <summary>The idle float: metres up and down, cycles a second, each item out of step.</summary>
            public float floatMetres = 0.006f, floatHz = 0.2f;
            /// <summary>A ray on an item: its scale grows by this; the middle's ring and rim at full strength.</summary>
            public float hoverScale = 1.05f;
            /// <summary>Alive (the middle): metres toward the reader, seconds to come alive / to go back.</summary>
            public float aliveLift = 0.02f, aliveSeconds = 0.45f, leaveSeconds = 0.3f;
            /// <summary>The ring: its size as a multiple of the card's height, its strength, its turn (radians/s).</summary>
            public float glowSize = 1.7f, glowAlpha = 0.7f, glowHoverAlpha = 0.95f, glowTurn = 0.3f;
            /// <summary>The rim: metres outside the card, its width, its corner, its strength.</summary>
            public float rimGap = 0.007f, rimWidth = 0.0022f, rimCorner = 0.02f, rimAlpha = 0.85f;
            /// <summary>The soft shadow behind each item: strength, metres down, its size against the card.</summary>
            public float shadowAlpha = 0.16f, shadowDrop = 0.014f, shadowGrow = 1.25f;
            /// <summary>The mascot on the middle comic: its height, its hop's seconds and height.</summary>
            public float mascotHeight = 0.075f, hopSeconds = 0.45f, hopHeight = 0.05f;
            /// <summary>The arrival: seconds flying in (pencil), seconds of the colour sweep.</summary>
            public float arriveSeconds = 1.3f, sweepSeconds = 0.6f;
            /// <summary>The fan in: seconds per item and the delay per place from the middle; the fold away.</summary>
            public float fanSeconds = 0.7f, fanStagger = 0.07f, foldSeconds = 0.5f;
            /// <summary>Under the middle: the pill, the chip, the dots (metres).</summary>
            public float infoBelow = 0.04f, pillWidth = 0.21f, pillHeight = 0.058f, titleCap = 0.017f, lineCap = 0.0085f;
            public float chipGap = 0.01f, chipHeight = 0.026f, chipCap = 0.0085f, dotsGap = 0.014f, dot = 0.0045f, dotPitch = 0.014f, dotPill = 0.018f;
            /// <summary>Colours (the Zumi brand).</summary>
            public Color cream = ZumiDraw.Hex(0xF7F4EF), plate = ZumiDraw.Hex(0xF4ECE4), paper = ZumiDraw.Hex(0xF5EDDC), ink = ZumiDraw.Hex(0x2A211B), softInk = ZumiDraw.Hex(0x6B5E52);
            /// <summary>An empty place: a translucent cream-grey card and its frame.</summary>
            public Color emptyFill = new(0.85f, 0.83f, 0.8f, 0.28f), emptyFrame = new(0.6f, 0.57f, 0.53f, 0.45f);
            /// <summary>"Create": its fill's opacity, the dashed border (dash, gap, width), the "Invite only" chip's
            /// lettering and height.</summary>
            public float newFillAlpha = 0.8f, dash = 0.012f, dashGap = 0.008f, dashWidth = 0.0018f, inviteChipCap = 0.0085f, inviteChipHeight = 0.024f;
            /// <summary>The invite panel: seconds of the turn over, its size, corner, lettering, buttons (height, the
            /// primary's width, the secondary's, the gap), the mascot beside it.</summary>
            public float flipSeconds = 0.35f;
            public Vector2 panelSize = new(0.3f, 0.2f);
            public float panelCorner = 0.022f, panelTitleCap = 0.0125f, panelBodyCap = 0.0096f, buttonHeight = 0.036f, primaryWidth = 0.15f, secondaryWidth = 0.075f, buttonGap = 0.014f, buttonCap = 0.0095f;
            public float panelMascotHeight = 0.1f, buttonHoverScale = 1.05f, buttonPressScale = 0.95f;
            public Color buttonFill = ZumiDraw.Hex(0xFFFFFF), secondaryFill = ZumiDraw.Hex(0xF4ECE4), secondaryHover = ZumiDraw.Hex(0xEADDCF);
        }

        public static readonly Look Style = new();

        // ---- the mechanics ---------------------------------------------------------------------------------------
        /// <summary>Speed (items a second) lost per second when let go; below SettleSpeed it settles.</summary>
        public const float Friction = 3.5f, SettleSpeed = 1.2f, SettleSeconds = 0.18f;
        /// <summary>A ray pinch that turned more than this many degrees sideways is a drag, not a press.</summary>
        public const float DragDegrees = 4f, DragMetres = 0.03f;
        /// <summary>An open hand turns the arc while within the arc's band and moving sideways faster than this.</summary>
        public const float SwipeMinSpeed = 0.4f, SwipeBand = 0.2f;
        /// <summary>Metres a hand must sweep across before the arc follows it.</summary>
        public const float SwipeStart = 0.05f;
        /// <summary>The middle item can be taken only while the arc is this close to resting on it.</summary>
        public const float SettledWithin = 0.15f;
        public const int Visible = 5;

        /// <summary>The invite panel's "See how it's made"; its opening and closing.</summary>
        public event Action SeeHowPressed, InviteOpened, InviteClosed;

        // ---- read-only state for tests and tools -------------------------------------------------------------
        /// <summary>"hidden", "fanning", "shown", "folding".</summary>
        public string State { get; private set; } = "hidden";
        /// <summary>The invite panel: "opening", "open", "closing"; null while the Create card shows.</summary>
        public string Invite { get; private set; }
        /// <summary>A button of the invite panel ("see", "back"): its world position, and whether a hand is on it.</summary>
        public Vector3 InviteButtonPosition(string which) => (which == "see" ? seeButton : backButton)?.root.position ?? default;
        public bool InviteButtonHovered(string which) => (which == "see" ? seeButton : backButton)?.Touched ?? false;
        public float Scroll { get; private set; }
        public int Count => items.Count;
        public int CentreIndex => items.Count == 0 ? -1 : Mathf.Clamp(Mathf.RoundToInt(Scroll), 0, items.Count - 1);
        /// <summary>"comic", "create"; null when empty.</summary>
        public string CentreKind => CentreIndex >= 0 ? items[CentreIndex].kind : null;
        public string CentreTitle => CentreIndex >= 0 ? items[CentreIndex].title : null;
        /// <summary>How alive the middle item is, 0..1.</summary>
        public float CentreAlive => CentreIndex >= 0 ? items[CentreIndex].alive : 0f;
        public bool MascotShown => mascot && mascot.gameObject.activeInHierarchy;
        /// <summary>The arrival: "flying", "sweeping", null.</summary>
        public string Arrival => arrival?.phase;
        /// <summary>"ray", "hand" while the arc is being turned.</summary>
        public string Dragging { get; private set; }
        /// <summary>The last press: "ray centre comic" (opened), "ray side 1", "poke centre create", "ray invite see" ...;
        /// and how many.</summary>
        public string LastPress { get; private set; }
        public int Presses { get; private set; }
        public int Swipes { get; private set; }
        /// <summary>Empty frames showing now.</summary>
        public int EmptyShown { get; private set; }
        /// <summary>The middle item's world position (for tools).</summary>
        public Vector3 CentrePosition => CentreIndex >= 0 ? items[CentreIndex].position : default;
        /// <summary>Item i's world position (for tools: a ray aimed at it).</summary>
        public Vector3 ItemPosition(int i) => i >= 0 && i < items.Count ? items[i].position : default;
        public string ItemKind(int i) => i >= 0 && i < items.Count ? items[i].kind : null;
        public bool HoveredCentre => CentreIndex >= 0 && Hovered(items[CentreIndex]);

        sealed class Item
        {
            public string kind, title, line, hint;
            public ZumiBook book;
            public Transform card;
            public ZumiDraw.Parts parts;
            public Grabbable grab;
            public Transform hit;
            public BoxCollider box;
            public RayInteractable ray;
            public PokeInteractable poke;
            public Transform shadow;
            public Material shadowMaterial;
            public Vector3 position, front;
            public float scale, opacity, alive, fan;
            public bool placed;
            public float bob;
        }

        sealed class Incoming
        {
            public Item item;
            public string phase;
            public Vector3 from;
            public float since;
        }

        readonly List<Item> items = new();
        readonly List<(Transform t, ZumiDraw.Parts parts, Material frame)> empties = new();
        Shader flat;
        GameObject mascotPrefab;
        Pose anchor;
        Vector3 fanFrom;
        float shownSince, foldSince, velocity, settleVelocity;
        int? goTo;
        Action folded;
        Incoming arrival;
        bool grabbedOnce;
        // the middle's dressing
        Transform glow, rim, mascot, perch, info, chip, dots;
        Material glowMaterial, rimMaterial, dotPillMaterial;
        TextMesh title, line, chipText;
        readonly ZumiDraw.Parts infoParts = new() { blended = true, queue = 3400 };
        readonly ZumiDraw.Parts chipParts = new() { blended = true, queue = 3400 };
        readonly ZumiDraw.Parts dotParts = new() { blended = true, queue = 3400 };
        int dotsFor = -1, centreBefore = -1;
        float mascotSince = -10f;
        // the ray turning the arc
        Item rayItem;
        RayInteractor rayBy;
        float rayStartYaw;
        bool rayDragged;
        // a hand turning it
        readonly ZumiPinch hands = new();
        readonly Dictionary<int, Vector3> lastTips = new();
        readonly Dictionary<int, float> sweeps = new();
        float handTurnUntil;

        public void Init(Shader flatShader, GameObject mascot)
        {
            flat = flatShader;
            mascotPrefab = mascot;
        }

        // ---- the items ---------------------------------------------------------------------------------------

        /// <summary>A comic, first in the row (newest first).</summary>
        public void AddComic(ZumiBook book, string title, string line)
        {
            if (Has(book)) return;
            var item = new Item { kind = "comic", book = book, title = title, line = line, hint = "Grab to read" };
            MakeHit(item);
            MakeShadow(item);
            items.Insert(0, item);
            book.gameObject.SetActive(false);
            if (State != "hidden") book.Shelve();
        }

        public bool Has(ZumiBook book)
        {
            foreach (var i in items)
                if (i.book == book) return true;
            return false;
        }

        /// <summary>"Create", last in the row.</summary>
        public void AddCreate()
        {
            var item = new Item { kind = "create", title = "Create", line = "", hint = "Grab to open", parts = new ZumiDraw.Parts { blended = true, queue = 3000 } };
            item.card = BuildCreateCard(item.parts, out item.grab);
            MakeHit(item);
            MakeShadow(item);
            items.Add(item);
        }

        // ---- showing ---------------------------------------------------------------------------------------------

        /// <summary>The arc fans in round where the head is now, out of from (or from just below the middle), its
        /// first item (the newest comic, or Create) in the middle.</summary>
        public void Show(Vector3? from = null)
        {
            anchor = ZumiFlowKit.LevelHead();
            fanFrom = from ?? anchor.position + anchor.rotation * new Vector3(0f, -Style.drop - 0.1f, Style.distance - 0.1f);
            shownSince = Time.time;
            State = "fanning";
            velocity = settleVelocity = 0f;
            goTo = null;
            Scroll = 0f;
            foreach (var i in items)
            {
                i.placed = false;
                i.alive = 0f;
                if (i.book) i.book.Shelve();
                else i.card.gameObject.SetActive(true);
                i.shadow.gameObject.SetActive(true);
            }
            EnsureDressing();
            Debug.Log($"[Zumi] carousel: shown, {items.Count} items, {CentreTitle} in the middle");
        }

        /// <summary>A comic shown being made: the arc fans in and the comic flies from `from` to its place in the
        /// middle in pencil, then its colour sweeps in.</summary>
        public void Arrive(ZumiBook book, string title, string line, Vector3 from)
        {
            AddComic(book, title, line);
            Show(from);
            arrival = new Incoming { item = items[0], phase = "flying", from = from, since = Time.time };
            book.SetGraphite(1f, new Vector4(1f, 0f, 0f, -1000f));
            Debug.Log($"[Zumi] carousel: {title} arrives");
        }

        /// <summary>The arc folds into its middle and fades; then done.</summary>
        public void Fold(Action done)
        {
            if (State == "hidden")
            {
                done?.Invoke();
                return;
            }
            State = "folding";
            foldSince = Time.time;
            folded = done;
            Dragging = null;
            rayItem = null;
        }

        /// <summary>Everything goes at once, except a book that is opening (it carries on by itself).</summary>
        public void Hide()
        {
            State = "hidden";
            Dragging = null;
            rayItem = null;
            arrival = null;
            foreach (var i in items)
            {
                i.hit.gameObject.SetActive(false);
                i.shadow.gameObject.SetActive(false);
                if (i.book && i.book.State is "shelf" or "held") i.book.gameObject.SetActive(false);
                if (i.card) i.card.gameObject.SetActive(false);
            }
            foreach (var e in empties) e.t.gameObject.SetActive(false);
            SetDressing(false);
            Invite = null;
            flip = 0f;
            if (invite) invite.gameObject.SetActive(false);
        }

        // ---- building --------------------------------------------------------------------------------------------

        // the target a ray hits (a box the card's size, so the ray takes the item and not the air between) and a
        // poke presses (a disc on its face). It follows the item; built inactive and wired, as the SDK's parts read
        // their fields when they wake
        void MakeHit(Item item)
        {
            var go = new GameObject($"{item.title} target");
            go.SetActive(false);
            item.box = go.AddComponent<BoxCollider>();
            item.box.isTrigger = true;
            var surface = go.AddComponent<ColliderSurface>();
            surface.InjectAllColliderSurface(item.box);
            item.ray = go.AddComponent<RayInteractable>();
            item.ray.InjectAllRayInteractable(surface);
            var plane = go.AddComponent<PlaneSurface>();
            var circle = go.AddComponent<CircleSurface>();
            circle.InjectAllCircleSurface(plane);
            circle.InjectOptionalRadius(0.08f);
            item.poke = go.AddComponent<PokeInteractable>();
            item.poke.InjectAllPokeInteractable(circle);
            item.ray.WhenStateChanged += change =>
            {
                if (change.NewState == InteractableState.Select) RayDown(item);
                else if (change.PreviousState == InteractableState.Select) RayUp(item);
            };
            item.poke.WhenStateChanged += change =>
            {
                if (change.NewState == InteractableState.Select) Press(item, "poke");
            };
            item.hit = go.transform;
        }

        void MakeShadow(Item item)
        {
            item.shadowMaterial = ZumiFlowKit.Picture(ZumiFlowKit.SoftDisc, new Color(Style.ink.r, Style.ink.g, Style.ink.b, 0f), 2430);
            item.shadow = ZumiFlowKit.Card($"{item.title} shadow", null, Vector2.one, item.shadowMaterial).transform;
            item.shadow.gameObject.SetActive(false);
        }

        // "Create": translucent cream, a dashed ink border, an "Invite only" chip and its name; drawn facing -z
        Transform BuildCreateCard(ZumiDraw.Parts parts, out Grabbable grab)
        {
            var s = Style;
            var root = new GameObject("Create").transform;
            root.gameObject.SetActive(false);
            float w = s.cardSize.x, h = s.cardSize.y;
            ZumiDraw.Shape(flat, parts, "Fill", root, 0f, new Color(s.cream.r, s.cream.g, s.cream.b, s.newFillAlpha), 0, ZumiDraw.Rounded(w, h, s.cardCorner));
            var dashes = new List<Vector2[]>();
            var inset = s.dashWidth;
            for (var x = -w / 2f + s.cardCorner; x < w / 2f - s.cardCorner - s.dash * 0.5f; x += s.dash + s.dashGap)
            {
                var len = Mathf.Min(s.dash, w / 2f - s.cardCorner - x);
                dashes.Add(ZumiDraw.Box(x, h / 2f - inset - s.dashWidth, len, s.dashWidth));
                dashes.Add(ZumiDraw.Box(x, -h / 2f + inset, len, s.dashWidth));
            }
            for (var y = -h / 2f + s.cardCorner; y < h / 2f - s.cardCorner - s.dash * 0.5f; y += s.dash + s.dashGap)
            {
                var len = Mathf.Min(s.dash, h / 2f - s.cardCorner - y);
                dashes.Add(ZumiDraw.Box(-w / 2f + inset, y, s.dashWidth, len));
                dashes.Add(ZumiDraw.Box(w / 2f - inset - s.dashWidth, y, s.dashWidth, len));
            }
            ZumiDraw.Shape(flat, parts, "Dashes", root, -0.0005f, s.ink, 1, dashes.ToArray());
            // the chip: cream on a hairline of soft ink, so it reads on the translucent cream card
            const string invite = "Invite only";
            var chipWidth = ZumiDraw.Width(invite, s.inviteChipCap) + 0.022f;
            var chipRoot = new GameObject("Invite only").transform;
            chipRoot.SetParent(root, false);
            chipRoot.localPosition = new Vector3(0f, 0.022f, -0.0008f);
            const float line = 0.0012f;
            ZumiDraw.Shape(flat, parts, "Chip edge", chipRoot, 0f, new Color(s.softInk.r, s.softInk.g, s.softInk.b, 0.55f), 2,
                ZumiDraw.Rounded(chipWidth + 2f * line, s.inviteChipHeight + 2f * line, s.inviteChipHeight / 2f + line));
            ZumiDraw.Shape(flat, parts, "Chip", chipRoot, -0.0003f, s.cream, 3, ZumiDraw.Rounded(chipWidth, s.inviteChipHeight, s.inviteChipHeight / 2f));
            ZumiDraw.Text(flat, parts, "Chip text", chipRoot, new Vector3(0f, 0f, -0.0006f), s.inviteChipCap, s.ink, 4, invite);
            var label = ZumiDraw.Text(flat, parts, "Name", root, new Vector3(0f, -0.03f, -0.001f), 0.022f, s.ink, 4, "Create");
            label.fontStyle = FontStyle.Bold;
            grab = ZumiGrabbableProp.MakeGrabbable(root.gameObject, new Bounds(Vector3.zero, new Vector3(w, h, 0.01f)));
            grab.WhenPointerEventRaised += e =>
            {
                if (e.Type == PointerEventType.Select) CreateGrabbed();
            };
            return root;
        }

        // ---- the invite panel ------------------------------------------------------------------------------------

        sealed class PanelButton
        {
            public Transform root;
            public readonly ZumiDraw.Parts parts = new() { blended = true, queue = 3120 };
            public Material fill, ring;
            public IInteractableView[] views;
            public RayInteractable ray;
            public PokeInteractable poke;
            public float scale = 1f;

            public bool Touched
            {
                get
                {
                    foreach (var v in views)
                        if (v.State is InteractableState.Hover or InteractableState.Select) return true;
                    return false;
                }
            }

            public bool Selected
            {
                get
                {
                    foreach (var v in views)
                        if (v.State == InteractableState.Select) return true;
                    return false;
                }
            }
        }

        Transform invite, inviteMascot;
        readonly ZumiDraw.Parts inviteParts = new() { blended = true, queue = 3100 };
        PanelButton seeButton, backButton;
        float flip, inviteSince;

        // a cream panel facing -z: the title, two lines, "See how it's made" (the gradient ring) and "Back", and the
        // mascot standing at its lower right
        void BuildInvite()
        {
            var s = Style;
            invite = new GameObject("Invite panel").transform;
            float w = s.panelSize.x, h = s.panelSize.y;
            ZumiDraw.Shape(flat, inviteParts, "Plate", invite, 0f, s.cream, 0, ZumiDraw.Rounded(w, h, s.panelCorner));
            const float pad = 0.022f;
            var title = ZumiDraw.Text(flat, inviteParts, "Title", invite, new Vector3(0f, h / 2f - pad - 0.008f, -0.001f), s.panelTitleCap, s.ink, 2, "Creating is invite-only for now");
            title.fontStyle = FontStyle.Bold;
            var body = ZumiDraw.Text(flat, inviteParts, "Body", invite, new Vector3(0f, 0.004f, -0.001f), s.panelBodyCap, s.softInk, 2,
                "We're opening creation to a few artists first.\nWant to see how a comic is made?");
            body.lineSpacing = 1.15f;
            var y = -h / 2f + pad + s.buttonHeight / 2f;
            var total = s.primaryWidth + s.buttonGap + s.secondaryWidth;
            backButton = MakeButton("Back", "back", new Vector2(-total / 2f + s.secondaryWidth / 2f, y), s.secondaryWidth, false);
            seeButton = MakeButton("See how it's made", "see", new Vector2(total / 2f - s.primaryWidth / 2f, y), s.primaryWidth, true);
            var perch = new GameObject("Invite mascot").transform;
            perch.SetParent(invite, false);
            // on the right, clear of the comic in the place to the left
            perch.localPosition = new Vector3(w / 2f + 0.05f, -h / 2f + 0.004f, -0.01f);
            perch.localRotation = Quaternion.Euler(0f, -18f, 0f);
            var m = ZumiFlowKit.Mascot(mascotPrefab, perch, s.panelMascotHeight, "happy");
            inviteMascot = m ? perch : null;
            invite.gameObject.SetActive(false);
        }

        PanelButton MakeButton(string text, string which, Vector2 at, float width, bool primary)
        {
            var s = Style;
            var b = new PanelButton();
            var go = new GameObject($"Invite {text}");
            go.SetActive(false);
            b.root = go.transform;
            b.root.SetParent(invite, false);
            b.root.localPosition = new Vector3(at.x, at.y, -0.002f);
            var h = s.buttonHeight;
            var fill = ZumiDraw.Shape(flat, b.parts, "Fill", b.root, 0f, primary ? s.buttonFill : s.secondaryFill, 0, ZumiDraw.Rounded(width, h, h / 2f));
            b.fill = fill.GetComponent<MeshRenderer>().sharedMaterial;
            if (primary)
            {
                b.ring = new Material(ZumiFlowKit.RimShader) { name = "Invite ring", renderQueue = b.parts.queue + 1 };
                var ring = new GameObject("Ring", typeof(MeshFilter), typeof(MeshRenderer));
                ring.transform.SetParent(b.root, false);
                ring.transform.localPosition = new Vector3(0f, 0f, -0.0004f);
                ring.GetComponent<MeshFilter>().sharedMesh = ZumiFlowKit.RoundedBand(new Vector2(width + 0.005f, h + 0.005f), h / 2f + 0.0025f, 0.0032f);
                ring.GetComponent<MeshRenderer>().sharedMaterial = b.ring;
            }
            var label = ZumiDraw.Text(flat, b.parts, "Label", b.root, new Vector3(0f, 0f, -0.001f), s.buttonCap, primary ? s.ink : s.softInk, 2, text);
            label.fontStyle = FontStyle.Bold;
            // a ray hits its box; a poke presses its face (a plane clipped to the button)
            var box = go.AddComponent<BoxCollider>();
            box.isTrigger = true;
            box.size = new Vector3(width, h, 0.01f);
            var surface = go.AddComponent<ColliderSurface>();
            surface.InjectAllColliderSurface(box);
            b.ray = go.AddComponent<RayInteractable>();
            b.ray.InjectAllRayInteractable(surface);
            var plane = go.AddComponent<PlaneSurface>();
            var clipper = go.AddComponent<BoundsClipper>();
            clipper.Size = new Vector3(width, h, 0.02f);
            var clipped = go.AddComponent<ClippedPlaneSurface>();
            clipped.InjectAllClippedPlaneSurface(plane, new IBoundsClipper[] { clipper });
            b.poke = go.AddComponent<PokeInteractable>();
            b.poke.InjectAllPokeInteractable(clipped);
            b.views = new IInteractableView[] { b.poke, b.ray };
            b.poke.WhenStateChanged += change =>
            {
                if (change.NewState == InteractableState.Select) InvitePress(which, "poke");
            };
            b.ray.WhenStateChanged += change =>
            {
                if (change.NewState == InteractableState.Select) InvitePress(which, "ray");
            };
            go.SetActive(true);
            return b;
        }

        void OpenInvite()
        {
            if (Invite != null) return;
            if (!invite) BuildInvite();
            Invite = "opening";
            inviteSince = Time.time;
            Debug.Log("[Zumi] carousel: Create turns over: invite only");
            InviteOpened?.Invoke();
        }

        /// <summary>The invite panel turns back into the Create card.</summary>
        public void CloseInvite(string why = "back")
        {
            if (Invite is null or "closing") return;
            Invite = "closing";
            Debug.Log($"[Zumi] carousel: the invite panel turns back ({why})");
        }

        void InvitePress(string which, string how)
        {
            // only a panel fully turned, a beat after (the poke that turned it may still be pressing)
            if (Invite != "open" || Time.time - inviteSince < InviteSettleSeconds || State != "shown") return;
            if (which == "back")
            {
                Note($"{how} invite back", "Create turns back");
                CloseInvite();
                return;
            }
            Note($"{how} invite see", "See how it's made");
            SeeHowPressed?.Invoke();
        }

        /// <summary>The invite panel's buttons take a press only this long after it has turned.</summary>
        public const float InviteSettleSeconds = 0.25f;

        /// <summary>Presses a button of the invite panel ("see", "back"), as a ray pinch does (tools and tests).</summary>
        public void PressInvite(string which) => InvitePress(which, "tool");

        // the turn over: the card turns its edge to the reader (0 to 0.5), then the panel turns in from the other side
        void Flip(float dt)
        {
            if (Invite == null) return;
            var s = Style;
            var createIndex = items.FindIndex(x => x.kind == "create");
            // swiping or moving to another item closes it
            if (Invite is "opening" or "open" && State == "shown" && (Dragging != null || goTo.HasValue || Mathf.Abs(Scroll - createIndex) > 0.15f))
                CloseInvite("the arc turned");
            var opening = Invite is "opening" or "open";
            flip = Mathf.MoveTowards(flip, opening ? 1f : 0f, dt / s.flipSeconds);
            if (Invite == "opening" && flip >= 1f)
            {
                Invite = "open";
                inviteSince = Time.time;
            }
            if (Invite == "closing" && flip <= 0f)
            {
                Invite = null;
                invite.gameObject.SetActive(false);
                InviteClosed?.Invoke();
            }
        }

        void PlaceInvite(Item item, float fold)
        {
            if (!invite) return;
            var s = Style;
            var on = flip > 0.5f && Invite != null;
            if (invite.gameObject.activeSelf != on) invite.gameObject.SetActive(on);
            if (!on) return;
            var k = (flip - 0.5f) * 2f;
            var yaw = -90f * (1f - ZumiFlowKit.Smooth(k));
            invite.SetPositionAndRotation(item.position - item.front * 0.008f, Quaternion.LookRotation(-item.front, Vector3.up) * Quaternion.Euler(0f, yaw, 0f));
            invite.localScale = Vector3.one * Mathf.Lerp(0.9f, 1f, ZumiFlowKit.Smooth(k)) * (1f - 0.5f * fold);
            var alpha = 1f - fold;
            inviteParts.SetAlpha(alpha);
            var live = Invite == "open" && fold <= 0f;
            foreach (var b in new[] { seeButton, backButton })
            {
                if (b.ray.enabled != live) b.ray.enabled = live;
                if (b.poke.enabled != live) b.poke.enabled = live;
                var hovered = live && b.Touched;
                var target = live && b.Selected ? s.buttonPressScale : hovered ? s.buttonHoverScale : 1f;
                b.scale = Mathf.MoveTowards(b.scale, target, Time.deltaTime * 1.5f);
                b.root.localScale = Vector3.one * b.scale;
                b.parts.SetAlpha(alpha);
                if (b.ring)
                {
                    b.ring.SetFloat("_Turn", -Time.time * 0.6f);
                    b.ring.SetColor("_Color", new Color(1f, 1f, 1f, (hovered ? 1f : 0.8f) * alpha));
                }
                else
                {
                    var c = hovered ? s.secondaryHover : s.secondaryFill;
                    b.fill.SetColor("_Color", new Color(c.r, c.g, c.b, alpha));
                }
            }
            if (inviteMascot) inviteMascot.gameObject.SetActive(alpha > 0.05f);
        }

        Transform MakeEmpty()
        {
            var s = Style;
            var parts = new ZumiDraw.Parts { blended = true, queue = 2990 };
            var t = new GameObject("Empty place").transform;
            ZumiDraw.Shape(flat, parts, "Fill", t, 0f, s.emptyFill, 0, ZumiDraw.Rounded(s.cardSize.x, s.cardSize.y, s.cardCorner));
            var frame = ZumiFlowKit.Picture(Texture2D.whiteTexture, s.emptyFrame, 2992);
            var band = new GameObject("Frame", typeof(MeshFilter), typeof(MeshRenderer));
            band.transform.SetParent(t, false);
            band.transform.localPosition = new Vector3(0f, 0f, -0.0005f);
            band.GetComponent<MeshFilter>().sharedMesh = ZumiFlowKit.RoundedBand(s.cardSize, s.cardCorner, 0.0015f);
            band.GetComponent<MeshRenderer>().sharedMaterial = frame;
            empties.Add((t, parts, frame));
            return t;
        }

        void EnsureDressing()
        {
            var s = Style;
            if (!glow)
            {
                glowMaterial = new Material(ZumiFlowKit.GlowShader) { name = "Carousel ring", renderQueue = 2440 };
                glowMaterial.SetFloat("_Core", 0f);
                glow = ZumiFlowKit.Card("Carousel ring", null, Vector2.one, glowMaterial).transform;
                rimMaterial = new Material(ZumiFlowKit.RimShader) { name = "Carousel rim", renderQueue = 3010 };
                rim = new GameObject("Carousel rim", typeof(MeshFilter), typeof(MeshRenderer)).transform;
                rim.GetComponent<MeshRenderer>().sharedMaterial = rimMaterial;
                perch = new GameObject("Carousel perch").transform;
                var m = ZumiFlowKit.Mascot(mascotPrefab, perch, s.mascotHeight, "happy");
                mascot = m ? m.transform : null;
                BuildInfo();
            }
            SetDressing(true);
        }

        void SetDressing(bool on)
        {
            if (!glow) return;
            glow.gameObject.SetActive(on);
            rim.gameObject.SetActive(on);
            perch.gameObject.SetActive(on);
            info.gameObject.SetActive(on);
        }

        // under the middle: a cream pill (title, one line), a chip with a hand ("Grab to read"), the dots
        void BuildInfo()
        {
            var s = Style;
            info = new GameObject("Carousel info").transform;
            ZumiDraw.Shape(flat, infoParts, "Pill", info, 0f, s.plate, 0, ZumiDraw.Rounded(s.pillWidth, s.pillHeight, s.pillHeight / 2f));
            title = ZumiDraw.Text(flat, infoParts, "Title", info, new Vector3(0f, 0.009f, -0.002f), s.titleCap, s.ink, 2, "");
            title.fontStyle = FontStyle.Bold;
            line = ZumiDraw.Text(flat, infoParts, "Line", info, new Vector3(0f, -0.014f, -0.002f), s.lineCap, s.softInk, 2, "");
            chip = new GameObject("Chip").transform;
            chip.SetParent(info, false);
            chip.localPosition = new Vector3(0f, -s.pillHeight / 2f - s.chipGap - s.chipHeight / 2f, 0f);
            ZumiDraw.Shape(flat, chipParts, "Chip", chip, 0f, s.cream, 0, ZumiDraw.Rounded(0.1f, s.chipHeight, s.chipHeight / 2f));
            // a hand: a palm and four fingers
            var hand = new GameObject("Hand").transform;
            hand.SetParent(chip, false);
            hand.localPosition = new Vector3(-0.034f, -0.002f, -0.001f);
            ZumiDraw.Shape(flat, chipParts, "Palm", hand, 0f, s.softInk, 2, ZumiDraw.Rounded(0.009f, 0.008f, 0.003f),
                ZumiDraw.Box(-0.0042f, 0.003f, 0.0016f, 0.006f), ZumiDraw.Box(-0.0019f, 0.003f, 0.0016f, 0.0075f),
                ZumiDraw.Box(0.0004f, 0.003f, 0.0016f, 0.007f), ZumiDraw.Box(0.0027f, 0.003f, 0.0016f, 0.0055f));
            chipText = ZumiDraw.Text(flat, chipParts, "Hint", chip, new Vector3(0.006f, 0f, -0.002f), s.chipCap, s.softInk, 2, "");
            dots = new GameObject("Dots").transform;
            dots.SetParent(info, false);
            dots.localPosition = new Vector3(0f, chip.localPosition.y - s.chipHeight / 2f - s.dotsGap, 0f);
            dotPillMaterial = new Material(ZumiFlowKit.RimShader) { name = "Dot pill", renderQueue = 3405 };
        }

        void RebuildDots()
        {
            dotsFor = items.Count;
            foreach (Transform c in dots) Destroy(c.gameObject);
            dotParts.Destroy();
            var s = Style;
            var x0 = -(items.Count - 1) * s.dotPitch / 2f;
            for (var i = 0; i < items.Count; i++)
            {
                var d = ZumiDraw.Shape(flat, dotParts, $"Dot {i}", dots, -0.001f, s.softInk, 1, ZumiDraw.Disc(s.dot / 2f, 16));
                d.localPosition = new Vector3(x0 + i * s.dotPitch, 0f, -0.001f);
            }
            var pill = ZumiFlowKit.Card("Current", dots, new Vector2(s.dotPill, s.dot * 1.1f), dotPillMaterial);
            pill.transform.localPosition = new Vector3(0f, 0f, -0.002f);
            pill.GetComponent<MeshFilter>().sharedMesh = ZumiFlowKit.RoundedBand(Vector2.one, 0.5f, 0.5f, 6);
        }

        // ---- input -----------------------------------------------------------------------------------------------

        static bool Hovered(Item item) =>
            item.ray && item.ray.State is InteractableState.Hover or InteractableState.Select;

        bool Busy => State != "shown" || arrival != null || AnyHeld();

        bool AnyHeld()
        {
            foreach (var i in items)
                if (i.book && i.book.State is "held" or "opening") return true;
            return false;
        }

        void Press(Item item, string how)
        {
            if (Busy) return;
            var i = items.IndexOf(item);
            if (i < 0) return;
            var centre = i == CentreIndex && Mathf.Abs(Scroll - i) < SettledWithin;
            if (!centre)
            {
                goTo = i;
                velocity = 0f;
                Note($"{how} side {i}", $"{item.title} to the middle");
                return;
            }
            if (item.kind == "create")
            {
                Note($"{how} centre create", "Create: invite only");
                OpenInvite();
                return;
            }
            // a poke on the middle comic is a hand reaching to take it: only a ray pinch opens it
            if (how == "poke") return;
            Note($"{how} centre comic", $"{item.title} opens");
            item.book.Open();
        }

        void Note(string press, string what)
        {
            LastPress = press;
            Presses++;
            Debug.Log($"[Zumi] carousel: {press}: {what}");
        }

        void CreateGrabbed()
        {
            grabbedOnce = true;
            if (Busy || Invite != null) return;
            var i = items.FindIndex(x => x.kind == "create");
            if (i != CentreIndex) return;
            Note("grab centre create", "Create: invite only");
            OpenInvite();
        }

        void RayDown(Item item)
        {
            if (Busy) return;
            rayItem = item;
            rayBy = null;
            foreach (var r in item.ray.SelectingInteractors)
            {
                rayBy = r;
                break;
            }
            rayStartYaw = rayBy ? Yaw(rayBy.Forward) : 0f;
            rayStartAcross = rayLastAcross = rayBy ? Across(rayBy) : 0f;
            rayDragged = false;
            goTo = null;
        }

        // where the ray crosses the arc's middle plane, metres to the right of the eye's forward: a ray turned or a
        // hand moved sideways both move it
        float Across(RayInteractor r)
        {
            var forward = anchor.rotation * Vector3.forward;
            var dz = Vector3.Dot(r.Forward, forward);
            var origin = r.Origin;
            var t = dz > 0.05f ? (Vector3.Dot(anchor.position - origin, forward) + Style.distance) / dz : 0f;
            return Vector3.Dot(origin + r.Forward * t - anchor.position, anchor.rotation * Vector3.right);
        }

        float rayStartAcross, rayLastAcross;

        void RayUp(Item item)
        {
            if (rayItem != item) return;
            rayItem = null;
            if (rayDragged)
            {
                Dragging = null;
                Swipes++;
                Debug.Log($"[Zumi] carousel: turned by the ray to {Scroll:F2}, running on at {velocity:F2}/s");
                return;
            }
            Press(item, "ray");
        }

        float Yaw(Vector3 dir) => Vector3.SignedAngle(anchor.rotation * Vector3.forward, Vector3.ProjectOnPlane(dir, Vector3.up), Vector3.up);

        // a ray pinched and drawn sideways (turned past DragDegrees, or its crossing moved past DragMetres) turns
        // the arc, the items following the ray's crossing
        void FollowRay(float dt)
        {
            if (rayItem == null || !rayBy) return;
            var across = Across(rayBy);
            if (!rayDragged && Mathf.Abs(Mathf.DeltaAngle(rayStartYaw, Yaw(rayBy.Forward))) < DragDegrees && Mathf.Abs(across - rayStartAcross) < DragMetres) return;
            if (!rayDragged) rayLastAcross = rayStartAcross;
            rayDragged = true;
            Dragging = "ray";
            var d = -(across - rayLastAcross) / Style.side[1];
            rayLastAcross = across;
            Scroll += d;
            if (dt > 0f) velocity = Mathf.Lerp(velocity, d / dt, 0.4f);
        }

        // an open hand moving sideways through the arc's band turns it with the hand
        void FollowHands(float dt)
        {
            if (dt <= 0f || Dragging == "ray" || AnyHeld()) return;
            var n = 0;
            var turning = false;
            var eye = anchor.position;
            var right = anchor.rotation * Vector3.right;
            var forward = anchor.rotation * Vector3.forward;
            foreach (var tip in hands.OpenTips())
            {
                var had = lastTips.TryGetValue(n, out var last);
                sweeps.TryGetValue(n, out var sweep);
                lastTips[n] = tip;
                var key = n++;
                if (!had) continue;
                var rel = tip - eye;
                var inBand = Mathf.Abs(Vector3.Dot(rel, forward) - Style.distance) < SwipeBand && Mathf.Abs(rel.y + Style.drop) < 0.25f
                             && Mathf.Abs(Vector3.Dot(rel, right)) < Style.side[2] + 0.1f;
                var move = tip - last;
                var sideways = Vector3.Dot(move, right);
                // a sweep: an open hand moving across, fast, and mostly across (a hand reaching in to take the
                // middle comic moves toward it, not across it)
                var across = inBand && Mathf.Abs(sideways) / dt >= SwipeMinSpeed && Mathf.Abs(sideways) > 2f * (move - right * sideways).magnitude;
                if (!across && Time.time > handTurnUntil)
                {
                    sweeps[key] = 0f;
                    continue;
                }
                if (!inBand) continue;
                sweep += sideways;
                sweeps[key] = sweep;
                if (Mathf.Abs(sweep) < SwipeStart && Dragging != "hand") continue;
                // one place per side[1] metres of hand; the items under the hand move with it
                var d = -sideways / Style.side[1];
                Scroll += d;
                velocity = Mathf.Lerp(velocity, d / dt, 0.5f);
                goTo = null;
                turning = true;
            }
            if (turning)
            {
                if (Dragging != "hand") Debug.Log("[Zumi] carousel: an open hand turns it");
                Dragging = "hand";
                handTurnUntil = Time.time + 0.12f;
            }
            else if (Dragging == "hand" && Time.time > handTurnUntil)
            {
                Dragging = null;
                Swipes++;
                Debug.Log($"[Zumi] carousel: swiped by hand to {Scroll:F2}, running on at {velocity:F2}/s");
            }
        }

        /// <summary>Sets the arc running at that speed (items a second), as a swipe does (tools and tests).</summary>
        public void Fling(float perSecond)
        {
            if (Busy) return;
            goTo = null;
            velocity = perSecond;
            Swipes++;
        }

        /// <summary>Presses item i, as a ray pinch does (tools and tests).</summary>
        public void PressItem(int i)
        {
            if (i >= 0 && i < items.Count) Press(items[i], "tool");
        }

        // ---- the loop --------------------------------------------------------------------------------------------

        void Update()
        {
            if (State == "hidden") return;
            var dt = Time.deltaTime;
            if (State == "fanning" && Time.time - shownSince > Style.fanSeconds + Style.fanStagger * 3f) State = "shown";
            if (State == "shown" && arrival == null)
            {
                FollowRay(dt);
                FollowHands(dt);
                Coast(dt);
            }
            Arriving();
            Flip(dt);
            Layout(dt);
            if (State == "folding" && Time.time - foldSince >= Style.foldSeconds)
            {
                Hide();
                var done = folded;
                folded = null;
                done?.Invoke();
            }
        }

        // let go, it runs on and slows, then settles on the nearest item (or the one pressed); never past the ends
        void Coast(float dt)
        {
            if (Dragging != null || items.Count == 0) return;
            var last = items.Count - 1;
            if (goTo.HasValue)
            {
                Scroll = Mathf.SmoothDamp(Scroll, goTo.Value, ref settleVelocity, SettleSeconds * 1.5f);
                if (Mathf.Abs(Scroll - goTo.Value) < 0.002f)
                {
                    Scroll = goTo.Value;
                    goTo = null;
                }
                return;
            }
            Scroll += velocity * dt;
            velocity *= Mathf.Exp(-Friction * dt);
            if (Scroll < 0f || Scroll > last) velocity *= Mathf.Exp(-12f * dt);
            if (Mathf.Abs(velocity) >= SettleSpeed) return;
            settleVelocity = velocity;
            Scroll = Mathf.SmoothDamp(Scroll, Mathf.Clamp(Mathf.Round(Scroll), 0, last), ref settleVelocity, SettleSeconds);
            velocity = settleVelocity;
            if (Mathf.Abs(velocity) < 0.01f && Mathf.Abs(Scroll - Mathf.Round(Scroll)) < 0.002f) velocity = 0f;
        }

        // the arriving comic flies in in pencil, then the colour sweeps across it, left to right
        void Arriving()
        {
            if (arrival == null) return;
            var s = Style;
            var t = Time.time - arrival.since;
            var item = arrival.item;
            if (arrival.phase == "flying" && t >= s.arriveSeconds)
            {
                arrival.phase = "sweeping";
                arrival.since = Time.time;
                Debug.Log($"[Zumi] carousel: {item.title} landed; its colour sweeps in");
                return;
            }
            if (arrival.phase != "sweeping") return;
            var k = Mathf.Clamp01(t / s.sweepSeconds);
            var right = Vector3.Cross(item.front, Vector3.up).normalized;
            var half = s.cardSize.x * item.scale / 2f + 0.01f;
            var from = Vector3.Dot(item.position, right) - half;
            item.book.SetGraphite(1f, new Vector4(right.x, right.y, right.z, from + 2f * half * ZumiFlowKit.Smooth(k)));
            if (k < 1f) return;
            item.book.SetGraphite(0f, new Vector4(1f, 0f, 0f, -1000f));
            arrival = null;
            Debug.Log($"[Zumi] carousel: {item.title} is in colour");
        }

        static float Table(float[] values, float at)
        {
            at = Mathf.Clamp(at, 0f, values.Length - 1);
            var i = Mathf.Min((int)at, values.Length - 2);
            return Mathf.Lerp(values[i], values[i + 1], at - i);
        }

        void Layout(float dt)
        {
            var s = Style;
            var eye = anchor.position;
            var forward = anchor.rotation * Vector3.forward;
            var right = anchor.rotation * Vector3.right;
            var now = Time.time;
            var centre = CentreIndex;
            var k = 1f - Mathf.Exp(-14f * dt);
            var fold = State == "folding" ? ZumiFlowKit.Smooth((now - foldSince) / s.foldSeconds) : 0f;
            var middle = eye + forward * (s.distance + s.back[0]) + Vector3.up * -s.drop;
            if (centre != centreBefore)
            {
                centreBefore = centre;
                mascotSince = -10f;
            }

            for (var i = 0; i < items.Count; i++)
            {
                var item = items[i];
                var o = i - Scroll;
                var a = Mathf.Abs(o);
                var shown = a < 2.6f;
                var waiting = item.book ? item.book.State == "shelf" : true;
                var visual = item.book ? item.book.transform : item.card;
                // the Create card is turned over into the invite panel past half the turn
                var turned = item.kind == "create" && flip >= 0.5f;
                if (waiting && visual.gameObject.activeSelf != (shown && !turned)) visual.gameObject.SetActive(shown && !turned);
                var targetable = shown && waiting && State == "shown" && arrival == null && !(item.kind == "create" && Invite != null);
                if (item.hit.gameObject.activeSelf != targetable) item.hit.gameObject.SetActive(targetable);
                // no poke on the middle comic: a hand reaching through its face to take it would be taken by the
                // poke (the rig gives a poke precedence over a grab)
                var pokeOn = !(item.book && i == centre);
                if (item.poke.enabled != pokeOn) item.poke.enabled = pokeOn;
                item.shadow.gameObject.SetActive(shown && waiting);
                if (!shown || !waiting) continue;

                var isCentre = i == centre && a < SettledWithin && State == "shown";
                var aliveWanted = isCentre && arrival == null ? 1f : 0f;
                item.alive = Mathf.MoveTowards(item.alive, aliveWanted, dt / (aliveWanted > item.alive ? s.aliveSeconds : s.leaveSeconds));
                if (item.alive > 0.5f && i == centre && mascotSince < 0f && item.kind == "comic") mascotSince = now;

                var sign = Mathf.Sign(o);
                var bob = s.floatMetres * Mathf.Sin(2f * Mathf.PI * (s.floatHz * now + i * 0.37f));
                var front = Quaternion.AngleAxis(sign * Table(s.turn, a), Vector3.up) * -forward;
                var position = eye + forward * (s.distance + Table(s.back, a)) + right * (sign * Table(s.side, a))
                               + Vector3.up * (bob - s.drop) - forward * (s.aliveLift * ZumiFlowKit.Smooth(item.alive));
                var scale = Table(s.scale, a) * (Hovered(item) && State == "shown" ? s.hoverScale : 1f);
                var opacity = Table(s.opacity, a);
                // the fan, out of fanFrom, the middle first; the fold, into the middle
                var f = ZumiFlowKit.Smooth((now - shownSince - s.fanStagger * a) / s.fanSeconds);
                if (arrival != null && arrival.item == item)
                {
                    var t = arrival.phase == "flying" ? ZumiFlowKit.Smooth((now - arrival.since) / s.arriveSeconds) : 1f;
                    var lift = Mathf.Sin(t * Mathf.PI) * 0.08f;
                    position = Vector3.Lerp(arrival.from, position, t) + Vector3.up * lift;
                    scale *= Mathf.Lerp(0.3f, 1f, t);
                    opacity *= Mathf.Clamp01(t * 3f);
                    f = 1f;
                    item.placed = false;
                }
                if (f < 1f || fold > 0f)
                {
                    position = Vector3.Lerp(Vector3.Lerp(fanFrom, position, f), middle, fold);
                    scale *= Mathf.Lerp(0.2f, 1f, f) * (1f - 0.6f * fold);
                    opacity *= f * (1f - fold);
                    item.placed = false;
                }
                if (item.placed)
                {
                    // a comic let go glides back to its place
                    item.position = Vector3.Lerp(item.position, position, k);
                    item.front = Vector3.Slerp(item.front, front, k).normalized;
                    item.scale = Mathf.Lerp(item.scale, scale, k);
                }
                else
                {
                    item.position = position;
                    item.front = front;
                    item.scale = scale;
                    item.placed = f >= 1f && fold <= 0f;
                }
                item.opacity = opacity;
                Place(item, a);
                if (item.kind == "create") PlaceInvite(item, fold);
            }
            Empties(eye, forward, right, now, fold);
            Dress(centre, now);
        }

        void Place(Item item, float a)
        {
            var s = Style;
            var w = s.cardSize.x * item.scale;
            var h = s.cardSize.y * item.scale;
            if (item.book)
            {
                var size = item.book.Size.y > 0f ? s.cardSize.y / item.book.Size.y : 1f;
                item.book.Place(item.position, Quaternion.LookRotation(item.front, Vector3.up), item.scale * size);
                var brightness = Mathf.Lerp(1f, s.offBrightness, Mathf.Clamp01(a * 2f) * (1f - item.alive));
                item.book.SetShade(brightness, item.opacity);
                item.book.SetGrabbable(State == "shown" && arrival == null && item.alive > 0.5f && Dragging == null);
            }
            else
            {
                var turn = item.kind == "create" ? 180f * ZumiFlowKit.Smooth(Mathf.Min(flip, 0.5f)) : 0f;
                item.card.SetPositionAndRotation(item.position, Quaternion.LookRotation(-item.front, Vector3.up) * Quaternion.Euler(0f, turn, 0f));
                item.card.localScale = Vector3.one * item.scale;
                item.parts.SetAlpha(item.opacity);
            }
            var rot = Quaternion.LookRotation(-item.front, Vector3.up);
            item.hit.SetPositionAndRotation(item.position + item.front * 0.006f, rot);
            item.box.size = new Vector3(w, h, 0.01f);
            item.shadow.SetPositionAndRotation(item.position - item.front * 0.012f + Vector3.down * s.shadowDrop * item.scale, rot);
            item.shadow.localScale = new Vector3(w * s.shadowGrow, h * s.shadowGrow, 1f);
            ZumiFlowKit.SetTint(item.shadowMaterial, new Color(s.ink.r, s.ink.g, s.ink.b, s.shadowAlpha * item.opacity));
        }

        // places the row has no item for: grey frames, untouchable
        void Empties(Vector3 eye, Vector3 forward, Vector3 right, float now, float fold)
        {
            var s = Style;
            var used = 0;
            var c = Mathf.RoundToInt(Scroll);
            for (var p = c - 3; p <= c + 3; p++)
            {
                if (p >= 0 && p < items.Count) continue;
                var o = p - Scroll;
                var a = Mathf.Abs(o);
                if (a > 2.6f) continue;
                if (used >= empties.Count) MakeEmpty();
                var (t, parts, frame) = empties[used++];
                t.gameObject.SetActive(true);
                var sign = Mathf.Sign(o);
                var front = Quaternion.AngleAxis(sign * Table(s.turn, a), Vector3.up) * -forward;
                var position = eye + forward * (s.distance + Table(s.back, a)) + right * (sign * Table(s.side, a)) + Vector3.up * -s.drop;
                var f = ZumiFlowKit.Smooth((now - shownSince - s.fanStagger * a) / s.fanSeconds) * (1f - fold);
                t.SetPositionAndRotation(position, Quaternion.LookRotation(-front, Vector3.up));
                t.localScale = Vector3.one * Table(s.scale, a);
                var alpha = Table(s.opacity, a) * f;
                parts.SetAlpha(alpha);
                ZumiFlowKit.SetTint(frame, new Color(s.emptyFrame.r, s.emptyFrame.g, s.emptyFrame.b, s.emptyFrame.a * alpha));
            }
            EmptyShown = used;
            for (var i = used; i < empties.Count; i++) empties[i].t.gameObject.SetActive(false);
        }

        // the middle's ring, rim, mascot, pill, chip and dots
        void Dress(int centre, float now)
        {
            if (!glow || centre < 0) return;
            var s = Style;
            var item = items[centre];
            var alive = ZumiFlowKit.Smooth(item.alive) * (State == "folding" ? 0f : 1f);
            var waiting = !item.book || item.book.State == "shelf";
            var rot = Quaternion.LookRotation(-item.front, Vector3.up);
            var hovered = Hovered(item);
            var on = alive > 0.001f && waiting;
            // the Create card turned over into the invite panel: its rim and the chip under it go
            var turned = item.kind == "create" ? Mathf.Clamp01(flip * 2f) : 0f;
            glow.gameObject.SetActive(on);
            rim.gameObject.SetActive(on);
            if (on)
            {
                glow.SetPositionAndRotation(item.position - item.front * 0.02f, rot);
                glow.localScale = Vector3.one * (s.glowSize * s.cardSize.y * item.scale * Mathf.Lerp(0.6f, 1f, alive));
                glowMaterial.SetFloat("_Turn", now * s.glowTurn);
                glowMaterial.SetColor("_Color", new Color(1f, 1f, 1f, (hovered ? s.glowHoverAlpha : s.glowAlpha) * alive));
                var rimSize = s.cardSize + Vector2.one * (2f * s.rimGap);
                if (rimFor != rimSize)
                {
                    rimFor = rimSize;
                    rim.GetComponent<MeshFilter>().sharedMesh = ZumiFlowKit.RoundedBand(rimSize, s.rimCorner, s.rimWidth);
                }
                rim.SetPositionAndRotation(item.position + item.front * 0.002f, rot);
                rim.localScale = Vector3.one * item.scale;
                rimMaterial.SetFloat("_Turn", -now * s.glowTurn * 1.5f);
                rimMaterial.SetColor("_Color", new Color(1f, 1f, 1f, (hovered ? 1f : s.rimAlpha) * alive * (1f - turned)));
            }
            // the mascot hops onto the comic's top right corner
            var hop = mascotSince > 0f ? Mathf.Clamp01((now - mascotSince) / s.hopSeconds) : 0f;
            var mascotOn = mascot && item.kind == "comic" && waiting && alive > 0.5f && hop > 0f;
            perch.gameObject.SetActive(mascotOn);
            if (mascotOn)
            {
                var right = Vector3.Cross(item.front, Vector3.up).normalized;
                var corner = item.position + right * (s.cardSize.x * item.scale / 2f - 0.03f) + Vector3.up * (s.cardSize.y * item.scale / 2f) + item.front * 0.01f;
                var start = corner + right * 0.06f + Vector3.down * 0.04f;
                var p = Vector3.Lerp(start, corner, ZumiFlowKit.Smooth(hop)) + Vector3.up * (Mathf.Sin(hop * Mathf.PI) * s.hopHeight);
                perch.SetPositionAndRotation(p, rot);
                perch.localScale = Vector3.one * Mathf.Lerp(0.3f, 1f, ZumiFlowKit.Smooth(hop * 1.5f));
            }
            // the pill, the chip and the dots under the middle
            var infoAlpha = State is "folding" ? 0f : ZumiFlowKit.Smooth((now - shownSince) / s.fanSeconds) * (arrival != null ? 0f : 1f) * (1f - turned);
            info.gameObject.SetActive(infoAlpha > 0.001f);
            if (!info.gameObject.activeSelf) return;
            // Create names itself on its card: no pill under it, and the chip rises into the pill's place
            var pillShown = item.kind != "create";
            var rise = pillShown ? 0f : s.pillHeight / 2f + s.chipGap + s.chipHeight / 2f;
            var below = anchor.position + anchor.rotation * new Vector3(0f, -s.drop - s.cardSize.y / 2f - s.infoBelow - s.pillHeight / 2f + rise, s.distance + s.back[0] - 0.01f);
            info.SetPositionAndRotation(below, ZumiFlowKit.Facing(below, anchor.position));
            var settled = Mathf.Clamp01(1f - Mathf.Abs(Scroll - centre) * 2f);
            var titleText = item.title.ToUpperInvariant();
            if (title.text != titleText) title.text = titleText;
            if (line.text != item.line) line.text = item.line;
            if (chipText.text != item.hint) chipText.text = item.hint;
            infoParts.SetAlpha(pillShown ? infoAlpha * settled : 0f);
            chipParts.SetAlpha(infoAlpha * settled * (!grabbedOnce || hovered ? 1f : 0f));
            if (dotsFor != items.Count) RebuildDots();
            dotParts.SetAlpha(infoAlpha);
            var x0 = -(items.Count - 1) * s.dotPitch / 2f;
            var current = dots.Find("Current");
            if (current) current.localPosition = new Vector3(x0 + Scroll * s.dotPitch, 0f, -0.002f);
            dotPillMaterial.SetFloat("_Turn", now);
            dotPillMaterial.SetColor("_Color", new Color(1f, 1f, 1f, infoAlpha));
            if (item.book && item.book.Grabbed) grabbedOnce = true;
        }

        Vector2 rimFor;

        void OnDestroy()
        {
            infoParts.Destroy();
            chipParts.Destroy();
            dotParts.Destroy();
            inviteParts.Destroy();
            foreach (var b in new[] { seeButton, backButton })
            {
                if (b == null) continue;
                b.parts.Destroy();
                if (b.ring) Destroy(b.ring);
            }
            if (invite) Destroy(invite.gameObject);
            foreach (var e in empties)
            {
                e.parts.Destroy();
                Destroy(e.frame);
            }
            foreach (var i in items)
            {
                if (i.hit) Destroy(i.hit.gameObject);
                if (i.shadow) Destroy(i.shadow.gameObject);
                if (i.shadowMaterial) Destroy(i.shadowMaterial);
                i.parts?.Destroy();
            }
            foreach (var m in new[] { glowMaterial, rimMaterial, dotPillMaterial })
                if (m) Destroy(m);
        }
    }
}
