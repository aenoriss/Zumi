using System;
using System.Collections.Generic;
using Oculus.Interaction.Input;
using UnityEngine;

namespace Zumi
{
    /// <summary>
    /// The reader's control: a round menu over the palm. Its first face is the transport and nothing else: back, pause
    /// or resume, forward, three large buttons. A small petal at the foot of the plate turns it to a second face with
    /// the three settings, each under its name and what it is set to now: Motion (the accents on or off), Room (what
    /// the place does to the real room: full, plain, off) and Re-seat (the seat, and all that is placed around it,
    /// taken again where the head is; the clock keeps its time). The petal brings the first face back, and so does
    /// lowering the hand. Why a second face rather than more buttons on the first: the three transport buttons keep
    /// their size and their place, a finger that misses one cannot change a setting, and the settings get targets as
    /// large as theirs.
    ///
    /// It appears when a hand is held open with its palm toward the face, in view, for a moment (either hand), and
    /// goes when the palm turns away. The other hand chooses: a fingertip poke, or its ray and a pinch. Nothing else
    /// a hand does reaches the clock; a pinch in the air does nothing.
    /// </summary>
    public class ZumiHandMenu : MonoBehaviour
    {
        /// <summary>The palm opens the menu when it points within this angle of the eyes.</summary>
        public const float OpenAngle = 35f;
        /// <summary>An open menu stays until the palm has turned this far from the eyes.</summary>
        public const float CloseAngle = 60f;
        /// <summary>The hand must be within this angle of where the head looks: a hand resting on a lap is not asking.</summary>
        public const float ViewAngle = 40f;
        /// <summary>Seconds the open palm must hold before the menu appears.</summary>
        public const float OpenSeconds = 0.3f;
        /// <summary>Seconds the palm may be away (or the hand lost) before an open menu goes.</summary>
        public const float CloseSeconds = 0.25f;
        // an open finger's tip is about 1.8 times as far from the wrist as its knuckle; a curled one's is nearer
        const float OpenFingerRatio = 1.4f;
        // one pill of three round buttons on each face, the same size and pitch on both; the petal a small disc under
        // the pill; the settings' names under their buttons
        const float LiftMetres = 0.08f, ButtonRadius = 0.018f, Pitch = 0.046f, FollowPerSecond = 18f;
        const float PillWidth = 0.158f, PillHeight = 0.054f, SettingsHeight = 0.086f, RowRise = 0.012f;
        const float PetalRadius = 0.0105f, PetalDrop = 0.062f, LabelCap = 0.0052f, Ring = 0.0012f;
        static readonly Color RingColour = ZumiDraw.Hex(0xD9C7B4);

        [Tooltip("Zumi/Flat: one flat colour, unlit")]
        [SerializeField] Shader flatShader;

        sealed class Item
        {
            public string action;
            /// <summary>The face it is on: false the transport, true the settings, null both.</summary>
            public bool? face;
            public Func<string> fire;
            public ZumiDraw.RoundButton button;
            public TextMesh label;
            public Func<string> state;
            public Material icon;
            public Func<bool> lit;
        }

        ZumiTransport transport;
        ZumiReader reader;
        Hand[] hands = Array.Empty<Hand>();
        Hand owner, candidate;
        float candidateSince, lostSince;
        Transform menu;
        GameObject pauseIcon, playIcon, dotsIcon, returnIcon;
        bool settings;
        float reseatedAt = -1f;
        const float ReseatedSeconds = 2f;
        readonly List<Item> items = new();
        readonly ZumiDraw.Parts parts = new();

        internal Shader FlatShader => flatShader;

