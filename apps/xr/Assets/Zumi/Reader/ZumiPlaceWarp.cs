using UnityEngine;
using static System.FormattableString;

namespace Zumi
{
    /// <summary>
    /// How a place is fitted to the room it is shown in: a map from the place's own directions (its picture, hDeg by
    /// vDeg around the seat) to the room's. A pure function of the room's ground plan as seen from the seat, the
    /// room's height and the place's span: the same room and seat give the same warp, and Reseat gives a new one.
    ///
    /// 1. The room from the seat: along every azimuth, which wall is met, how far (r) and how squarely (q, the cosine
    ///    of the angle between the line of sight and the wall's normal).
    /// 2. What can show: the key wall in full, and its neighbours for as long as they are seen squarely enough
    ///    (q at least MinSquareness); past that the place fades out over EdgeDegrees. Up and down: the walls, from the
    ///    floor line to their top; the ceiling does not show (seen from below it smears).
    /// 3. The place's core (Core): the middle of its picture, CoreShare of its width, from CoreDown below its horizon
    ///    to CoreUp above it.
    /// 4. One zoom for the core, m0: the largest that still fits the core on the key wall, never above 1 (nothing is
    ///    enlarged) and never below MinZoom. Inside the core the zoom is the same across and up, so shapes keep their
    ///    proportions; the core's middle is the key wall's middle and the place's horizon is at the eye's height.
    /// 5. Outside the core the zoom follows the wall: it aims at as many degrees of picture per metre of wall as the
    ///    core's edge has (so a stretch of wall seen at a grazing angle gets little picture squeezed and a stretch
    ///    beside the seat gets it spread), kept within m0 / ZoomRange and m0 * ZoomRange (and never above 1) and eased
    ///    over SmoothDegrees so there is no kink at a corner. Up and down follow the same local zoom.
    /// 6. Depth follows the zoom: a part shown smaller is that much farther (ZumiPlaces then puts the whole beyond
    ///    the walls).
    /// Without a scanned room the map is the plain zoom m0 that fits the core in the window.
    /// </summary>
    public sealed class ZumiPlaceWarp
    {
        /// <summary>A neighbouring wall shows the place while it is seen at least this squarely: the cosine of 60 degrees.</summary>
        public const float MinSquareness = 0.5f;
        /// <summary>The place always shows at least this many degrees to either side of the key wall's direction,
        /// whatever the walls there: the panel covers 27.5 of them.</summary>
        public const float MinShowDegrees = 50f;
        /// <summary>Degrees over which the place fades out past the end of what can show.</summary>
        public const float EdgeDegrees = 8f;
        /// <summary>The core: this share of the picture's width, about its middle.</summary>
        public const float CoreShare = 0.6f;
        /// <summary>The core reaches this share of the picture's half height above its horizon (the vignette's full
        /// strength) and this share below it.</summary>
        public const float CoreUp = 0.3f, CoreDown = 0.5f;
        /// <summary>The core is never shown smaller than this.</summary>
        public const float MinZoom = 0.5f;
        /// <summary>Outside the core the local zoom stays within m0 / ZoomRange and m0 * ZoomRange.</summary>
        public const float ZoomRange = 1.5f;
        /// <summary>Degrees of room over which the local zoom eases toward what the wall asks for.</summary>
        public const float SmoothDegrees = 15f;
        const float Step = 0.25f, MaxAzimuth = 150f;

        /// <summary>The core's zoom.</summary>
        public float m0;
        /// <summary>Degrees from the key wall's direction (right positive): the key wall's two ends, and the ends of
        /// what can show.</summary>
        public float keyLeft, keyRight, showLeft, showRight;
        /// <summary>The smallest and the largest local zoom over the picture.</summary>
        public float zoomMin, zoomMax;
        /// <summary>Metres of wall one degree of picture covers, where the neighbouring walls are worst and best: at
        /// the picture's edge and just past the key wall's corner, before (zoom 1) and after. 0 where there is none.</summary>
        public float wallPerDegreeCornerBefore, wallPerDegreeEdgeBefore, wallPerDegreeCornerAfter, wallPerDegreeEdgeAfter;

        readonly float halfSpan;
        // per Step of picture azimuth from -halfSpan: the room azimuth it maps to and the local zoom there
        readonly float[] azimuth, zoom;
        readonly Vector2[] outline;
        readonly float wallDistance, up, down;
        readonly bool room;

        public string Summary => Invariant($"m0 {m0:F2}, key wall {keyLeft:F0}..{keyRight:F0} deg, shows {showLeft:F0}..{showRight:F0} deg, local zoom {zoomMin:F2}..{zoomMax:F2}, wall per picture degree at the corner {wallPerDegreeCornerBefore * 100f:F1} -> {wallPerDegreeCornerAfter * 100f:F1} cm, at the picture's edge {wallPerDegreeEdgeBefore * 100f:F1} -> {wallPerDegreeEdgeAfter * 100f:F1} cm");

