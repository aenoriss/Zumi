using System;
using UnityEngine;

namespace Zumi
{
    /// <summary>
    /// The episode's one clock: seconds from its start. Everything shown or heard reads Time and nothing else; only
    /// the transport (the hand menu, the editor keys) and the reader's own autoplay and system pauses call Play,
    /// Pause and Seek. A networked clock for a shared room implements this and replaces ZumiDspClock.
    /// </summary>
    public interface IEpisodeClock
    {
        double Time { get; }
        bool Playing { get; }
        /// <summary>The episode's length: Time never passes it.</summary>
        double Duration { get; }
        void Play();
        void Pause();
        /// <summary>Jumps to t (clamped to the episode); playing or paused stays as it was.</summary>
        void Seek(double t);
        /// <summary>While playing: the audio engine's time (AudioSettings.dspTime) at which the clock reads t, in the
        /// past or ahead. What a sound is scheduled by, so it starts on the clock to the sample.</summary>
        double DspTimeAt(double t);
        /// <summary>Raised once each time the clock reaches Duration while playing; it has stopped there.</summary>
        event Action Ended;
        /// <summary>Seconds since the clock stopped at Duration, on the same time base as Time; 0 while it has not, or
        /// once it has left the end again. What closes an episode (the place going, the end card coming) reads this:
        /// Time itself never passes Duration.</summary>
        double EndedFor { get; }
    }

    /// <summary>
    /// The local clock, on the audio engine's time (AudioSettings.dspTime): a voice scheduled with PlayScheduled sits
    /// on the same timeline, so sound cannot drift from what is shown. dspTime moves one audio buffer at a time
    /// (about 20 ms), which is finer than anything the reader times by it.
    /// </summary>
    public sealed class ZumiDspClock : IEpisodeClock
    {
        // Time = anchorTime + (dspTime - anchorDsp) while playing; anchorTime alone while paused
        double anchorTime, anchorDsp, anchorWall;
        // the audio engine's time at which the clock stopped at the end; negative while it is not there
        double endedDsp = -1d;

        public double Duration { get; }
        public bool Playing { get; private set; }
        public event Action Ended;

        public ZumiDspClock(double duration) => Duration = duration;

        public double Time => Playing ? Math.Min(Duration, anchorTime + (AudioSettings.dspTime - anchorDsp)) : anchorTime;

        /// <summary>Seconds the clock has gained on real time since it last started or jumped; 0 while paused or at
        /// the end. A check that the audio engine's time runs at the wall's pace, nothing reads it to tell the time.</summary>
        public double WallDrift => Playing && Time < Duration
            ? Time - anchorTime - (UnityEngine.Time.realtimeSinceStartupAsDouble - anchorWall) : 0d;

        public double EndedFor => endedDsp >= 0d ? Math.Max(0d, AudioSettings.dspTime - endedDsp) : 0d;

        public double DspTimeAt(double t) => anchorDsp + (t - anchorTime);

        public void Play()
        {
            if (Playing || anchorTime >= Duration) return;
            Anchor(anchorTime);
            Playing = true;
        }

        void Anchor(double time)
        {
            anchorTime = time;
            anchorDsp = AudioSettings.dspTime;
            anchorWall = UnityEngine.Time.realtimeSinceStartupAsDouble;
        }

        public void Pause()
        {
            if (!Playing) return;
            anchorTime = Time;
            Playing = false;
        }

        public void Seek(double t)
        {
            Anchor(Math.Clamp(t, 0d, Duration));
            endedDsp = -1d;
        }

        /// <summary>Once a frame, by the clock's owner: stops at the end and says so.</summary>
        public void Tick()
        {
            if (!Playing || Time < Duration) return;
            anchorTime = Duration;
            Playing = false;
            endedDsp = AudioSettings.dspTime;
            Ended?.Invoke();
        }
    }
}
