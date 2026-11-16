using System;
using System.Collections.Generic;
using UnityEngine;

namespace Zumi
{
    /// <summary>
    /// The few things the reader says in words, each a cream card that belongs to the seat like the panel does:
    ///   title         the series and the episode, in the middle, from the moment the episode is open until the clock
    ///                 starts (at least TitleSeconds), then gone over the clock's first TitleFadeSeconds. Only real
    ///                 titles: one that is missing, empty or just the id again is not shown (TitleLines).
    ///   hint          one line about the hand menu under the panel, the first time only: until the menu was opened
    ///                 once or the line was up HintSeconds; kept in ZumiSettings.
    ///   end           when the clock has ended: a card below the last panel with one round button per thing to do
    ///                 next. Today that is Replay; the row is laid out for any number (EndActionIds).
    ///   open_failed   the episode cannot be opened.
    ///   panel_missing the panel on the clock has no scene that loads: a plain card stands where it would be, the
    ///                 clock keeps time and the voices go on.
    /// This reads the clock and never moves it; Replay goes through the reader.
    /// </summary>
    [RequireComponent(typeof(ZumiSeat))]
    public class ZumiCards : MonoBehaviour
    {
        /// <summary>Real seconds a title is on show before the clock may start.</summary>
        public const float TitleSeconds = 2f;
        /// <summary>Clock seconds over which the title goes once the episode plays.</summary>
        public const float TitleFadeSeconds = 0.6f;
        /// <summary>Real seconds after the episode starts before the hint comes, and how long it stays.</summary>
        public const float HintDelaySeconds = 2f, HintSeconds = 12f;
        /// <summary>Seconds after the clock ended over which the end card comes.</summary>
        public const float EndFadeSeconds = 0.6f;
        /// <summary>Real seconds a card takes to come or go when it follows a state rather than the clock.</summary>
        public const float FadeSeconds = 0.2f;
        /// <summary>Metres from the seat's eye to a card: just in front of the panel's windows.</summary>
        public const float CardDistance = 0.9f;
        /// <summary>The end card: metres from the seat's eye (within reach of a finger, and of a ray) and below its level.</summary>
        public const float EndCardDistance = 0.6f, EndCardDrop = 0.22f;
        /// <summary>Metres between the panel's lower edge and the hint, at the panel's distance.</summary>
        public const float HintGap = 0.07f;
        /// <summary>The end card's buttons: their radius and the distance between two.</summary>
        public const float EndButtonRadius = 0.028f, EndButtonPitch = 0.085f;
        public const string HintText = "Hold an open palm toward your face for the menu";
        public const string EndText = "The end", OpenFailedText = "This episode can't be opened", PanelMissingText = "This panel can't be shown";
        // capitals' height in metres: 1.3 and 0.9 degrees at the cards' distance
        const float LargeCap = 0.02f, SmallCap = 0.014f, Padding = 0.03f, LineGap = 1.9f;
        const int Queue = 3500;

        sealed class Card
        {
            public string name;
            public Transform root;
            public readonly ZumiDraw.Parts parts = new() { blended = true, queue = Queue };
            public readonly List<string> lines = new();
            public float alpha;
            public Vector2 size;
        }

        sealed class EndAction
        {
            public string id, label;
            public Action act;
            public Vector2[][] icon;
        }

        static readonly IReadOnlyList<string> None = Array.Empty<string>();

        ZumiReader reader;
        ZumiPanelPresenter presenter;
        ZumiHandMenu menu;
        ZumiSeat seat;
        Shader shader;
        Card title, hint, end, openFailed, panelMissing;
        readonly List<EndAction> endActions = new();
        readonly List<string> endActionIds = new();
        readonly List<ZumiDraw.RoundButton> endButtons = new();
        bool titleArmed, hintPending;
        float titleSince, startedSince = -1f, hintShownFor;
        string openFailedFor;

        // ---- read-only state for tests and tools ---------------------------------------------------------------