        /// <summary>The core of a place's picture, in degrees: half its width, and how far it reaches above and below
        /// the horizon. Today by the picture's span alone; a weight by what the picture holds can replace this.</summary>
        public static void Core(float hDeg, float vDeg, out float halfWidth, out float above, out float below)
        {
            halfWidth = CoreShare * hDeg / 2f;
            above = CoreUp * vDeg / 2f;
            below = CoreDown * vDeg / 2f;
        }

        public ZumiPlaceWarp(RoomShape shape, float hDeg, float vDeg)
        {
            halfSpan = hDeg / 2f;
            room = shape.mode == RoomMode.Scanned && shape.outline.Length >= 3;
            wallDistance = shape.wallDistance;
            up = shape.ceilingY - shape.eye.y;
            down = shape.eye.y - shape.floorY;
            Core(hDeg, vDeg, out var core, out var above, out var below);

            float keyUp, keyDown;
            if (room)
            {
                // the ground plan in the place's frame: the eye at the origin, y to the key wall, x to its right
                outline = new Vector2[shape.outline.Length];
                Vector2 eye = new(shape.eye.x, shape.eye.z), ahead = new(shape.forward.x, shape.forward.z), right = new(shape.right.x, shape.right.z);
                for (var i = 0; i < outline.Length; i++) outline[i] = new Vector2(Vector2.Dot(shape.outline[i] - eye, right), Vector2.Dot(shape.outline[i] - eye, ahead));
                Cast(0f, out var key, out _, out _);
                for (keyRight = 0f; keyRight < MaxAzimuth && Cast(keyRight + Step, out var e, out _, out _) && e == key; keyRight += Step) { }
                for (keyLeft = 0f; keyLeft > -MaxAzimuth && Cast(keyLeft - Step, out var e, out _, out _) && e == key; keyLeft -= Step) { }
                for (showRight = keyRight; showRight < MaxAzimuth && Cast(showRight + Step, out _, out _, out var q) && q >= MinSquareness; showRight += Step) { }
                for (showLeft = keyLeft; showLeft > -MaxAzimuth && Cast(showLeft - Step, out _, out _, out var q) && q >= MinSquareness; showLeft -= Step) { }
                // the panel hides MinShowDegrees less its margin of the middle: a key wall narrower than that would
                // leave nothing of the place in sight
                showRight = Mathf.Max(showRight, MinShowDegrees);
                showLeft = Mathf.Min(showLeft, -MinShowDegrees);
                Cast((keyLeft + keyRight) / 2f, out _, out var r, out _);
                keyUp = Mathf.Atan2(up, r) * Mathf.Rad2Deg;
                keyDown = Mathf.Atan2(down, r) * Mathf.Rad2Deg;
            }
            else
            {
                // one window on the wall plane
                keyRight = showRight = Mathf.Atan2(shape.windowHalf.x, wallDistance) * Mathf.Rad2Deg;
                keyLeft = showLeft = -keyRight;
                keyUp = Mathf.Atan2(shape.windowCentre.y + shape.windowHalf.y - shape.eye.y, wallDistance) * Mathf.Rad2Deg;
                keyDown = Mathf.Atan2(shape.eye.y - (shape.windowCentre.y - shape.windowHalf.y), wallDistance) * Mathf.Rad2Deg;
            }
            // across: the core on the key wall, or failing that the whole picture in what can show
            var across = Mathf.Max((keyRight - keyLeft) / (2f * core), room ? (showRight - showLeft) / (hDeg - 2f * ZumiPlaces.VignetteInsetDegrees) : 0f);
            m0 = Mathf.Clamp(Mathf.Min(across, Mathf.Min(keyUp / above, keyDown / below)), MinZoom, 1f);
            var centre = (keyLeft + keyRight) / 2f;

            var n = Mathf.CeilToInt(2f * halfSpan / Step) + 1;
            azimuth = new float[n];
            zoom = new float[n];
            zoomMin = zoomMax = m0;
            for (var i = 0; i < n; i++)
            {
                var theta = -halfSpan + i * Step;
                if (Mathf.Abs(theta) > core) continue;
                azimuth[i] = centre + m0 * theta;
                zoom[i] = m0;
            }
            // outward from each edge of the core
            foreach (var side in new[] { 1, -1 })
            {
                float a = centre + side * m0 * core, z = m0, reference = Density(a);
                var first = true;
                for (var theta = core + Step; theta <= halfSpan + 1e-3f; theta += Step)
                {
                    if (room && reference > 0f)
                    {
                        // as much picture per metre of wall as at the core's edge, within the range, eased
                        var asked = Mathf.Clamp(m0 * Density(a) / reference, m0 / ZoomRange, Mathf.Min(1f, m0 * ZoomRange));
                        z += (asked - z) * Mathf.Min(1f, z * Step / SmoothDegrees);
                    }
                    a += side * z * Step;
                    var i = Mathf.Clamp(Mathf.RoundToInt((side * theta + halfSpan) / Step), 0, n - 1);
                    azimuth[i] = a;
                    zoom[i] = z;
                    zoomMin = Mathf.Min(zoomMin, z);
                    zoomMax = Mathf.Max(zoomMax, z);
                    // on the neighbouring wall: how much wall a degree of picture covers
                    if (!room || side < 0 || !Cast(a, out _, out var r, out var q) || a <= keyRight) continue;
                    var metres = r / Mathf.Max(q, 0.02f) * Mathf.Deg2Rad;
                    if (first)
                    {
                        wallPerDegreeCornerAfter = metres * z;
                        first = false;
                    }
                    wallPerDegreeEdgeAfter = metres * z;
                }
            }
            if (!room) return;
            // the same two places with no warp: the picture's own degrees on the room
            if (keyRight + Step < halfSpan && Cast(keyRight + Step, out _, out var r0, out var q0)) wallPerDegreeCornerBefore = r0 / Mathf.Max(q0, 0.02f) * Mathf.Deg2Rad;
            if (keyRight + Step < halfSpan && Cast(halfSpan, out _, out var r1, out var q1)) wallPerDegreeEdgeBefore = r1 / Mathf.Max(q1, 0.02f) * Mathf.Deg2Rad;
        }

