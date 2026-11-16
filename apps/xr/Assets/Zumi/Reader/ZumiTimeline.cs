using System.Collections.Generic;
using Zumi.Format;

namespace Zumi
{
    /// <summary>
    /// When each panel of an episode is on the clock, from the manifest's precomputed startTime and endTime. The panel
    /// at t is the last one that has started: [startTime, endTime) when the panels follow each other, as the
    /// pipeline writes them. A hand-made file without times gets them from the format's pacing rule.
    /// </summary>
    public sealed class ZumiTimeline
    {
        public readonly struct Entry
        {
            public readonly string id;
            public readonly double start, end;

            public Entry(string id, double start, double end)
            {
                this.id = id;
                this.start = start;
                this.end = end;
            }
        }

        readonly List<Entry> panels = new();

        public IReadOnlyList<Entry> Panels => panels;
        public double Duration => panels.Count > 0 ? panels[^1].end : 0d;

        public ZumiTimeline(ZumiManifest manifest)
        {
            var at = 0d;
            foreach (var p in manifest.panels)
            {
                var start = p.startTime ?? at;
                var end = p.endTime ?? start + Pacing.Duration(p, _ => 0f);
                panels.Add(new Entry(p.id, start, end));
                at = end;
            }
        }

        /// <summary>-1 for an episode without panels.</summary>
        public int IndexAt(double t)
        {
            var i = panels.Count - 1;
            while (i > 0 && panels[i].start > t) i--;
            return i;
        }

        public string IdAt(double t) => panels.Count > 0 ? panels[IndexAt(t)].id : null;
    }
}
