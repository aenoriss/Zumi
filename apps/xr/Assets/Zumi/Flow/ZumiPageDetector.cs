using System;
using System.Collections.Generic;
using UnityEngine;

namespace Zumi
{
    /// <summary>
    /// Says when a new pencil page lies in the scan guide, still, with no hand over it. Pure: fed the guide's
    /// straightened camera sample ten times a second it returns a <see cref="State"/>; it draws nothing and touches
    /// no Unity object. The reference is PageDetector in pipeline/segment/experiments/scan_sim.py, where it was tuned
    /// on simulated Quest 3 sessions; keep the two in step.
    ///
    /// The sample it expects, one call per read-back:
    /// - <see cref="ReadWidth"/> x <see cref="ReadHeight"/> (192 x 268) RGBA32 pixels, row 0 the guide's near edge,
    ///   one bilinear tap per pixel as ZumiWarp draws it, NOT averaged (pencil is read at this resolution; the
    ///   detector averages 2x2 itself for the rest).
    /// - The guide AND a ring of desk around it: the warp's quad is the guide grown by <see cref="RingMetres"/> on
    ///   each side (0.0525 m across, 0.0726 m along for A4), so the guide is cols 32..159, rows 44..223.
    /// - sRGB-encoded values, which is what an ARGB32 render texture in this linear-colour-space project reads
    ///   back. Thresholds are relative to the paper's own white except <see cref="LightDeskWhite"/>.
    ///
    /// Method. (1) White W: the guide's 90th-percentile luma and its colour; all measures are divided by it, so
    /// exposure and gain drop out. (2) Page: most of the guide is near W in brightness and in colour (a cast light
    /// moves paper and white together), and W is clearly brighter than the desk ring, or, on a desk as light as the
    /// guide, bright in absolute terms (an empty desk is its own white, but dimmer). (3) Still: the last sample is
    /// aligned to this one (whole-pixel shift, then a least-squares sub-pixel shift, rotation, scale, gain and
    /// offset: head jitter and exposure); at most a few blocks of the residual, ring included (an arm crosses the
    /// ring), changed. (4) Pencil: read-back pixels darker than the local paper, above the sample's own noise, spread
    /// over many blocks. (5) New: the pencil map correlates with no page taken this session. (6) All of them for
    /// <see cref="HoldSeconds"/>: <see cref="State.Capture"/>.
    /// </summary>
    public sealed class ZumiPageDetector
    {
        public enum State { Empty, Seen, Holding, Capture }

        // ---- the sample ------------------------------------------------------------------------------------------
        /// <summary>The guide at the averaged resolution, px.</summary>
        public const int GuideWidth = 64, GuideHeight = 90;
        /// <summary>The desk ring each side of the guide at the averaged resolution, px.</summary>
        public const int RingX = 16, RingY = 22;
        /// <summary>The averaged sample, the guide and its ring: 96 x 134.</summary>
        public const int Width = GuideWidth + 2 * RingX, Height = GuideHeight + 2 * RingY;
        /// <summary>The read-back the detector is fed: twice the averaged sample, 192 x 268.</summary>
        public const int ReadWidth = 2 * Width, ReadHeight = 2 * Height;

        /// <summary>How far the warp's quad reaches beyond the guide on each side, metres.</summary>
        public static Vector2 RingMetres(Vector2 guide) => new(guide.x * RingX / GuideWidth, guide.y * RingY / GuideHeight);

