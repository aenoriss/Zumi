using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;
using Zumi.Format;

namespace Zumi
{
    /// <summary>
    /// The episode's music: every track of episode.music as a loop whose level is the score's envelope at the
    /// clock's time and nothing else (the envelope already holds the ducking under voices, the fades and the
    /// crossfades: nothing is ducked here). A track plays where the format's rule says it is at that time
    /// (Score.PositionAt), so a seek lands where straight play would be. This reads the clock and never moves it.
    /// Where it sits: there is no room model yet, so the score's placement is laid out around the seat at the
    /// distances below: "wide" is the file's left and right channels from two points to the reader's left and right,
    /// "point" both channels from one point in the placement's direction.
    /// A track is decoded only around the stretches where it sounds, so the four are never all in memory.
    /// </summary>
    public class ZumiMusic : MonoBehaviour
    {
        /// <summary>A playing track further than this from where the clock says it should be is put back (the
        /// browser viewer's tolerance).</summary>
        public const float ResyncSeconds = 0.5f;
        /// <summary>wide: metres from the seat to each of the two points, and their angle to the left and right of
        /// straight ahead.</summary>
        public const float WideDistance = 2f, WideAzimuthDegrees = 70f;
        /// <summary>point: metres from the seat to the point.</summary>
        public const float PointDistance = 2f;
        /// <summary>A track is decoded when it will sound within this many seconds.</summary>
        public const double LoadAheadSeconds = 10d;
        /// <summary>A silent track is freed when it will not sound again within this many seconds.</summary>
        public const double UnloadBeyondSeconds = 30d;
        /// <summary>A track starts this many audio buffers from now (ZumiVoices.LeadBuffers).</summary>
        public const int LeadBuffers = 2;

        internal enum Load { None, Reading, Ready, Failed }

        /// <summary>One track's state, read live from its sound sources.</summary>
        public sealed class Track
        {
            internal MusicTrack info;
            internal List<List<float>> knots;
            internal Load load;
            internal AudioClip[] clips;
            internal readonly AudioSource[] sources = new AudioSource[2];
            internal bool started, point;
            internal double startDsp;
            internal float duration;

            public string Id => info.id;
            public bool Loaded => load == Load.Ready;
            /// <summary>The level it is played at now: its sources' volume (in "point" the two channels share one
            /// point at half each, which is this level).</summary>
            public float Gain => sources[0] ? sources[0].volume * (point ? 2f : 1f) : 0f;
            /// <summary>Heard now: playing, above the format's silence.</summary>
            public bool Audible => started && sources[0].isPlaying && AudioSettings.dspTime >= startDsp && Gain > Score.Silent;
            /// <summary>Seconds into its file it is playing at; -1 when not playing.</summary>
            public float Position => started && AudioSettings.dspTime >= startDsp ? sources[0].time : -1f;
            /// <summary>Seconds its playing position is from where the clock says it should be, as last checked.</summary>
            public float PositionError { get; internal set; }
            /// <summary>Bytes of decoded samples held now (32-bit floats).</summary>
            public long Bytes => Loaded ? (long)clips[0].samples * clips.Length * sizeof(float) : 0L;
        }

        IEpisodeSource source;
        IEpisodeClock clock;
        Score score;
        bool metaSpatializer;
        readonly List<Track> tracks = new();
        readonly List<string> audible = new(), loaded = new(), failed = new();

        // ---- read-only state for tests and tools ----------------------------------------------------------------

