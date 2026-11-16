using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.XR;
using static System.FormattableString;

namespace Zumi
{
    /// <summary>
    /// The reader: opens one episode, owns its clock and hands both to the parts that show it (the panel, the voices,
    /// the music, the place through the wall with its props and its light, the cards). The episode starts playing by
    /// itself once its title has had its moment, its first panel is drawn, the opening's music is decoded and the
    /// opening's place is fitted; it stops at its end, says so (EpisodeEnded) and can be played again (Replay). When
    /// the system takes the app away from the reader (the headset comes off, the system menu opens, the app is
    /// paused) the clock pauses, and resumes only if it was playing. An episode that cannot be opened is a state
    /// (SourceState Failed, a card says so), not a crash. The reader's settings are kept between launches.
    /// </summary>
    [RequireComponent(typeof(ZumiPanelPresenter), typeof(ZumiHandMenu))]
    [RequireComponent(typeof(ZumiPlaces), typeof(ZumiRoomLight))]
    public class ZumiReader : MonoBehaviour
    {
        [Tooltip("The episode to open: its path under StreamingAssets")]
        [SerializeField] string episodeFile = "Episodes/dan-buck.zumi";

        IEpisodeSource source;
        ZumiDspClock clock;
        ZumiTimeline timeline;
        ZumiTransport transport;
        ZumiPanelPresenter presenter;
        ZumiMusic music;
        ZumiPlaces places;
        ZumiCards cards;
        ZumiSeat seat;
        bool autoStarted;
        double openedAt;
        // what currently keeps the app from the reader, and whether the clock goes on when all of it has passed
        readonly HashSet<string> interruptions = new();
        bool resumeAfterInterruption;

        public IEpisodeClock Clock => clock;
        /// <summary>The episode file, once open: the creation flow reads a panel's scene and its sounds from it.</summary>
        public IEpisodeSource Source => source;
        /// <summary>The episode is open but waits for a book to be opened (ZumiFlow): no seat, nothing shown, no clock.</summary>
        public bool WaitsForBook { get; private set; }
        public ZumiTimeline Timeline => timeline;
        /// <summary>Raised each time the clock reaches the episode's end. What comes after an episode (the next
        /// chapter, the library) hangs on this.</summary>
        public event Action EpisodeEnded;

        // read-only state for tests and tools
        public string SourceState => (source?.State ?? EpisodeSourceState.Closed).ToString();
        public string SourceError => source?.Error;
        /// <summary>The episode's file, without its folders.</summary>
        public string EpisodeName => Path.GetFileName(episodeFile);
        public double ClockTime => clock?.Time ?? 0d;
        public bool Playing => clock != null && clock.Playing;
        public double Duration => clock?.Duration ?? 0d;
        /// <summary>Seconds the clock has gained on real time since it last started or jumped (ZumiDspClock.WallDrift).</summary>
        public double ClockDrift => clock?.WallDrift ?? 0d;
        /// <summary>The panel the clock is on, whether or not it is drawn yet.</summary>
        public string CurrentPanelId => clock != null ? timeline.IdAt(clock.Time) : null;
        /// <summary>The episode has begun (or begun again): everything it waits for was ready and the clock was started.</summary>
        public bool Started => autoStarted;
        public bool Ended { get; private set; }
        /// <summary>Seconds since the clock ended; 0 while it has not.</summary>
        public double EndedFor => clock?.EndedFor ?? 0d;
        /// <summary>How many times the episode ended, and how many times it was begun again from its end card.</summary>
        public int EndCount { get; private set; }
        public int ReplayCount { get; private set; }
        public bool Interrupted => interruptions.Count > 0;
        /// <summary>Why the clock last stopped or went on: "autoplay", "menu", "keys", "system", "end", "replay".</summary>
        public string ClockCause { get; private set; }
        /// <summary>In the editor, Space and the arrow keys reach the transport. A test run switches this off, so a key
        /// pressed at the machine meanwhile cannot move the clock under it.</summary>
        public bool EditorKeys { get; set; } = true;
        /// <summary>Seconds from this component's start until the first panel was drawn; -1 before that.</summary>
        public float FirstPanelSeconds { get; private set; } = -1f;