        // ---- thresholds ------------------------------------------------------------------------------------------
        /// <summary>The paper's white: this quantile of the guide's luma.</summary>
        public const float WhiteQuantile = 0.90f;
        /// <summary>A paper pixel: luma at least this share of white; colour (max - min of r, g, b each divided by
        /// the white's) at most this.</summary>
        public const float PaperRel = 0.72f, PaperChroma = 0.16f;
        /// <summary>A page: at least this share of the guide is paper.</summary>
        public const float PaperShare = 0.65f;
        /// <summary>...and white is at least this many times the ring's median luma; else (a desk as light as the
        /// guide) white is at least <see cref="LightDeskWhite"/> (sRGB, 0..1).</summary>
        public const float PageOverDesk = 1.3f, LightDeskWhite = 0.6f;
        /// <summary>White below this (0..1) is too dark to judge.</summary>
        public const float MinWhite = 0.12f;
        /// <summary>Alignment: the last sample is shifted up to this many px each way before the sub-pixel fit.</summary>
        public const int Shift = 2;
        /// <summary>Still: the residual's blocks of this many px; a block moved when its mean changed by more than
        /// max(StillBlock, StillNoise x the median block change); at most StillBlocks moved.</summary>
        public const int Block = 6;
        public const float StillBlock = 0.015f, StillNoise = 4f;
        public const int StillBlocks = 3;
        /// <summary>Pencil: a read-back pixel darker than the local paper (3x3 max, 5x5 box) by at least
        /// max(InkDark, InkNoise x the sample's noise).</summary>
        public const float InkDark = 0.12f, InkNoise = 5f;
        /// <summary>A page carries pencil: at least this share of the guide's pooled pixels, in at least this many
        /// of its InkBlocksX x InkBlocksY blocks.</summary>
        public const float InkShare = 0.004f;
        public const int InkBlocks = 8, InkBlocksX = 16, InkBlocksY = 18;
        /// <summary>New: 1 - the best correlation of the pencil map with each page taken, over shifts of up to
        /// NovelShift px, at least this.</summary>
        public const float Novel = 0.5f;
        public const int NovelShift = 4;
        /// <summary>Without the novelty test (<see cref="RequireNovelty"/> off; C# only, not in scan_sim.py): after a
        /// capture the next page counts once the guide was seen without a page, or a sample moved at least this many
        /// blocks (a hand passing over it; head jitter moves a few).</summary>
        public const int RearmBlocks = 20;
        /// <summary>Page, still, pencil and new for this long: capture.</summary>
        public const float HoldSeconds = 0.6f;

        // ---- the last sample's measures, for the log and the guide's feedback -------------------------------------
        public float White { get; private set; }
        public float Desk { get; private set; }
        public float Paper { get; private set; }
        public bool Present { get; private set; }
        public int Moved { get; private set; }
        public bool Still { get; private set; }
        public float Noise { get; private set; }
        public float Ink { get; private set; }
        public int InkBlockCount { get; private set; }
        /// <summary>Lowest novelty against the pages taken (1 with none taken); measured only while page, still and
        /// pencil hold.</summary>
        public float Novelty { get; private set; } = 1f;
        public bool Fresh { get; private set; } = true;
        /// <summary>On: a page whose pencil matches a page taken is refused. Off: a page is new once the scanner
        /// re-armed (<see cref="RearmBlocks"/>).</summary>
        public bool RequireNovelty { get; set; } = true;
        /// <summary>Novelty off: false from a capture until the guide was seen empty or a hand passed over it.</summary>
        public bool Armed { get; private set; } = true;
        public int PagesKnown => taken.Count;
        public float HoldProgress => holdSince < 0f ? 0f : Mathf.Clamp01((lastTime - holdSince) / HoldSeconds);
        public override string ToString() =>
            $"white {White:F2} desk {Desk:F2} paper {Paper:F2} moved {Moved} noise {Noise:F3} ink {Ink:F4}/{InkBlockCount} new {Novelty:F2} armed {Armed}";

        // ---- state -----------------------------------------------------------------------------------------------
        const int N1 = Width * Height, N2 = ReadWidth * ReadHeight, NG = GuideWidth * GuideHeight;
        readonly float[] r1 = new float[N1], g1 = new float[N1], b1 = new float[N1], l1 = new float[N1];
        float[] norm = new float[N1], lastNorm = new float[N1];
        bool haveLast;
        readonly float[] l2 = new float[N2], mx = new float[N2], tmp = new float[N2], bg = new float[N2];
        readonly float[] pooled = new float[NG];
        float[] sig = new float[NG];
        readonly List<float[]> taken = new();
        readonly int[] hist = new int[256];
        readonly int[] noiseHist = new int[NoiseBins];
        const int NoiseBins = 1000;
        const float NoiseRange = 0.25f;
        float holdSince = -1f, lastTime;

        /// <summary>A page was taken (by this or by the Scan button) from the last sample: the same pencil is not
        /// taken again.</summary>
        public void Captured()
        {
            holdSince = -1f;
            Armed = false;
            taken.Add((float[])sig.Clone());
        }