        /// <summary>In the order of episode.music.</summary>
        public IReadOnlyList<Track> Tracks => tracks;
        public IReadOnlyList<string> AudibleTrackIds
        {
            get
            {
                audible.Clear();
                foreach (var track in tracks)
                    if (track.Audible) audible.Add(track.Id);
                return audible;
            }
        }
        public IReadOnlyList<string> LoadedTrackIds
        {
            get
            {
                loaded.Clear();
                foreach (var track in tracks)
                    if (track.Loaded) loaded.Add(track.Id);
                return loaded;
            }
        }
        /// <summary>The tracks whose file is missing or cannot be decoded: silent for the whole episode.</summary>
        public IReadOnlyList<string> FailedTrackIds
        {
            get
            {
                failed.Clear();
                foreach (var track in tracks)
                    if (track.load == Load.Failed) failed.Add(track.Id);
                return failed;
            }
        }
        public long LoadedBytes
        {
            get
            {
                var bytes = 0L;
                foreach (var track in tracks) bytes += track.Bytes;
                return bytes;
            }
        }
        /// <summary>The most decoded samples held at once so far, in bytes.</summary>
        public long PeakLoadedBytes { get; private set; }
        /// <summary>"wide" or "point": how the music sits around the seat now.</summary>
        public string Placement { get; private set; } = "wide";
        /// <summary>The largest gap, over the tracks, between the level a track is played at and the envelope at the
        /// clock's time, both read now.</summary>
        public float GainError
        {
            get
            {
                var worst = 0f;
                if (clock != null)
                    foreach (var track in tracks)
                        if (track.Loaded) worst = Mathf.Max(worst, Mathf.Abs(track.Gain - Score.GainAt(track.knots, (float)clock.Time)));
                return worst;
            }
        }

        public void Bind(IEpisodeSource source, ZumiManifest manifest, IEpisodeClock clock)
        {
            this.source = source;
            this.clock = clock;
            score = manifest.episode?.score;
            metaSpatializer = AudioSettings.GetSpatializerPluginName() == "Meta XR Audio";
            // without a score a file is hand-made (musicCue): the pipeline's files all carry one
            if (score == null) return;
            foreach (var info in manifest.episode.music)
                if (score.envelope.TryGetValue(info.id, out var knots) && knots.Count > 0)
                    tracks.Add(new Track { info = info, knots = knots });
            Update();
        }

        /// <summary>Every track that sounds at t, or within two seconds of it, is decoded (or cannot be).</summary>
        public bool ReadyAt(double t)
        {
            foreach (var track in tracks)
                if (NextAudible(track.knots, t) - t <= 2d && track.load is Load.None or Load.Reading) return false;
            return true;
        }

        void Update()
        {
            if (clock == null) return;
            var t = clock.Time;
            AudioSettings.GetDSPBufferSize(out var buffer, out _);
            var lead = (double)LeadBuffers * buffer / AudioSettings.outputSampleRate;
            var now = AudioSettings.dspTime;
            var point = PlacementAt(t, out var yaw, out var pitch);
            Placement = point ? "point" : "wide";

            foreach (var track in tracks)
            {
                var wait = NextAudible(track.knots, t) - t;
                if (track.load == Load.None && wait <= LoadAheadSeconds) Read(track);
                else if (track.load == Load.Ready && wait > UnloadBeyondSeconds) Free(track);
                if (track.load != Load.Ready) continue;

                var gain = Score.GainAt(track.knots, (float)t);
                track.point = point;
                for (var side = 0; side < 2; side++)
                {
                    track.sources[side].volume = point ? gain * 0.5f : gain;
                    track.sources[side].transform.localPosition = point
                        ? Quaternion.Euler(-pitch, yaw, 0f) * Vector3.forward * PointDistance
                        : Quaternion.Euler(0f, side == 0 ? -WideAzimuthDegrees : WideAzimuthDegrees, 0f) * Vector3.forward * WideDistance;
                }

                if (!clock.Playing || gain <= Score.Silent)
                {
                    if (track.started) Stop(track);
                    continue;
                }
                if (track.started && now >= track.startDsp)
                {
                    // where it is against where the clock says, the short way round the loop
                    var off = track.sources[0].time - Score.PositionAt(track.knots, (float)t, track.duration);
                    if (off > track.duration / 2f) off -= track.duration;
                    else if (off < -track.duration / 2f) off += track.duration;
                    track.PositionError = off;
                    if (Mathf.Abs(off) > ResyncSeconds) Stop(track);
                }
                if (track.started) continue;
                track.startDsp = now + lead;
                var from = Score.PositionAt(track.knots, (float)(t + lead), track.duration);
                foreach (var s in track.sources)
                {
                    s.timeSamples = Mathf.Clamp(Mathf.RoundToInt(from * s.clip.frequency), 0, s.clip.samples - 1);
                    s.PlayScheduled(track.startDsp);
                }
                track.started = true;
                track.PositionError = 0f;
            }
        }