        public bool Open => owner != null;
        /// <summary>While on, the menu does not open (the creation flow's menu and scanner own the hands).</summary>
        public bool Suppressed { get; set; }
        /// <summary>Asked first when a button is pressed, with its name; true: the press was taken (the creation flow's
        /// playback skips to its end) and the reader does not see it.</summary>
        public Func<string, bool> Intercept { get; set; }
        /// <summary>"left" or "right" while open; null otherwise.</summary>
        public string OpenHand => owner == null ? null : owner.Handedness == Handedness.Left ? "left" : "right";
        /// <summary>The face on show: "main" (the transport) or "settings"; null while the menu is closed.</summary>
        public string Page => !Open ? null : settings ? "settings" : "main";
        /// <summary>Where the menu is drawn, in world space; meaningful while Open.</summary>
        public Vector3 Position => menu ? menu.position : default;
        /// <summary>The way the menu's face points, in world space (toward the eyes while Open).</summary>
        public Vector3 Facing => menu ? -menu.forward : default;
        /// <summary>The button pressed last: "pause", "resume", "forward", "back"; "settings", "main" (the petal);
        /// "motion_on", "motion_off", "room_full", "room_nograde", "room_off", "reseat"; null before any.</summary>
        public string LastAction { get; private set; }
        public int ActionCount { get; private set; }
        /// <summary>What the settings' face reads under its buttons, in their order; empty on the other face.</summary>
        public IReadOnlyList<string> SettingLabels
        {
            get
            {
                shownLabels.Clear();
                if (Open && settings)
                    foreach (var item in items)
                        if (item.label) shownLabels.Add(item.label.text.Replace('\n', ' '));
                return shownLabels;
            }
        }
        readonly List<string> shownLabels = new();

        public void Bind(ZumiTransport transport, ZumiReader reader)
        {
            this.transport = transport;
            this.reader = reader;
            Build();
        }

        void Update()
        {
            if (transport == null || !Camera.main) return;
            if (hands.Length == 0) hands = FindObjectsByType<Hand>(FindObjectsInactive.Include);
            var head = Camera.main.transform;
            if (Suppressed)
            {
                owner = candidate = null;
                if (menu.gameObject.activeSelf) menu.gameObject.SetActive(false);
                Hints(head);
                return;
            }

            if (owner != null)
            {
                if (Asks(owner, head, CloseAngle, needOpenFingers: false, out _, out _)) lostSince = -1f;
                else if (lostSince < 0f) lostSince = Time.unscaledTime;
                else if (Time.unscaledTime - lostSince >= CloseSeconds) owner = null;
            }
            else
            {
                Hand asking = null;
                foreach (var hand in hands)
                    if (Asks(hand, head, OpenAngle, needOpenFingers: true, out _, out _) && (asking == null || hand == candidate)) asking = hand;
                if (asking != candidate)
                {
                    candidate = asking;
                    candidateSince = Time.unscaledTime;
                }
                else if (candidate != null && Time.unscaledTime - candidateSince >= OpenSeconds)
                {
                    owner = candidate;
                    candidate = null;
                    lostSince = -1f;
                    // it always opens on the transport
                    settings = false;
                    Place(head, snap: true);
                }
            }

            if (Open) everOpened = true;
            Hints(head);
            if (menu.gameObject.activeSelf != Open) menu.gameObject.SetActive(Open);
            if (!Open) return;
            Place(head, snap: false);
            foreach (var item in items)
            {
                // the petal is on both faces
                var shown = item.face == null || item.face == settings;
                if (item.button.transform.gameObject.activeSelf != shown) item.button.transform.gameObject.SetActive(shown);
                if (item.label && item.label.gameObject.activeSelf != shown) item.label.gameObject.SetActive(shown);
            }
            mainPlate.SetActive(!settings);
            settingsPlate.SetActive(settings);
            dotsIcon.SetActive(!settings);
            returnIcon.SetActive(settings);
            pauseIcon.SetActive(transport.Playing);
            playIcon.SetActive(!transport.Playing);
            foreach (var item in items)
            {
                item.button.disc.SetColor("_Color", item.button.Touched ? ZumiDraw.Hover : ZumiDraw.Button);
                if (item.state != null)
                {
                    var text = item.state();
                    if (item.label.text != text) item.label.text = text;
                }
                if (item.lit != null) item.icon.SetColor("_Color", item.lit() ? ZumiDraw.Ink : ZumiDraw.FaintInk);
            }
        }