        /// <summary>The last page came off the stack (Undo): it may be taken again.</summary>
        public void Forget()
        {
            if (taken.Count > 0) taken.RemoveAt(taken.Count - 1);
        }

        /// <summary>A new session: no page taken yet.</summary>
        public void Reset()
        {
            taken.Clear();
            Armed = true;
            Resume();
        }

        /// <summary>Samples resume after a gap (the sweep and the flight): no stillness across it.</summary>
        public void Resume()
        {
            haveLast = false;
            holdSince = -1f;
        }

        public State Feed(Color32[] px, float time) => Feed(new ReadOnlySpan<Color32>(px), time);

        public State Feed(ReadOnlySpan<Color32> px, float time)
        {
            if (px.Length < N2) throw new ArgumentException($"expected {ReadWidth}x{ReadHeight} pixels, got {px.Length}");
            lastTime = time;
            const float k = 1f / 255f;
            for (var i = 0; i < N2; i++)
            {
                var c = px[i];
                l2[i] = (0.299f * c.r + 0.587f * c.g + 0.114f * c.b) * k;
            }
            for (var y = 0; y < Height; y++)
            for (var x = 0; x < Width; x++)
            {
                int a = 2 * y * ReadWidth + 2 * x, b = a + ReadWidth;
                Color32 p0 = px[a], p1 = px[a + 1], p2 = px[b], p3 = px[b + 1];
                var j = y * Width + x;
                r1[j] = (p0.r + p1.r + p2.r + p3.r) * k * 0.25f;
                g1[j] = (p0.g + p1.g + p2.g + p3.g) * k * 0.25f;
                b1[j] = (p0.b + p1.b + p2.b + p3.b) * k * 0.25f;
                l1[j] = 0.299f * r1[j] + 0.587f * g1[j] + 0.114f * b1[j];
            }

            // 1. white and its colour
            var white = GuideQuantile(WhiteQuantile);
            float wr = 0f, wg = 0f, wb = 0f;
            var wn = 0;
            for (var y = RingY; y < RingY + GuideHeight; y++)
            for (var x = RingX; x < RingX + GuideWidth; x++)
            {
                var j = y * Width + x;
                if (l1[j] < white) continue;
                wr += r1[j]; wg += g1[j]; wb += b1[j]; wn++;
            }
            wn = Mathf.Max(wn, 1);
            wr = Mathf.Max(wr / wn, 0.02f); wg = Mathf.Max(wg / wn, 0.02f); wb = Mathf.Max(wb / wn, 0.02f);
            White = white;
            var ws = Mathf.Max(white, 0.02f);

            // 2. page
            var paper = 0;
            for (var y = RingY; y < RingY + GuideHeight; y++)
            for (var x = RingX; x < RingX + GuideWidth; x++)
            {
                var j = y * Width + x;
                float nr = r1[j] / wr, ng = g1[j] / wg, nb = b1[j] / wb;
                var chroma = Mathf.Max(nr, Mathf.Max(ng, nb)) - Mathf.Min(nr, Mathf.Min(ng, nb));
                if (l1[j] >= PaperRel * ws && chroma <= PaperChroma) paper++;
            }
            Paper = (float)paper / NG;
            Desk = RingMedian();
            Present = Paper >= PaperShare && white >= MinWhite && (white >= PageOverDesk * Desk || white >= LightDeskWhite);

            // 3. still
            for (var i = 0; i < N1; i++) norm[i] = l1[i] / ws;
            Moved = haveLast ? MovedBlocks() : int.MaxValue;
            (norm, lastNorm) = (lastNorm, norm);
            haveLast = true;
            Still = Moved <= StillBlocks;

            // 4. pencil, on the whole read-back (the box blur near the guide's edge sees the ring), counted in the guide
            for (var i = 0; i < N2; i++) l2[i] /= ws;
            Max3(l2, mx, ReadWidth, ReadHeight);
            Box(mx, tmp, bg, ReadWidth, ReadHeight, 2);
            Noise = GuideNoise();
            var threshold = Mathf.Max(InkDark, InkNoise * Noise);
            var inkCount = 0;
            Span<int> blockInk = stackalloc int[InkBlocksX * InkBlocksY];
            blockInk.Clear();
            for (var y = 0; y < GuideHeight; y++)
            for (var x = 0; x < GuideWidth; x++)
            {
                var d = 0f;
                for (var dy = 0; dy < 2; dy++)
                for (var dx = 0; dx < 2; dx++)
                {
                    var j = (2 * (y + RingY) + dy) * ReadWidth + 2 * (x + RingX) + dx;
                    d = Mathf.Max(d, Mathf.Clamp01(1f - l2[j] / Mathf.Max(bg[j], 1e-3f)));
                }
                pooled[y * GuideWidth + x] = d;
                if (d < threshold) continue;
                inkCount++;
                blockInk[y * InkBlocksY / GuideHeight * InkBlocksX + x * InkBlocksX / GuideWidth]++;
            }
            Ink = (float)inkCount / NG;
            var blocks = 0;
            foreach (var b in blockInk) if (b > 0) blocks++;
            InkBlockCount = blocks;
            var hasInk = Ink >= InkShare && blocks >= InkBlocks;
            Box(pooled, sigTmp, sig, GuideWidth, GuideHeight, 1);

            // 5. new: measured only when it can matter (it is the costly part); without it, re-armed
            if (!RequireNovelty)
            {
                if (!Armed && (!Present || (Moved != int.MaxValue && Moved >= RearmBlocks))) Armed = true;
                Novelty = 1f;
                Fresh = Armed;
            }
            else if (Present && Still && hasInk)
            {
                Novelty = 1f;
                foreach (var t in taken)
                {
                    Novelty = Mathf.Min(Novelty, 1f - BestCorrelation(sig, t));
                    if (Novelty < Novel) break;
                }
                Fresh = Novelty >= Novel;
            }

            // 6. hold
            if (Present && Still && hasInk && Fresh)
            {
                if (holdSince < 0f) holdSince = time;
                return time - holdSince >= HoldSeconds - 1e-4f ? State.Capture : State.Holding;
            }
            holdSince = -1f;
            return Present ? State.Seen : State.Empty;
        }