        /// <summary>The card on show now: "open_failed", "end", "panel_missing", "title"; null when none is.</summary>
        public string Notice => Shown(openFailed) ? "open_failed" : Shown(end) ? "end" : Shown(panelMissing) ? "panel_missing" : Shown(title) ? "title" : null;
        /// <summary>That card's lines of lettering.</summary>
        public IReadOnlyList<string> NoticeLines => Notice switch { "open_failed" => openFailed.lines, "end" => end.lines, "panel_missing" => panelMissing.lines, "title" => title.lines, _ => None };
        /// <summary>How much of that card shows, 0 to 1.</summary>
        public float NoticeAlpha => Notice switch { "open_failed" => openFailed.alpha, "end" => end.alpha, "panel_missing" => panelMissing.alpha, "title" => title.alpha, _ => 0f };
        /// <summary>Where that card is, in world space.</summary>
        public Vector3 NoticePosition => Notice switch { "open_failed" => openFailed.root.position, "end" => end.root.position, "panel_missing" => panelMissing.root.position, "title" => title.root.position, _ => default };
        /// <summary>The episode's title as it is shown at the start; empty when the file has no real title.</summary>
        public IReadOnlyList<string> Title => title?.lines ?? None;
        /// <summary>A real title has been on show long enough (or there is none): the clock may start.</summary>
        public bool TitleReady => title == null || !titleArmed || Time.unscaledTime - titleSince >= TitleSeconds;
        public bool HintShown => Shown(hint);
        public string HintLine => Shown(hint) ? hint.lines[0] : null;
        public Vector3 HintPosition => hint != null ? hint.root.position : default;
        /// <summary>Whether the hint was already given, as kept between launches.</summary>
        public bool HintSeen => ZumiSettings.MenuHintSeen;
        /// <summary>What the end card offers, in the order of its buttons.</summary>
        public IReadOnlyList<string> EndActionIds => endActionIds;
        public string LastEndAction { get; private set; }
        public int EndActionCount { get; private set; }

        static bool Shown(Card card) => card != null && card.alpha > 0.01f;

        /// <summary>The lines a title card shows for a file's series and episode: each title that is a real one. A
        /// title that is missing, blank, or only repeats its id (what the pipeline writes when it was given none) is
        /// not a title.</summary>
        public static List<string> TitleLines(string seriesId, string seriesTitle, string episodeId, string episodeTitle)
        {
            var lines = new List<string>();
            if (Real(seriesTitle, seriesId)) lines.Add(seriesTitle.Trim());
            if (Real(episodeTitle, episodeId)) lines.Add(episodeTitle.Trim());
            return lines;
        }

        static bool Real(string title, string id) =>
            !string.IsNullOrWhiteSpace(title) && !string.Equals(title.Trim(), id?.Trim(), StringComparison.OrdinalIgnoreCase);

        void Awake()
        {
            reader = GetComponent<ZumiReader>();
            presenter = GetComponent<ZumiPanelPresenter>();
            menu = GetComponent<ZumiHandMenu>();
            seat = GetComponent<ZumiSeat>();
            shader = menu.FlatShader;
            hintPending = !ZumiSettings.MenuHintSeen;
            endActions.Add(new EndAction { id = "replay", label = "Replay", act = () => reader.Replay(), icon = ReplayIcon() });
            foreach (var action in endActions) endActionIds.Add(action.id);
        }

        /// <summary>The episode's titles, as its file gives them; the card is made only for real ones.</summary>
        public void SetTitles(string seriesId, string seriesTitle, string episodeId, string episodeTitle)
        {
            Remove(ref title);
            var lines = TitleLines(seriesId, seriesTitle, episodeId, episodeTitle);
            if (lines.Count == 0) return;
            var text = new List<(string, float, Color)>();
            for (var i = 0; i < lines.Count; i++) text.Add((lines[i], i == 0 ? LargeCap : SmallCap, i == 0 ? ZumiDraw.Ink : ZumiDraw.SoftInk));
            title = Message("Title", new Vector3(0f, 0f, CardDistance), text, 0f);
        }

        /// <summary>The episode is about to begin, or begin again: its title comes first.</summary>
        public void Arm()
        {
            titleArmed = title != null;
            titleSince = Time.unscaledTime;
            startedSince = -1f;
        }

