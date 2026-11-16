using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using Zumi.Format;
using static System.FormattableString;

namespace Zumi
{
    /// <summary>
    /// The voiced bubbles' clips, each started on the episode clock to the sample and heard from the card that says
    /// it. A panel's clips are read with the panel and the next panel's ahead, as the presenter does with scenes.
    /// This reads the clock and never moves it: every frame it asks the clock at which audio-engine time each line's
    /// first sample falls, and a line whose answer changed (a pause, a resume, a seek) is stopped and scheduled
    /// again from there, at the sample the clock is on. So nothing here knows what a seek is.
    /// A line said by a card of another panel, or by someone off-panel, has no card here: it comes from the panel's
    /// middle.
    /// </summary>
    public class ZumiVoices : MonoBehaviour
    {
        /// <summary>A line is handed to the audio engine this long before its first sample.</summary>
        public const double ScheduleAheadSeconds = 1d;
        /// <summary>A line that starts in its middle (a resume, a seek) starts this many audio buffers from now: the
        /// engine cannot start a sound inside the buffer it is already mixing.</summary>
        public const int LeadBuffers = 2;
        /// <summary>With less than this left of a line, it is not started.</summary>
        public const double MinTailSeconds = 0.05;
        const int StartLogLength = 64;

        sealed class Voice
        {
            public string key, panelId, card;
            public double start;
            public AudioClip clip;
            public AudioSource source;
            // the audio-engine time its first sample was scheduled for, and the one it really starts at (later than
            // that when it starts in its middle)
            public bool armed, measured, atCard;
            public double armedZero, startDsp;
            public int startSample;
            public int pausedSample = -1;
            public double pausedClock;
        }

        sealed class PanelVoices
        {
            public int index;
            public readonly List<Voice> voices = new();
            public CancellationTokenSource loading = new();
        }

        IEpisodeSource source;
        ZumiTimeline timeline;
        IEpisodeClock clock;
        ZumiPanelPresenter presenter;
        Transform holder;
        bool metaSpatializer;
        readonly List<PanelVoices> panels = new();
        readonly List<string> playing = new(), startLog = new(), failed = new();

        // ---- read-only state for tests and tools ----------------------------------------------------------------

        /// <summary>The lines heard now, as "panel/bubble": started, not over, the clock playing.</summary>
        public IReadOnlyList<string> PlayingBubbleIds => playing;
        public string PlayingBubbleId => playing.Count > 0 ? playing[0] : null;
        /// <summary>Where the line heard now comes from, in world space.</summary>
        public Vector3 PlayingPosition { get; private set; }
        /// <summary>Whether the line heard now comes from its card (true) or the panel's middle.</summary>
        public bool PlayingAtCard { get; private set; }
        /// <summary>The line that started last, and how far its sound was from the clock when first heard, in
        /// milliseconds: where the clip was, less where the clock says it should be. Positive: ahead of the clock.</summary>
        public string LastStartedBubbleId { get; private set; }
        public float LastStartErrorMs { get; private set; }
        /// <summary>Seconds into its clip the line that started last began at: 0 for a line heard from its start.</summary>
        public float LastStartOffsetSeconds { get; private set; }
        /// <summary>Every start so far, oldest first (the last 64): "panel/bubble error_ms from offset_s".</summary>
        public IReadOnlyList<string> StartLog => startLog;
        /// <summary>Lines that went on after a pause from the sample they stopped on. Each then runs the engine's
        /// start lead behind the clock (its entry in StartLog says how far).</summary>
        public int Resumes { get; private set; }
        /// <summary>The voiced lines whose clip is missing or cannot be decoded, as "panel/bubble", since the episode
        /// opened: each is shown as timed text only.</summary>
        public IReadOnlyList<string> FailedBubbleIds => failed;
        public int LoadedClipCount { get; private set; }
        /// <summary>Bytes of decoded samples held now (32-bit floats).</summary>
        public long LoadedClipBytes { get; private set; }
        /// <summary>"Meta XR Audio" when its spatializer renders the voices; "Unity" for Unity's own 3D panning.</summary>
        public string Spatializer => metaSpatializer ? "Meta XR Audio" : "Unity";

        public void Bind(IEpisodeSource source, ZumiTimeline timeline, IEpisodeClock clock, ZumiPanelPresenter presenter)
        {
            this.source = source;
            this.timeline = timeline;
            this.clock = clock;
            this.presenter = presenter;
            holder = new GameObject("Voices").transform;
            holder.SetParent(transform, false);
            metaSpatializer = AudioSettings.GetSpatializerPluginName() == "Meta XR Audio";
        }

        void Update()
        {
            if (clock == null) return;
            var current = timeline.IndexAt(clock.Time);
            var last = Mathf.Min(timeline.Panels.Count - 1, current + ZumiPanelPresenter.PrefetchAhead);
            for (var i = panels.Count - 1; i >= 0; i--)
                if (panels[i].index < current || panels[i].index > last) Drop(panels[i]);
            for (var i = current; i >= 0 && i <= last; i++)
                if (!panels.Exists(p => p.index == i)) Load(i);

            AudioSettings.GetDSPBufferSize(out var buffer, out _);
            var lead = (double)LeadBuffers * buffer / AudioSettings.outputSampleRate;
            var now = AudioSettings.dspTime;
            playing.Clear();
            foreach (var panel in panels)
                foreach (var voice in panel.voices)
                    if (voice.clip) Tick(voice, now, lead);
        }