        readonly float[] sigTmp = new float[NG];

        float GuideQuantile(float q)
        {
            Array.Clear(hist, 0, hist.Length);
            for (var y = RingY; y < RingY + GuideHeight; y++)
            for (var x = RingX; x < RingX + GuideWidth; x++)
                hist[Mathf.Clamp((int)(l1[y * Width + x] * 255f + 0.5f), 0, 255)]++;
            return FromHistogram(hist, q, NG) / 255f;
        }

        float RingMedian()
        {
            Array.Clear(hist, 0, hist.Length);
            var n = 0;
            for (var y = 0; y < Height; y++)
            for (var x = 0; x < Width; x++)
            {
                if (y >= RingY && y < RingY + GuideHeight && x >= RingX && x < RingX + GuideWidth) continue;
                hist[Mathf.Clamp((int)(l1[y * Width + x] * 255f + 0.5f), 0, 255)]++;
                n++;
            }
            return FromHistogram(hist, 0.5f, n) / 255f;
        }

        static int FromHistogram(int[] h, float q, int n)
        {
            var target = q * (n - 1);
            var seen = 0;
            for (var v = 0; v < h.Length; v++)
            {
                seen += h[v];
                if (seen > target) return v;
            }
            return h.Length - 1;
        }

        // the read-back's noise in the guide: the median neighbour difference (pencil is too sparse to move it),
        // as a standard deviation
        float GuideNoise()
        {
            Array.Clear(noiseHist, 0, NoiseBins);
            var n = 0;
            for (var y = 2 * RingY; y < 2 * (RingY + GuideHeight); y++)
            for (var x = 2 * RingX; x < 2 * (RingX + GuideWidth) - 1; x++)
            {
                var d = Mathf.Abs(l2[y * ReadWidth + x + 1] - l2[y * ReadWidth + x]);
                noiseHist[Mathf.Min((int)(d / NoiseRange * NoiseBins), NoiseBins - 1)]++;
                n++;
            }
            var median = (FromHistogram(noiseHist, 0.5f, n) + 0.5f) * NoiseRange / NoiseBins;
            return 1.4826f * median / Mathf.Sqrt(2f);
        }