        void Update()
        {
            var clock = reader.Clock;
            var dt = Time.unscaledDeltaTime;
            var taken = seat.Taken;

            // the episode cannot be opened
            var failed = taken && reader.SourceState == nameof(EpisodeSourceState.Failed);
            if (failed && openFailed == null)
                openFailed = Message("OpenFailed", new Vector3(0f, 0f, CardDistance),
                    new List<(string, float, Color)> { (OpenFailedText, LargeCap, ZumiDraw.Ink), (reader.EpisodeName, SmallCap, ZumiDraw.SoftInk) }, 0f);
            Ease(openFailed, failed, dt);

            // the title: whole until the clock starts, then gone with the clock's first moments
            if (title != null)
            {
                if (!titleArmed) Set(title, 0f);
                else if (!reader.Started) Ease(title, taken, dt);
                else
                {
                    var left = 1f - (float)(clock.Time / TitleFadeSeconds);
                    Set(title, Mathf.Min(title.alpha, Mathf.Clamp01(left)));
                    if (left <= 0f) titleArmed = false;
                }
            }

            // the panel on the clock cannot be shown
            var missing = taken && clock != null && presenter.CurrentFailed;
            if (missing && panelMissing == null)
                panelMissing = Message("PanelMissing", new Vector3(0f, 0f, ZumiPanelPresenter.ReadingDistance),
                    new List<(string, float, Color)> { (PanelMissingText, SmallCap, ZumiDraw.SoftInk) }, 0.2f);
            Ease(panelMissing, missing, dt);

            // the hint, once
            if (reader.Started && startedSince < 0f) startedSince = Time.unscaledTime;
            var hinting = false;
            if (hintPending && reader.Started)
            {
                if (menu.Open || hintShownFor >= HintSeconds)
                {
                    hintPending = false;
                    ZumiSettings.MenuHintSeen = true;
                    Debug.Log($"[Zumi] cards: the menu hint was given ({(menu.Open ? "the menu was opened" : "shown its time")})");
                }
                else hinting = taken && !reader.Ended && Time.unscaledTime - startedSince >= HintDelaySeconds;
            }
            if (hinting && hint == null)
                hint = Message("Hint", Vector3.zero, new List<(string, float, Color)> { (HintText, SmallCap, ZumiDraw.Ink) }, 0f);
            if (hint != null && hinting)
            {
                // under the panel on show, whatever its shape
                var panel = presenter.ShownPanelMetres;
                var drop = panel.y > 0f ? panel.y / 2f + HintGap : 0.25f;
                hint.root.localPosition = new Vector3(0f, -drop, ZumiPanelPresenter.ReadingDistance - 0.05f);
                hint.root.localRotation = Quaternion.LookRotation(hint.root.localPosition);
                hintShownFor += dt;
            }
            Ease(hint, hinting, dt);

            // the end card, on the time since the clock ended
            var ended = taken && clock != null && reader.Ended;
            if (ended && end == null) BuildEnd();
            if (end != null)
            {
                Set(end, ended ? Mathf.Clamp01((float)(clock.EndedFor / EndFadeSeconds)) : 0f);
                foreach (var button in endButtons) button.disc.SetColor("_Color", WithAlpha(button.Touched ? ZumiDraw.Hover : ZumiDraw.Button, end.alpha));
            }
        }

        static Color WithAlpha(Color c, float a) => new(c.r, c.g, c.b, a);

        void Ease(Card card, bool shown, float dt)
        {
            if (card == null) return;
            Set(card, Mathf.MoveTowards(card.alpha, shown ? 1f : 0f, dt / FadeSeconds));
        }

        static void Set(Card card, float alpha)
        {
            card.alpha = alpha;
            var visible = alpha > 0.001f;
            if (card.root.gameObject.activeSelf != visible) card.root.gameObject.SetActive(visible);
            if (visible) card.parts.SetAlpha(alpha);
        }