        void Tick(Voice voice, double now, double lead)
        {
            var at = presenter.PanelCentre;
            voice.atCard = voice.card != null && presenter.TryCardCentre(voice.panelId, voice.card, out at);
            voice.source.transform.position = voice.atCard ? at : presenter.PanelCentre;

            var rate = voice.clip.frequency;
            var length = (double)voice.clip.samples / rate;
            // the audio-engine time of the line's first sample, as the clock has it now
            var zero = clock.DspTimeAt(voice.start);
            var wanted = clock.Playing && now < zero + length - MinTailSeconds && zero - now < ScheduleAheadSeconds;
            if (!wanted)
            {
                if (!voice.armed) return;
                if (now >= voice.startDsp && voice.source.isPlaying)
                {
                    voice.pausedSample = voice.source.timeSamples;
                    voice.pausedClock = clock.Time;
                }
                voice.source.Stop();
                voice.armed = false;
                return;
            }
            if (!voice.armed || Math.Abs(voice.armedZero - zero) > 0.0005)
            {
                voice.source.Stop();
                voice.startDsp = Math.Max(zero, now + lead);
                voice.startSample = Math.Clamp((int)Math.Round((voice.startDsp - zero) * rate), 0, voice.clip.samples - 1);
                // a resume (the clock is where the line stopped): on from the very sample it stopped on, no word is
                // clipped. The engine needs the lead to start, so this one line then runs that far behind the clock
                if (voice.pausedSample >= 0 && Math.Abs(clock.Time - voice.pausedClock) < 1e-3)
                {
                    voice.startSample = voice.pausedSample;
                    Resumes++;
                }
                voice.source.timeSamples = voice.startSample;
                voice.source.PlayScheduled(voice.startDsp);
                voice.pausedSample = -1;
                voice.armed = true;
                voice.armedZero = zero;
                voice.measured = false;
                return;
            }
            if (now < voice.startDsp || !voice.source.isPlaying) return;
            playing.Add(voice.key);
            PlayingPosition = voice.source.transform.position;
            PlayingAtCard = voice.atCard;
            if (voice.measured || voice.source.timeSamples <= voice.startSample) return;
            voice.measured = true;
            LastStartedBubbleId = voice.key;
            LastStartErrorMs = (float)(((double)voice.source.timeSamples / rate - (clock.Time - voice.start)) * 1000d);
            LastStartOffsetSeconds = (float)voice.startSample / rate;
            if (startLog.Count >= StartLogLength) startLog.RemoveAt(0);
            startLog.Add(Invariant($"{voice.key} {LastStartErrorMs:+0.00;-0.00} ms from {(double)voice.startSample / rate:F2} s"));
            Debug.Log(Invariant($"[Zumi] voice: {voice.key} at {clock.Time:F2} s, {LastStartErrorMs:+0.00;-0.00} ms off the clock, from {(voice.atCard ? voice.card : "the panel's middle")}"));
        }

        void Load(int index)
        {
            var panel = source.Manifest.panels[index];
            var loaded = new PanelVoices { index = index };
            panels.Add(loaded);
            foreach (var bubble in panel.bubbles)
            {
                if (string.IsNullOrEmpty(bubble.audio)) continue;
                var voice = new Voice
                {
                    key = $"{panel.id}/{bubble.id}",
                    panelId = panel.id,
                    start = bubble.startTime ?? timeline.Panels[index].start + bubble.startOffset,
                };
                // only a card of this very panel has a place here
                if (bubble.TrySpeakerCard(panel.id, out var cardPanel, out var card) && cardPanel == panel.id) voice.card = card;
                loaded.voices.Add(voice);
                Read(loaded, voice, bubble.audio);
            }
        }

        async void Read(PanelVoices panel, Voice voice, string path)
        {
            var cancel = panel.loading.Token;
            try
            {
                var file = await source.Read(path, cancel);
                if (file == null) throw new InvalidOperationException($"{path} is not in the episode");
                var wav = await Task.Run(() => ZumiWav.Read(file), cancel);
                if (!this || cancel.IsCancellationRequested) return;
                voice.clip = AudioClip.Create(voice.key, wav.frames, 1, wav.sampleRate, false);
                voice.clip.SetData(wav.samples[0], 0);
                var go = new GameObject($"Voice {voice.key}");
                go.transform.SetParent(holder, false);
                voice.source = go.AddComponent<AudioSource>();
                voice.source.clip = voice.clip;
                voice.source.playOnAwake = false;
                voice.source.spatialBlend = 1f;
                voice.source.dopplerLevel = 0f;
                // full level out to the panel, falling off beyond it
                voice.source.rolloffMode = AudioRolloffMode.Logarithmic;
                voice.source.minDistance = ZumiPanelPresenter.ReadingDistance;
                voice.source.maxDistance = 10f;
                if (metaSpatializer)
                {
                    voice.source.spatialize = true;
                    go.AddComponent<MetaXRAudioSource>();
                }
                LoadedClipCount++;
                LoadedClipBytes += (long)wav.frames * sizeof(float);
            }
            catch (OperationCanceledException) { }
            catch (Exception e)
            {
                // the line is then what an unvoiced line is: its balloon, at its time
                if (!failed.Contains(voice.key)) failed.Add(voice.key);
                Debug.LogWarning($"[Zumi] voice: {voice.key} has no sound ({e.Message}); the line is shown as timed text only");
            }
        }

        void Drop(PanelVoices panel)
        {
            panel.loading.Cancel();
            panel.loading.Dispose();
            foreach (var voice in panel.voices)
            {
                if (!voice.clip) continue;
                LoadedClipCount--;
                LoadedClipBytes -= (long)voice.clip.samples * sizeof(float);
                if (voice.source) Destroy(voice.source.gameObject);
                Destroy(voice.clip);
            }
            panels.Remove(panel);
        }

        void OnDestroy()
        {
            foreach (var panel in panels.ToArray()) Drop(panel);
        }
    }
}