        // ---- stillness ---------------------------------------------------------------------------------------------

        const int SW = Width - 2 * Shift, SH = Height - 2 * Shift, SN = SW * SH;
        readonly float[] cur = new float[SN], prev = new float[SN], resid = new float[SN];
        readonly double[] ata = new double[36], atb = new double[6], coef = new double[6];

        // how many blocks of the whole sample changed, once the last sample is aligned to this one
        int MovedBlocks()
        {
            const int s = Shift;
            int bestX = 0, bestY = 0;
            var best = float.MaxValue;
            for (var dy = -s; dy <= s; dy++)
            for (var dx = -s; dx <= s; dx++)
            {
                var sum = 0f;
                for (var y = 0; y < SH; y++)
                {
                    int a = (y + s) * Width + s, b = (y + s + dy) * Width + s + dx;
                    for (var x = 0; x < SW; x++) sum += Mathf.Abs(norm[a + x] - lastNorm[b + x]);
                }
                if (sum < best) { best = sum; bestX = dx; bestY = dy; }
            }
            for (var y = 0; y < SH; y++)
            for (var x = 0; x < SW; x++)
            {
                cur[y * SW + x] = norm[(y + s) * Width + x + s];
                prev[y * SW + x] = lastNorm[(y + s + bestY) * Width + x + s + bestX];
            }
            FitResidual();
            int bx = SW / Block, by = SH / Block;
            Span<float> sum2 = stackalloc float[bx * by];
            Span<int> count = stackalloc int[bx * by];
            sum2.Clear();
            count.Clear();
            for (var y = 0; y < SH; y++)
            for (var x = 0; x < SW; x++)
            {
                var i = y * by / SH * bx + x * bx / SW;
                sum2[i] += resid[y * SW + x];
                count[i]++;
            }
            var change = new float[bx * by];
            for (var i = 0; i < change.Length; i++) change[i] = Mathf.Abs(sum2[i] / Mathf.Max(count[i], 1));
            var sorted = (float[])change.Clone();
            Array.Sort(sorted);
            var limit = Mathf.Max(StillBlock, StillNoise * sorted[sorted.Length / 2]);
            var moved = 0;
            foreach (var c in change) if (c > limit) moved++;
            return moved;
        }

        // cur - prev, minus what a sub-pixel shift, a small rotation and scale about the centre, and an exposure
        // gain and offset of prev explain (least squares): what changed on the desk
        void FitResidual()
        {
            Array.Clear(ata, 0, 36);
            Array.Clear(atb, 0, 6);
            Span<double> j = stackalloc double[6];
            float cx = (SW - 1) / 2f, cy = (SH - 1) / 2f;
            for (var pass = 0; pass < 2; pass++)
            for (var y = 0; y < SH; y++)
            for (var x = 0; x < SW; x++)
            {
                var i = y * SW + x;
                Basis(x, y, cx, cy, j);
                if (pass == 0)
                {
                    double d = cur[i] - prev[i];
                    for (var a = 0; a < 6; a++)
                    {
                        atb[a] += j[a] * d;
                        for (var b = a; b < 6; b++) ata[a * 6 + b] += j[a] * j[b];
                    }
                    if (y == SH - 1 && x == SW - 1) Solve();
                }
                else
                {
                    double e = 0;
                    for (var a = 0; a < 6; a++) e += j[a] * coef[a];
                    resid[i] = (float)(cur[i] - prev[i] - e);
                }
            }
        }

        // np.gradient: central differences inside, one-sided at the edges
        void Basis(int x, int y, float cx, float cy, Span<double> j)
        {
            var i = y * SW + x;
            double gx = x == 0 ? prev[i + 1] - prev[i] : x == SW - 1 ? prev[i] - prev[i - 1] : (prev[i + 1] - prev[i - 1]) * 0.5;
            double gy = y == 0 ? prev[i + SW] - prev[i] : y == SH - 1 ? prev[i] - prev[i - SW] : (prev[i + SW] - prev[i - SW]) * 0.5;
            double xc = x - cx, yc = y - cy;
            j[0] = gx;
            j[1] = gy;
            j[2] = -gx * yc + gy * xc;
            j[3] = gx * xc + gy * yc;
            j[4] = prev[i];
            j[5] = 1;
        }

