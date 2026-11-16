using System;

namespace Zumi
{
    /// <summary>
    /// What the reader can do to the clock: pause or resume, go forward, go back. The hand menu and the editor keys
    /// both call this, so the rules are stated once.
    /// </summary>
    public sealed class ZumiTransport
    {
        /// <summary>Back returns to the start of the panel on screen; within this many seconds of that start it goes
        /// to the panel before instead, so two presses in a row walk backwards.</summary>
        public const double BackRestartSeconds = 1d;

        readonly IEpisodeClock clock;
        readonly ZumiTimeline timeline;
        readonly Action<string> used;

        /// <param name="used">Told "menu" each time something here moves the clock (the reader keeps why it last did).</param>
        public ZumiTransport(IEpisodeClock clock, ZumiTimeline timeline, Action<string> used = null)
        {
            this.clock = clock;
            this.timeline = timeline;
            this.used = used;
        }

        public bool Playing => clock.Playing;

        public void TogglePause()
        {
            used?.Invoke("menu");
            if (clock.Playing) clock.Pause();
            else clock.Play();
        }

        /// <summary>To the next panel's start; nothing on the last panel.</summary>
        public void Forward()
        {
            var i = timeline.IndexAt(clock.Time);
            if (i < 0 || i + 1 >= timeline.Panels.Count) return;
            used?.Invoke("menu");
            clock.Seek(timeline.Panels[i + 1].start);
        }

        public void Back()
        {
            var i = timeline.IndexAt(clock.Time);
            if (i < 0) return;
            if (i > 0 && clock.Time - timeline.Panels[i].start < BackRestartSeconds) i--;
            used?.Invoke("menu");
            clock.Seek(timeline.Panels[i].start);
        }
    }
}