        static void Stop(Track track)
        {
            foreach (var s in track.sources) s.Stop();
            track.started = false;
        }

        // when, at or after t, the track next sounds: t itself while it does, infinity when it never will again
        static double NextAudible(List<List<float>> knots, double t)
        {
            for (var i = 0; i + 1 < knots.Count; i++)
                if (knots[i + 1][0] >= t && Mathf.Max(knots[i][1], knots[i + 1][1]) > Score.Silent) return Math.Max(t, knots[i][0]);
            return double.PositiveInfinity;
        }

        bool PlacementAt(double t, out float yaw, out float pitch)
        {
            yaw = pitch = 0f;
            foreach (var p in score.placement)
            {
                if (t < p.start || t >= p.end || p.mode != "point") continue;
                yaw = p.yaw ?? 0f;
                pitch = p.pitch ?? 0f;
                return true;
            }
            return false;
        }

        async void Read(Track track)
        {
            track.load = Load.Reading;
            try
            {
                var file = await source.Read(track.info.file, destroyCancellationToken);
                if (file == null) throw new InvalidOperationException($"{track.info.file} is not in the episode");
                var wav = await Task.Run(() => ZumiWav.Read(file), destroyCancellationToken);
                if (!this) return;
                // one clip a channel: each goes to its own point in the room
                track.clips = new AudioClip[Mathf.Min(wav.channels, 2)];
                for (var c = 0; c < track.clips.Length; c++)
                {
                    track.clips[c] = AudioClip.Create($"{track.Id} {c}", wav.frames, 1, wav.sampleRate, false);
                    track.clips[c].SetData(wav.samples[c], 0);
                }
                track.duration = (float)wav.Seconds;
                for (var side = 0; side < 2; side++)
                {
                    var go = new GameObject($"Music {track.Id} {(side == 0 ? "left" : "right")}");
                    go.transform.SetParent(transform, false);
                    var s = track.sources[side] = go.AddComponent<AudioSource>();
                    s.clip = track.clips[Mathf.Min(side, track.clips.Length - 1)];
                    s.playOnAwake = false;
                    s.loop = track.info.loop;
                    s.volume = 0f;
                    s.spatialBlend = 1f;
                    s.dopplerLevel = 0f;
                    // the envelope is the level: no fall-off with distance inside the room
                    s.rolloffMode = AudioRolloffMode.Logarithmic;
                    s.minDistance = 100f;
                    s.maxDistance = 200f;
                    if (!metaSpatializer) continue;
                    s.spatialize = true;
                    go.AddComponent<MetaXRAudioSource>().EnableAcoustics = false;
                }
                track.load = Load.Ready;
                PeakLoadedBytes = Math.Max(PeakLoadedBytes, LoadedBytes);
                Debug.Log($"[Zumi] music: {track.Id} decoded, {track.duration:F2} s, {track.clips.Length} channels, {track.Bytes / 1048576f:F1} MB; {LoadedBytes / 1048576f:F1} MB held");
            }
            catch (OperationCanceledException) { }
            catch (Exception e)
            {
                // silence where it would have sounded; nothing waits for it
                track.load = Load.Failed;
                Debug.LogWarning($"[Zumi] music: {track.Id} cannot be played ({e.Message}); the episode goes on without it");
            }
        }

        void Free(Track track)
        {
            foreach (var s in track.sources)
                if (s) Destroy(s.gameObject);
            foreach (var clip in track.clips) Destroy(clip);
            track.clips = null;
            track.started = false;
            track.load = Load.None;
        }

        void OnDestroy()
        {
            foreach (var track in tracks)
                if (track.load == Load.Ready) Free(track);
        }
    }
}