        // the settings the hand menu shows and changes
        public bool MotionEnabled => presenter.MotionEnabled;
        public RoomEffects RoomEffects => places.RoomEffects;
        public int Seatings => seat.Seatings;

        async void Start()
        {
            seat = Part<ZumiSeat>();
            presenter = GetComponent<ZumiPanelPresenter>();
            places = GetComponent<ZumiPlaces>();
            cards = Part<ZumiCards>();
            // what the reader chose before; a setting never touched keeps the scene's value
            if (ZumiSettings.TryMotion(out var motion)) presenter.MotionEnabled = motion;
            if (ZumiSettings.TryRoomEffects(out var effects)) places.RoomEffects = effects;
            openedAt = Time.realtimeSinceStartupAsDouble;
            source = new ZumiShippedEpisode(episodeFile);
            await source.Open(destroyCancellationToken);
            if (!this) return;
            if (source.State != EpisodeSourceState.Ready)
            {
                // the cards say so; nothing else of the reader starts
                Debug.LogWarning($"[Zumi] reader: the episode cannot be opened: {source.Error}");
                return;
            }
            var manifest = source.Manifest;
            timeline = new ZumiTimeline(manifest);
            clock = new ZumiDspClock(timeline.Duration);
            clock.Ended += () =>
            {
                Ended = true;
                EndCount++;
                ClockCause = "end";
                Debug.Log(Invariant($"[Zumi] reader: the episode ended at {clock.Time:F2} s"));
                EpisodeEnded?.Invoke();
            };
            transport = new ZumiTransport(clock, timeline, cause => ClockCause = cause);
            presenter.Bind(source, timeline, clock);
            Part<ZumiVoices>().Bind(source, timeline, clock, presenter);
            music = Part<ZumiMusic>();
            music.Bind(source, manifest, clock);
            places.Bind(source, manifest, clock);
            GetComponent<ZumiHandMenu>().Bind(transport, this);
            cards.SetTitles(manifest.series?.id, manifest.series?.title, manifest.episode?.id, manifest.episode?.title);
            cards.Arm();
            Debug.Log(Invariant($"[Zumi] reader: {manifest.series?.title} · {timeline.Panels.Count} panels, {timeline.Duration:F2} s, opened in {Time.realtimeSinceStartupAsDouble - openedAt:F2} s"));
        }

        // the parts that show and sound the episode live on this object; a scene saved before one existed gets it here
        T Part<T>() where T : Component => TryGetComponent<T>(out var part) ? part : gameObject.AddComponent<T>();

        /// <summary>Jumps the clock to t seconds (clamped to the episode); playing or paused stays as it was. The
        /// hand menu only steps by panels: this is for tools and tests, and for a scrubber later.</summary>
        public void Seek(double t) => clock?.Seek(t);

        /// <summary>From the top: the clock goes to 0 and the episode begins as it did the first time, once its
        /// opening is ready again.</summary>
        public void Replay()
        {
            if (clock == null) return;
            ReplayCount++;
            clock.Pause();
            clock.Seek(0d);
            ClockCause = "replay";
            autoStarted = false;
            cards.Arm();
            Debug.Log("[Zumi] reader: replay");
        }

        /// <summary>Called before Start by the creation flow: the episode opens, but nothing of it shows and the seat is
        /// not taken until Begin.</summary>
        public void HoldForBook()
        {
            WaitsForBook = true;
            Part<ZumiSeat>().Held = true;
        }

        /// <summary>A book was opened: the seat is taken where the head is now and the episode begins from its title.</summary>
        public void Begin()
        {
            WaitsForBook = false;
            var s = Part<ZumiSeat>();
            s.Held = false;
            s.Reseat();
            if (clock != null && !autoStarted) cards.Arm();
            Debug.Log("[Zumi] reader: a book was opened, the episode begins");
        }

        /// <summary>The accents on or off, kept between launches.</summary>
        public void SetMotion(bool on)
        {
            presenter.MotionEnabled = on;
            ZumiSettings.SaveMotion(on);
        }

        /// <summary>The next of Full, NoGrade, Off, kept between launches.</summary>
        public void CycleRoomEffects()
        {
            places.RoomEffects = (RoomEffects)(((int)places.RoomEffects + 1) % 3);
            ZumiSettings.SaveRoomEffects(places.RoomEffects);
        }