        // an open hand, tracked, in view, its palm toward the eyes within maxAngle
        static bool Asks(Hand hand, Transform head, float maxAngle, bool needOpenFingers, out Vector3 palm, out Vector3 normal)
        {
            palm = normal = default;
            if (!hand || !hand.isActiveAndEnabled || !hand.IsTrackedDataValid) return false;
            if (!hand.GetJointPose(HandJointId.HandWristRoot, out var wrist) || !hand.GetJointPose(HandJointId.HandIndex1, out var index)
                || !hand.GetJointPose(HandJointId.HandMiddle1, out var middle) || !hand.GetJointPose(HandJointId.HandPinky1, out var pinky)) return false;
            palm = (wrist.position + middle.position) * 0.5f;
            // from the knuckles, not a joint's axes: the same on both hands whatever the skeleton's frame. The cross
            // product points out of the back of a right hand and out of the palm of a left one
            normal = Vector3.Cross(index.position - wrist.position, pinky.position - wrist.position).normalized;
            if (hand.Handedness == Handedness.Right) normal = -normal;
            if (Vector3.Angle(normal, head.position - palm) > maxAngle) return false;
            if (Vector3.Angle(head.forward, palm - head.position) > ViewAngle) return false;
            if (!needOpenFingers) return true;
            if (hand.GetIndexFingerIsPinching()) return false;
            return Extended(hand, wrist.position, HandJointId.HandIndex1, HandJointId.HandIndexTip)
                   && Extended(hand, wrist.position, HandJointId.HandMiddle1, HandJointId.HandMiddleTip)
                   && Extended(hand, wrist.position, HandJointId.HandRing1, HandJointId.HandRingTip);
        }

        static bool Extended(Hand hand, Vector3 wrist, HandJointId knuckle, HandJointId tip) =>
            hand.GetJointPose(knuckle, out var k) && hand.GetJointPose(tip, out var t)
            && Vector3.Distance(t.position, wrist) > OpenFingerRatio * Vector3.Distance(k.position, wrist);

        // over the palm, facing the eyes; it follows the hand smoothly so tracking jitter does not shake the buttons
        void Place(Transform head, bool snap)
        {
            if (!Asks(owner, head, 180f, needOpenFingers: false, out var palm, out var normal) && !snap) return;
            var position = palm + normal * LiftMetres;
            var rotation = Quaternion.LookRotation(position - head.position, Vector3.up);
            var k = snap ? 1f : 1f - Mathf.Exp(-FollowPerSecond * Time.unscaledDeltaTime);
            menu.SetPositionAndRotation(Vector3.Lerp(menu.position, position, k), Quaternion.Slerp(menu.rotation, rotation, k));
        }

        void Fire(Item item)
        {
            if (!Open || (item.face != null && item.face != settings)) return;
            if (Intercept != null && Intercept(item.action))
            {
                LastAction = "intercepted";
                ActionCount++;
                Debug.Log($"[Zumi] menu: {item.action} taken by the creation flow");
                return;
            }
            LastAction = item.fire();
            ActionCount++;
            Debug.Log($"[Zumi] menu: {LastAction}");
        }

        // ---- telling the reader the menu is there ---------------------------------------------------------------
        // While reading, a small Zumi glow sits on the inside of each wrist in view (it pulses a few times the first
        // time, then stays quiet), and until the menu has been opened once a line low in the view says how to open
        // it, beside a little hand that turns its palm toward the reader.

        public const float DotSize = 0.032f, DotPulseSeconds = 0.8f, CoachAhead = 0.62f, CoachBelow = 0.27f, CoachCap = 0.012f;
        public const string CoachLine = "Turn your palm toward you for the menu";
        /// <summary>The menu has been opened at least once (the coach mark is gone for good).</summary>
        public bool EverOpened => everOpened;
        /// <summary>The coach mark is on show.</summary>
        public bool CoachShown => coach && coach.gameObject.activeSelf;
        bool everOpened;
        readonly Dictionary<Hand, (Transform dot, Material material)> dots = new();
        float dotsSince = -1f, coachAlpha;
        Transform coach, coachHand;
        readonly ZumiDraw.Parts coachParts = new() { blended = true, queue = 3600 };