        // a cream plate around centred lines of lettering, facing the seat's eye from `at` (in the seat's frame);
        // minHeight makes the plate at least that tall
        Card Message(string name, Vector3 at, List<(string text, float cap, Color colour)> lines, float minHeight)
        {
            var card = new Card { name = name, root = new GameObject($"Card {name}").transform };
            card.root.SetParent(transform, false);
            card.root.localPosition = at;
            if (at.sqrMagnitude > 1e-6f) card.root.localRotation = Quaternion.LookRotation(at);
            float width = 0f, height = 0f;
            foreach (var (text, cap, _) in lines)
            {
                width = Mathf.Max(width, ZumiDraw.Width(text, cap));
                height += cap * LineGap;
                card.lines.Add(text);
            }
            card.size = new Vector2(width + 2f * Padding, Mathf.Max(height + 2f * Padding, minHeight));
            ZumiDraw.Shape(shader, card.parts, "Plate", card.root, 0f, ZumiDraw.Plate, 0, ZumiDraw.Rounded(card.size.x, card.size.y, 0.02f));
            var y = height / 2f;
            foreach (var (text, cap, colour) in lines)
            {
                y -= cap * LineGap / 2f;
                ZumiDraw.Text(shader, card.parts, "Line", card.root, new Vector3(0f, y, -0.002f), cap, colour, 2, text);
                y -= cap * LineGap / 2f;
            }
            card.root.gameObject.SetActive(false);
            return card;
        }

        void BuildEnd()
        {
            var at = new Vector3(0f, -EndCardDrop, Mathf.Sqrt(EndCardDistance * EndCardDistance - EndCardDrop * EndCardDrop));
            end = new Card { name = "End", root = new GameObject("End").transform };
            end.root.SetParent(transform, false);
            end.root.localPosition = at;
            end.root.localRotation = Quaternion.LookRotation(at);
            end.lines.Add(EndText);
            // one column per action, the heading above them: more actions widen the plate, nothing else moves
            var n = endActions.Count;
            var width = Mathf.Max(ZumiDraw.Width(EndText, LargeCap), n * EndButtonPitch) + 2f * Padding;
            var height = LargeCap * LineGap + 2f * EndButtonRadius + SmallCap * LineGap + 2.5f * Padding;
            end.size = new Vector2(width, height);
            ZumiDraw.Shape(shader, end.parts, "Plate", end.root, 0f, ZumiDraw.Plate, 0, ZumiDraw.Rounded(width, height, 0.02f));
            var top = height / 2f - Padding;
            ZumiDraw.Text(shader, end.parts, "Heading", end.root, new Vector3(0f, top - LargeCap * LineGap / 2f, -0.002f), LargeCap, ZumiDraw.Ink, 2, EndText);
            var row = top - LargeCap * LineGap - Padding / 2f - EndButtonRadius;
            for (var i = 0; i < n; i++)
            {
                var action = endActions[i];
                var x = (i - (n - 1) / 2f) * EndButtonPitch;
                var button = ZumiDraw.Round(shader, end.parts, Capital(action.id), end.root, new Vector2(x, row), EndButtonRadius, 1, () => Fire(action));
                ZumiDraw.Shape(shader, end.parts, "Icon", button.transform, -0.002f, ZumiDraw.Ink, 2, action.icon);
                ZumiDraw.Text(shader, end.parts, "Label", end.root, new Vector3(x, row - EndButtonRadius - SmallCap * LineGap / 2f - 0.004f, -0.002f), SmallCap, ZumiDraw.SoftInk, 2, action.label);
                end.lines.Add(action.label);
                endButtons.Add(button);
            }
            end.root.gameObject.SetActive(false);
        }

        static string Capital(string id) => char.ToUpperInvariant(id[0]) + id.Substring(1);

        void Fire(EndAction action)
        {
            // a card that is still coming, or going, is not pressed
            if (end == null || end.alpha < 0.9f) return;
            LastEndAction = action.id;
            EndActionCount++;
            Debug.Log($"[Zumi] end card: {action.id}");
            action.act();
        }

        // three quarters of a ring with an arrowhead: again from the start
        static Vector2[][] ReplayIcon()
        {
            const float radius = 0.011f;
            // from the top, the long way round, to the right; the arrowhead at the top points the way the ring turns
            var shapes = new List<Vector2[]>(ZumiDraw.Arc(radius, 0.0032f, 90f, 360f, 9));
            shapes.Add(new[] { new Vector2(-0.001f, radius + 0.0055f), new Vector2(-0.001f, radius - 0.0055f), new Vector2(0.0075f, radius) });
            return shapes.ToArray();
        }

        void Remove(ref Card card)
        {
            if (card == null) return;
            if (card.root) Destroy(card.root.gameObject);
            card.parts.Destroy();
            card = null;
        }

        void OnDestroy()
        {
            Remove(ref title);
            Remove(ref hint);
            Remove(ref end);
            Remove(ref openFailed);
            Remove(ref panelMissing);
        }
    }
}