        /// <summary>The seat taken again where the head is now; the panel, the key wall, the place and its props follow
        /// it (ZumiRoom works the room out again). The clock keeps its time.</summary>
        public void Reseat() => seat.Reseat();

        void Update()
        {
            if (clock == null) return;
            clock.Tick();
            if (clock.Time < clock.Duration) Ended = false;
            // once the title has had its moment, the first panel is drawn, the music of the opening is decoded and the
            // opening's place is fitted to the room: nothing joins late
            if (!autoStarted && !WaitsForBook && seat.Taken && cards.TitleReady && presenter.CurrentSettled && music.ReadyAt(clock.Time) && places.ReadyAt(clock.Time))
            {
                autoStarted = true;
                if (FirstPanelSeconds < 0f)
                {
                    FirstPanelSeconds = (float)(Time.realtimeSinceStartupAsDouble - openedAt);
                    Debug.Log(Invariant($"[Zumi] reader: first panel {presenter.ShownPanelId} drawn after {FirstPanelSeconds:F2} s, playing"));
                }
                if (Interrupted) resumeAfterInterruption = true;
                else
                {
                    ClockCause = "autoplay";
                    clock.Play();
                }
            }
#if UNITY_EDITOR && ENABLE_INPUT_SYSTEM
            var keys = UnityEngine.InputSystem.Keyboard.current;
            if (keys == null || !EditorKeys) return;
            if (keys.spaceKey.wasPressedThisFrame) Key("space", transport.TogglePause);
            if (keys.rightArrowKey.wasPressedThisFrame) Key("right", transport.Forward);
            if (keys.leftArrowKey.wasPressedThisFrame) Key("left", transport.Back);
#endif
        }

#if UNITY_EDITOR && ENABLE_INPUT_SYSTEM
        // the editor's keys reach the clock like the menu does; said in the log so a run that was touched shows it
        void Key(string key, Action act)
        {
            act();
            ClockCause = "keys";
            Debug.Log($"[Zumi] reader: key {key}");
        }
#endif

        void Interrupt(string by)
        {
            if (!interruptions.Add(by) || interruptions.Count > 1 || clock == null) return;
            resumeAfterInterruption = clock.Playing;
            clock.Pause();
            ClockCause = "system";
            Debug.Log($"[Zumi] reader: held by the system ({by})");
        }

        void Restore(string from)
        {
            if (!interruptions.Remove(from) || interruptions.Count > 0 || !resumeAfterInterruption) return;
            resumeAfterInterruption = false;
            ClockCause = "system";
            clock?.Play();
        }

        // Unity's own pause: the app goes to the background, the headset sleeps
        void OnApplicationPause(bool paused)
        {
            if (paused) Interrupt("pause");
            else Restore("pause");
        }

        // Meta's: the system menu or a dialog over the app, and the headset taken off. Only with a headset: without
        // one OVRManager reports no focus and nobody present. Unity's OnApplicationFocus is left out on purpose: on
        // the headset it repeats InputFocusLost, and in the editor it fires whenever another window is clicked
        void OnInputFocusLost() => InterruptOnDevice("focus");
        void OnInputFocusAcquired() => Restore("focus");
        void OnHmdUnmounted() => InterruptOnDevice("unmounted");
        void OnHmdMounted() => Restore("unmounted");

        void InterruptOnDevice(string by)
        {
            if (XRSettings.isDeviceActive) Interrupt(by);
        }

        void OnEnable()
        {
            OVRManager.InputFocusLost += OnInputFocusLost;
            OVRManager.InputFocusAcquired += OnInputFocusAcquired;
            OVRManager.HMDUnmounted += OnHmdUnmounted;
            OVRManager.HMDMounted += OnHmdMounted;
        }

        void OnDisable()
        {
            OVRManager.InputFocusLost -= OnInputFocusLost;
            OVRManager.InputFocusAcquired -= OnInputFocusAcquired;
            OVRManager.HMDUnmounted -= OnHmdUnmounted;
            OVRManager.HMDMounted -= OnHmdMounted;
        }

        void OnDestroy() => source?.Dispose();
    }
}