        /// <summary>Where a point of the place's mesh (its own frame: the eye at the origin, x right, y up, z ahead)
        /// is shown: the unit direction in the same frame, the local zoom there, and how much of it shows by where it
        /// lands in the room (1 within what can show, 0 past its soft edge).</summary>
        public void Map(Vector3 p, out Vector3 direction, out float localZoom, out float shows)
        {
            var d = p.magnitude;
            var theta = Mathf.Atan2(p.x, p.z) * Mathf.Rad2Deg;
            var phi = Mathf.Asin(Mathf.Clamp(p.y / Mathf.Max(d, 1e-6f), -1f, 1f)) * Mathf.Rad2Deg;
            var at = Mathf.Clamp((theta + halfSpan) / Step, 0f, azimuth.Length - 1);
            int i = Mathf.Min((int)at, azimuth.Length - 2);
            var a = Mathf.Lerp(azimuth[i], azimuth[i + 1], at - i);
            localZoom = Mathf.Lerp(zoom[i], zoom[i + 1], at - i);
            var e = Mathf.Clamp(phi * localZoom, -89f, 89f) * Mathf.Deg2Rad;
            var ar = a * Mathf.Deg2Rad;
            direction = new Vector3(Mathf.Sin(ar) * Mathf.Cos(e), Mathf.Sin(e), Mathf.Cos(ar) * Mathf.Cos(e));
            var past = Mathf.Max(a - showRight, showLeft - a);
            var u = 1f - Mathf.Clamp01(past / EdgeDegrees);
            shows = u * u * (3f - 2f * u);
        }

        // picture the wall asks for along a room azimuth: degrees per metre of wall, up to a constant
        float Density(float a) => Cast(a, out _, out var r, out var q) ? q / r : 0f;

        // along a room azimuth (degrees from the key wall's direction): the wall met, how far, how squarely
        bool Cast(float a, out int edge, out float r, out float squareness)
        {
            edge = -1;
            r = float.PositiveInfinity;
            squareness = 0f;
            if (!room)
            {
                var c = Mathf.Cos(a * Mathf.Deg2Rad);
                if (c <= 1e-3f) return false;
                r = wallDistance / c;
                squareness = c;
                edge = 0;
                return true;
            }
            var d = new Vector2(Mathf.Sin(a * Mathf.Deg2Rad), Mathf.Cos(a * Mathf.Deg2Rad));
            for (int i = 0, j = outline.Length - 1; i < outline.Length; j = i++)
            {
                Vector2 p = outline[j], e = outline[i] - p;
                var cross = d.x * e.y - d.y * e.x;
                if (Mathf.Abs(cross) < 1e-8f) continue;
                var along = (p.x * e.y - p.y * e.x) / cross;
                var on = (p.x * d.y - p.y * d.x) / cross;
                if (along <= 1e-4f || on < 0f || on > 1f || along >= r) continue;
                r = along;
                edge = i;
                squareness = Mathf.Abs(cross) / e.magnitude;
            }
            return edge >= 0;
        }
    }
}