        void Solve()
        {
            var m = new double[6, 7];
            for (var a = 0; a < 6; a++)
            {
                for (var b = 0; b < 6; b++) m[a, b] = a <= b ? ata[a * 6 + b] : ata[b * 6 + a];
                m[a, a] += 1e-6;
                m[a, 6] = atb[a];
            }
            for (var c = 0; c < 6; c++)
            {
                var p = c;
                for (var r = c + 1; r < 6; r++) if (Math.Abs(m[r, c]) > Math.Abs(m[p, c])) p = r;
                if (p != c) for (var k = 0; k < 7; k++) (m[c, k], m[p, k]) = (m[p, k], m[c, k]);
                if (Math.Abs(m[c, c]) < 1e-12) continue;
                for (var r = 0; r < 6; r++)
                {
                    if (r == c) continue;
                    var f = m[r, c] / m[c, c];
                    for (var k = c; k < 7; k++) m[r, k] -= f * m[c, k];
                }
            }
            for (var a = 0; a < 6; a++) coef[a] = Math.Abs(m[a, a]) < 1e-12 ? 0 : m[a, 6] / m[a, a];
        }

        // ---- novelty ---------------------------------------------------------------------------------------------

        // the best normalised correlation of the taken map's centre over this map, shifted up to NovelShift px
        static float BestCorrelation(float[] a, float[] b)
        {
            const int s = NovelShift, w = GuideWidth, h = GuideHeight, tw = w - 2 * s, th = h - 2 * s, n = tw * th;
            float tm = 0f;
            for (var y = 0; y < th; y++)
            for (var x = 0; x < tw; x++) tm += b[(y + s) * w + x + s];
            tm /= n;
            var tv = 0f;
            for (var y = 0; y < th; y++)
            for (var x = 0; x < tw; x++) { var d = b[(y + s) * w + x + s] - tm; tv += d * d; }
            if (tv < 1e-8f) return 0f;
            var best = -1f;
            for (var oy = 0; oy <= 2 * s; oy++)
            for (var ox = 0; ox <= 2 * s; ox++)
            {
                float sa = 0f, saa = 0f, sab = 0f;
                for (var y = 0; y < th; y++)
                {
                    int ia = (y + oy) * w + ox, ib = (y + s) * w + s;
                    for (var x = 0; x < tw; x++)
                    {
                        var va = a[ia + x];
                        sa += va;
                        saa += va * va;
                        sab += va * (b[ib + x] - tm);
                    }
                }
                var av = saa - sa * sa / n;
                if (av < 1e-8f) continue;
                best = Mathf.Max(best, sab / Mathf.Sqrt(av * tv));
            }
            return best;
        }

        // ---- filters ---------------------------------------------------------------------------------------------

        // 3x3 max, edges clamped
        static void Max3(float[] src, float[] dst, int w, int h)
        {
            for (var y = 0; y < h; y++)
            {
                int y0 = Mathf.Max(y - 1, 0), y1 = Mathf.Min(y + 1, h - 1);
                for (var x = 0; x < w; x++)
                {
                    int x0 = Mathf.Max(x - 1, 0), x1 = Mathf.Min(x + 1, w - 1);
                    var m = 0f;
                    for (var yy = y0; yy <= y1; yy++)
                    for (var xx = x0; xx <= x1; xx++)
                        m = Mathf.Max(m, src[yy * w + xx]);
                    dst[y * w + x] = m;
                }
            }
        }

        // a (2r+1)-wide box blur, separable, edges clamped
        static void Box(float[] src, float[] tmp, float[] dst, int w, int h, int r)
        {
            var inv = 1f / (2 * r + 1);
            for (var y = 0; y < h; y++)
            for (var x = 0; x < w; x++)
            {
                var s = 0f;
                for (var d = -r; d <= r; d++) s += src[y * w + Mathf.Clamp(x + d, 0, w - 1)];
                tmp[y * w + x] = s * inv;
            }
            for (var y = 0; y < h; y++)
            for (var x = 0; x < w; x++)
            {
                var s = 0f;
                for (var d = -r; d <= r; d++) s += tmp[Mathf.Clamp(y + d, 0, h - 1) * w + x];
                dst[y * w + x] = s * inv;
            }
        }
    }
}