        bool Reading => !Suppressed && Intercept == null && reader != null && !reader.WaitsForBook;

        void Hints(Transform head)
        {
            var reading = Reading;
            // several Hand components feed each hand (raw data, filters): one hint per handedness
            var done = 0;
            foreach (var hand in hands)
            {
                if (!hand) continue;
                var bit = hand.Handedness == Handedness.Left ? 1 : 2;
                if ((done & bit) != 0)
                {
                    if (dots.TryGetValue(hand, out var extra)) extra.dot.gameObject.SetActive(false);
                    continue;
                }
                // any tracked hand the reader can see (wider than the menu's own view check)
                var show = reading && !Open && hand.isActiveAndEnabled && hand.IsTrackedDataValid
                           && hand.GetJointPose(HandJointId.HandWristRoot, out var seen)
                           && Vector3.Angle(head.forward, seen.position - head.position) < 60f;
                if (!dots.TryGetValue(hand, out var dot))
                {
                    if (!show) continue;
                    var m = new Material(ZumiFlowKit.GlowShader) { renderQueue = 3550 };
                    // small: all colour, no white core, so it reads as Zumi and not as a light
                    m.SetFloat("_Core", 0f);
                    dot = (ZumiFlowKit.Card($"Menu hint {hand.Handedness}", null, Vector2.one, m).transform, m);
                    dots[hand] = dot;
                }
                dot.dot.gameObject.SetActive(show);
                if (!show) continue;
                done |= bit;
                // the pulses start the first time a hand is seen while reading
                if (dotsSince < 0f) dotsSince = Time.unscaledTime;
                hand.GetJointPose(HandJointId.HandWristRoot, out var w);
                hand.GetJointPose(HandJointId.HandMiddle1, out var mid);
                hand.GetJointPose(HandJointId.HandIndex1, out var ix);
                hand.GetJointPose(HandJointId.HandPinky1, out var px);
                var palm = (w.position + mid.position) * 0.5f;
                var normal = Vector3.Cross(ix.position - w.position, px.position - w.position).normalized;
                // on the wrist, a little toward the hand, lifted off the skin on whichever side faces the eyes (the
                // inside when the palm is up, the back when it is down), so it is always seen
                var side = Vector3.Dot(normal, head.position - palm) >= 0f ? normal : -normal;
                var at = Vector3.Lerp(w.position, palm, 0.3f) + side * 0.016f;
                dot.dot.SetPositionAndRotation(at, Quaternion.LookRotation(at - head.position, Vector3.up));
                // three slow pulses the first time, then a quiet glow
                var t = (Time.unscaledTime - dotsSince) / DotPulseSeconds;
                var pulse = t < 3f ? Mathf.Sin(t * Mathf.PI) * Mathf.Sin(t * Mathf.PI) : 0f;
                dot.dot.localScale = Vector3.one * DotSize * (1f + 0.45f * pulse);
                dot.material.SetFloat("_Turn", Time.unscaledTime * 0.5f);
                dot.material.SetColor("_Color", new Color(1f, 1f, 1f, 0.75f + 0.25f * pulse));
            }
            // the coach mark
            var wanted = reading && !everOpened;
            if (wanted && !coach) BuildCoach(head);
            if (!coach) return;
            coachAlpha = Mathf.MoveTowards(coachAlpha, wanted && !Open ? 1f : 0f, Time.unscaledDeltaTime / 0.4f);
            coach.gameObject.SetActive(coachAlpha > 0.001f);
            if (!coach.gameObject.activeSelf) return;
            coachParts.SetAlpha(coachAlpha);
            var level = Vector3.ProjectOnPlane(head.forward, Vector3.up).normalized;
            var target = head.position + level * CoachAhead + Vector3.down * CoachBelow;
            var k = 1f - Mathf.Exp(-2.5f * Time.unscaledDeltaTime);
            coach.SetPositionAndRotation(Vector3.Lerp(coach.position, target, k), Quaternion.Slerp(coach.rotation, Quaternion.LookRotation(target - head.position, Vector3.up), k));
            // the little hand turns its palm to the reader and back, slowly
            // never thinner than a quarter, so it reads as a hand at every moment
            var turnK = Mathf.Cos(Time.unscaledTime * 1.8f);
            coachHand.localScale = new Vector3(Mathf.Sign(turnK) * Mathf.Max(0.25f, Mathf.Abs(turnK)), 1f, 1f) * handScale;
        }

        float handScale = 1f;

        void BuildCoach(Transform head)
        {
            coach = new GameObject("Menu coach").transform;
            var level = Vector3.ProjectOnPlane(head.forward, Vector3.up).normalized;
            var at = head.position + level * CoachAhead + Vector3.down * CoachBelow;
            coach.SetPositionAndRotation(at, Quaternion.LookRotation(at - head.position, Vector3.up));
            var textWidth = ZumiDraw.Width(CoachLine, CoachCap);
            var width = textWidth + 0.09f;
            ZumiDraw.Shape(flatShader, coachParts, "Plate", coach, 0f, ZumiDraw.Plate, 0, ZumiDraw.Rounded(width, 0.06f, 0.03f));
            ZumiDraw.Text(flatShader, coachParts, "Line", coach, new Vector3(0.025f, 0f, -0.002f), CoachCap, ZumiDraw.Ink, 2, CoachLine);
            // a small open hand: palm, four fingers, a thumb; a dot of the Zumi colours on its palm
            coachHand = new GameObject("Hand").transform;
            coachHand.SetParent(coach, false);
            coachHand.localPosition = new Vector3(-width / 2f + 0.026f, -0.007f, -0.002f);
            coachHand.localScale = Vector3.one * 1.5f;
            handScale = 1.5f;
            ZumiDraw.Shape(flatShader, coachParts, "Palm", coachHand, 0f, ZumiDraw.SoftInk, 1,
                ZumiDraw.Rounded(0.014f, 0.014f, 0.004f), ZumiDraw.Box(-0.0068f, 0.006f, 0.003f, 0.012f), ZumiDraw.Box(-0.0031f, 0.006f, 0.003f, 0.014f),
                ZumiDraw.Box(0.0006f, 0.006f, 0.003f, 0.013f), ZumiDraw.Box(0.0043f, 0.006f, 0.0027f, 0.01f), ZumiDraw.Box(0.0062f, -0.004f, 0.0075f, 0.003f));
            ZumiDraw.Shape(flatShader, coachParts, "Dot", coachHand, -0.0005f, ZumiDraw.Hex(0xC7A8FF), 2, ZumiDraw.Disc(0.0028f, 16));
            coachAlpha = 0f;
            coachParts.SetAlpha(0f);
        }

        // ---- the menu's objects, built once -------------------------------------------------------------------

        void Build()
        {
            menu = new GameObject("HandMenu").transform;
            menu.gameObject.SetActive(false);
            // the transport's pill, and the settings' taller one (their names under the buttons)
            mainPlate = ZumiDraw.Shape(flatShader, parts, "Plate", menu, 0f, ZumiDraw.Plate, 0, ZumiDraw.Rounded(PillWidth, PillHeight, PillHeight / 2f)).gameObject;
            settingsPlate = ZumiDraw.Shape(flatShader, parts, "Settings plate", menu, 0f, ZumiDraw.Plate, 0,
                ZumiDraw.Moved(ZumiDraw.Rounded(PillWidth, SettingsHeight, 0.026f), new Vector2(0f, RowRise - SettingsHeight / 2f + PillHeight / 2f))).gameObject;

            // seen from the front, +x is the reader's right: back, pause, forward in a row
            var pause = Add(false, "Pause", new Vector2(0f, 0f), ButtonRadius, () =>
            {
                var was = transport.Playing;
                transport.TogglePause();
                return was ? "pause" : "resume";
            });
            pauseIcon = Icon(pause, ZumiDraw.Bars(-0.0055f, 0.0038f), ZumiDraw.Bars(0.0017f, 0.0038f)).gameObject;
            playIcon = Icon(pause, ZumiDraw.Triangle(-0.004f, 0.0095f)).gameObject;
            Icon(Add(false, "Forward", new Vector2(Pitch, 0f), ButtonRadius, () => { transport.Forward(); return "forward"; }), ZumiDraw.Triangle(-0.006f, 0.0085f), ZumiDraw.Bars(0.0035f, 0.0026f));
            Icon(Add(false, "Back", new Vector2(-Pitch, 0f), ButtonRadius, () => { transport.Back(); return "back"; }), ZumiDraw.Triangle(0.006f, -0.0085f), ZumiDraw.Bars(-0.0061f, 0.0026f));

            // the petal: three dots to the settings, an arrow back to the transport
            var petal = Add(null, "Petal", new Vector2(0f, -PetalDrop), PetalRadius, () =>
            {
                settings = !settings;
                return settings ? "settings" : "main";
            });
            dotsIcon = Icon(petal, ZumiDraw.Moved(ZumiDraw.Disc(0.0013f, 10), new Vector2(-0.0042f, 0f)), ZumiDraw.Disc(0.0013f, 10), ZumiDraw.Moved(ZumiDraw.Disc(0.0013f, 10), new Vector2(0.0042f, 0f))).gameObject;
            returnIcon = Icon(petal, new[] { new Vector2(0.0028f, -0.0045f), new Vector2(0.0028f, 0.0045f), new Vector2(-0.0045f, 0f) }).gameObject;

            // the settings: the same row of three, each with its name and what it is set to
            var motion = Add(true, "Motion", new Vector2(-Pitch, RowRise), ButtonRadius, () =>
            {
                reader.SetMotion(!reader.MotionEnabled);
                return reader.MotionEnabled ? "motion_on" : "motion_off";
            });
            // a ball and the three lines it leaves behind
            Lit(motion, () => reader.MotionEnabled, ZumiDraw.Moved(ZumiDraw.Disc(0.0042f, 20), new Vector2(0.005f, 0f)),
                ZumiDraw.Box(-0.0095f, 0.0026f, 0.0075f, 0.0015f), ZumiDraw.Box(-0.0115f, -0.00075f, 0.0095f, 0.0015f), ZumiDraw.Box(-0.0095f, -0.0041f, 0.0075f, 0.0015f));
            Label(motion, () => reader.MotionEnabled ? "Motion\non" : "Motion\noff");

            var room = Add(true, "Room", new Vector2(0f, RowRise), ButtonRadius, () =>
            {
                reader.CycleRoomEffects();
                return "room_" + reader.RoomEffects.ToString().ToLowerInvariant();
            });
            // a window: its frame and its cross
            Lit(room, () => reader.RoomEffects != RoomEffects.Off, ZumiDraw.Box(-0.0085f, 0.006f, 0.017f, 0.0016f), ZumiDraw.Box(-0.0085f, -0.0076f, 0.017f, 0.0016f),
                ZumiDraw.Box(-0.0085f, -0.0076f, 0.0016f, 0.0152f), ZumiDraw.Box(0.0069f, -0.0076f, 0.0016f, 0.0152f), ZumiDraw.Box(-0.0006f, -0.0076f, 0.0012f, 0.0152f), ZumiDraw.Box(-0.0085f, -0.0006f, 0.017f, 0.0012f));
            Label(room, () => reader.RoomEffects switch { RoomEffects.Full => "Room\nfull", RoomEffects.NoGrade => "Room\nplain", _ => "Room\noff" });

            var reseat = Add(true, "Reseat", new Vector2(Pitch, RowRise), ButtonRadius, () =>
            {
                reader.Reseat();
                reseatedAt = Time.unscaledTime;
                return "reseat";
            });
            // a ring with its middle marked: here
            var mark = new List<Vector2[]>(ZumiDraw.Arc(0.0075f, 0.0018f, 0f, 360f, 20)) { ZumiDraw.Disc(0.0026f, 14) };
            Lit(reseat, null, mark.ToArray());
            // it has no setting to show: it says that it was done, for a moment
            Label(reseat, () => reseatedAt >= 0f && Time.unscaledTime - reseatedAt < ReseatedSeconds ? "Re-seat\ndone" : "Re-seat\nhere");

            // Reset demo (the creation flow forgets the comic it made, so the demo can be filmed again): a small disc
            // beside the petal, on the settings face only
            var reset = Add(true, "Reset", new Vector2(Pitch, -PetalDrop), PetalRadius, () =>
            {
                ResetDemo?.Invoke();
                resetAt = Time.unscaledTime;
                return "reset_demo";
            });
            Icon(reset, new List<Vector2[]>(ZumiDraw.Arc(0.0052f, 0.0013f, 40f, 320f, 14))
            {
                new[] { new Vector2(0.0058f, 0.0016f), new Vector2(0.0032f, 0.0052f), new Vector2(0.0072f, 0.0058f) },
            }.ToArray());
            reset.state = () => resetAt >= 0f && Time.unscaledTime - resetAt < ReseatedSeconds ? "Demo\nreset" : "Reset\ndemo";
            reset.label = ZumiDraw.Text(flatShader, parts, "Reset label", menu, reset.button.transform.localPosition + new Vector3(0f, -PetalRadius - 0.0105f, -0.001f), LabelCap, ZumiDraw.SoftInk, 3, reset.state());

            // Record scan samples (for tuning the scanner's detector): a small disc left of the petal, a dot lit
            // while it is on
            var record = Add(true, "Record", new Vector2(-Pitch, -PetalDrop), PetalRadius, () =>
            {
                ZumiScanner.RecordSamples = !ZumiScanner.RecordSamples;
                return ZumiScanner.RecordSamples ? "record_on" : "record_off";
            });
            Lit(record, () => ZumiScanner.RecordSamples, ZumiDraw.Disc(0.0042f, 20));
            record.state = () => ZumiScanner.RecordSamples ? "Record\nscans on" : "Record\nscans off";
            record.label = ZumiDraw.Text(flatShader, parts, "Record label", menu, record.button.transform.localPosition + new Vector3(0f, -PetalRadius - 0.0105f, -0.001f), LabelCap, ZumiDraw.SoftInk, 3, record.state());
        }

        /// <summary>The settings face's "Reset demo" (set by the creation flow); null: the button does nothing.</summary>
        public Action ResetDemo { get; set; }
        float resetAt = -1f;

        GameObject mainPlate, settingsPlate;

        Item Add(bool? face, string name, Vector2 at, float radius, Func<string> fire)
        {
            var item = new Item { action = name, face = face, fire = fire };
            item.button = ZumiDraw.Round(flatShader, parts, name, menu, at, radius, 1, () => Fire(item));
            // a thin ring: the button reads as one, on the cream plate
            ZumiDraw.Shape(flatShader, parts, "Ring", item.button.transform, -0.0005f, RingColour, 2, ZumiDraw.Arc(radius, Ring, 0f, 360f, 40));
            items.Add(item);
            return item;
        }

        Transform Icon(Item item, params Vector2[][] polygons) =>
            ZumiDraw.Shape(flatShader, parts, "Icon", item.button.transform, -0.002f, ZumiDraw.Ink, 3, polygons);

        // an icon that is ink while its setting is on and faint while it is off
        void Lit(Item item, Func<bool> lit, params Vector2[][] polygons)
        {
            item.icon = Icon(item, polygons).GetComponent<MeshRenderer>().sharedMaterial;
            item.lit = lit;
        }

        void Label(Item item, Func<string> state)
        {
            item.state = state;
            var at = item.button.transform.localPosition + new Vector3(0f, -ButtonRadius - 0.0125f, -0.001f);
            item.label = ZumiDraw.Text(flatShader, parts, $"{item.action} label", menu, at, LabelCap, ZumiDraw.SoftInk, 3, state());
        }

        void OnDestroy()
        {
            if (menu) Destroy(menu.gameObject);
            parts.Destroy();
            if (coach) Destroy(coach.gameObject);
            coachParts.Destroy();
            foreach (var (dot, material) in dots.Values)
            {
                if (dot) Destroy(dot.gameObject);
                Destroy(material);
            }
        }
    }
}
