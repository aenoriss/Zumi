using UnityEngine;
using static System.FormattableString;

namespace Zumi
{
    /// <summary>
    /// How a place is fitted to the room it is shown in: a map from the place's own directions (its picture, hDeg by
    /// vDeg around the seat) to the room's. A pure function of the room's ground plan as seen from the seat, the
    /// room's height, the seat's forward (where the panel floats) and the place's span: the same room and seat give
    /// the same warp, and Reseat gives a new one. One idea runs through it: each room direction gets as much of the
    /// picture as the reader can actually see there.
    ///
    /// 1. The room from the seat: along every azimuth, which wall is met, how far (r) and how squarely (q, the cosine
    ///    of the angle between the line of sight and the wall's normal).
    /// 2. What can show: the key wall in full, and its neighbours for as long as they are seen squarely enough
    ///    (q at least MinSquareness); past that the place fades out over EdgeDegrees. Up and down: the walls, from the
    ///    floor line to their top; the ceiling does not show (seen from below it smears).
    /// 3. What the panel hides: the panel floats on the seat's forward and covers at most PanelHalfDegrees to every
    ///    side of it, head movement included (the same bound for every panel, so the fit does not change from panel
    ///    to panel). A direction's visibility is the share of the wall's height there that the panel leaves in sight:
    ///    lowest behind the panel's middle, rising along one smooth bump to 1 at PanelEaseDegrees past its bound.
    /// 4. The place's core (Core): the middle of its picture, CoreShare of its width, from CoreDown below its horizon
    ///    to CoreUp above it.
    /// 5. One zoom for the core where it is in sight, m0: the largest that still fits the core on the key wall (taken
    ///    at least MinShowDegrees to either side: a key wall narrower than the panel would leave nothing of it in
    ///    sight), never above 1 (nothing in sight is enlarged) and never below MinZoom. Where the core is in sight
    ///    the zoom is the same across and up, so shapes keep their proportions; the picture's middle is the middle of
    ///    that stretch and the place's horizon is at the eye's height.
    /// 6. Behind the panel the zoom is m0 over the visibility, at most m0 * ZoomRange: little of the picture is spent
    ///    where it cannot be seen, so the core lands beside the panel.
    /// 7. Outside the core the zoom follows the wall: it aims at as many degrees of picture per metre of wall as the
    ///    core's edge has (so a stretch of wall seen at a grazing angle gets little picture squeezed and a stretch
    ///    beside the seat gets it spread), kept within m0 / ZoomRange and m0 * ZoomRange (and never above 1) and eased
    ///    over SmoothDegrees so there is no kink at a corner.
    /// 8. Up and down: the local zoom from CoreDown to CoreUp; beyond them, bending over BendDegrees, the zoom that
    ///    puts the picture's lower edge (at full strength) on the floor line and its upper edge on the top of the
    ///    wall, within the local zoom / ZoomRange and * ZoomRange. The shader cuts each pixel at the floor line and
    ///    the wall's top (Map hands it both); where the zoom is not enough the picture ends short of them.
    /// 9. Depth follows the zoom across: a part shown smaller is that much farther (ZumiPlaces then puts the whole
    ///    beyond the walls).
    /// Without a scanned room the walls are the one window, and the same rule holds in it.
    /// </summary>
    public sealed class ZumiPlaceWarp
    {
        /// <summary>A neighbouring wall shows the place while it is seen at least this squarely: the cosine of 60 degrees.</summary>
        public const float MinSquareness = 0.5f;
        /// <summary>The place always shows at least this many degrees to either side of the key wall's direction,
        /// whatever the walls there, and the core may take as much: the panel covers 27.5 of them.</summary>
        public const float MinShowDegrees = 50f;
        /// <summary>Degrees over which the place fades out past the end of what can show.</summary>
        public const float EdgeDegrees = 8f;
        /// <summary>The core: this share of the picture's width, about its middle.</summary>
        public const float CoreShare = 0.6f;
        /// <summary>The core reaches this share of the picture's half height above its horizon and this share below it.</summary>
        public const float CoreUp = 0.3f, CoreDown = 0.5f;
        /// <summary>The core is never shown smaller than this.</summary>
        public const float MinZoom = 0.5f;
        /// <summary>The local zoom stays within m0 / ZoomRange and m0 * ZoomRange.</summary>
        public const float ZoomRange = 1.5f;
        /// <summary>Degrees of room over which the local zoom eases toward what the wall asks for.</summary>
        public const float SmoothDegrees = 15f;
        /// <summary>Degrees to every side of the seat's forward the panel can hide: the largest panel's 27.5 and a
        /// margin for head movement, the same the props keep clear of.</summary>
        public const float PanelHalfDegrees = ZumiPropPlacer.PanelClearDegrees;
        /// <summary>Degrees past PanelHalfDegrees where the panel's weight has eased to nothing. The weight is one
        /// raised-cosine bump from the panel's middle out to there: a steep ramp bends the picture faster than the
        /// place's thinned triangles can follow, and straight lines in it break into steps.</summary>
        public const float PanelEaseDegrees = 8f;
        /// <summary>Degrees of picture over which the zoom up and down bends from the local zoom to the wall's.</summary>
        public const float BendDegrees = 8f;
        const float Step = 0.25f, MaxAzimuth = 150f;

        /// <summary>The core's zoom where it is in sight.</summary>
        public float m0;
        /// <summary>Degrees from the key wall's direction (right positive): the key wall's two ends, the ends of
        /// what can show, and the middle of the panel.</summary>
        public float keyLeft, keyRight, showLeft, showRight, panelAt;
        /// <summary>Where the core's two ends land, and how much of its width lands outside what the panel hides.</summary>
        public float coreLeft, coreRight, coreInSight;
        /// <summary>The smallest and the largest local zoom over the picture.</summary>
        public float zoomMin, zoomMax;
        /// <summary>Metres of wall one degree of picture covers, where the neighbouring walls are worst and best: at
        /// the picture's edge and just past the key wall's corner, before (zoom 1) and after. 0 where there is none.</summary>
        public float wallPerDegreeCornerBefore, wallPerDegreeEdgeBefore, wallPerDegreeCornerAfter, wallPerDegreeEdgeAfter;

        readonly float halfSpan, core, above, below, edgeUp;
        // per Step of picture azimuth from -halfSpan: the room azimuth it maps to, the local zoom there, and the
        // degrees from the eye's level up to the top of the wall and down to the floor line
        readonly float[] azimuth, zoom, wallUp, wallDown;
        readonly Vector2[] outline;
        readonly float wallDistance, up, down;
        readonly bool room;

        public string Summary => Invariant($"m0 {m0:F2}, key wall {keyLeft:F0}..{keyRight:F0} deg, shows {showLeft:F0}..{showRight:F0} deg, panel {panelAt - PanelHalfDegrees:F0}..{panelAt + PanelHalfDegrees:F0} deg, core {coreLeft:F0}..{coreRight:F0} deg with {coreInSight:P0} beside the panel, local zoom {zoomMin:F2}..{zoomMax:F2}, wall per picture degree at the corner {wallPerDegreeCornerBefore * 100f:F1} -> {wallPerDegreeCornerAfter * 100f:F1} cm, at the picture's edge {wallPerDegreeEdgeBefore * 100f:F1} -> {wallPerDegreeEdgeAfter * 100f:F1} cm");

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
            // the picture's upper and lower edge at full strength, inside its own soft edge over its ragged rim: it goes
            // to the top of the wall and the floor line, and the rim lands past them, where the shader cuts it
            edgeUp = Mathf.Max(vDeg / 2f - ZumiPlaces.VignetteInsetDegrees - ZumiPlaces.VignetteVerticalDegrees, 1f);
            room = shape.mode == RoomMode.Scanned && shape.outline.Length >= 3;
            wallDistance = shape.wallDistance;
            Core(hDeg, vDeg, out core, out above, out below);
            panelAt = Mathf.Atan2(Vector3.Dot(shape.ahead, shape.right), Vector3.Dot(shape.ahead, shape.forward)) * Mathf.Rad2Deg;

            if (room)
            {
                up = shape.ceilingY - shape.eye.y;
                down = shape.eye.y - shape.floorY;
                // the ground plan in the place's frame: the eye at the origin, y to the key wall, x to its right
                outline = new Vector2[shape.outline.Length];
                Vector2 eye = new(shape.eye.x, shape.eye.z), ahead = new(shape.forward.x, shape.forward.z), right = new(shape.right.x, shape.right.z);
                for (var i = 0; i < outline.Length; i++) outline[i] = new Vector2(Vector2.Dot(shape.outline[i] - eye, right), Vector2.Dot(shape.outline[i] - eye, ahead));
                Cast(0f, out var key, out _, out _);
                for (keyRight = 0f; keyRight < MaxAzimuth && Cast(keyRight + Step, out var e, out _, out _) && e == key; keyRight += Step) { }
                for (keyLeft = 0f; keyLeft > -MaxAzimuth && Cast(keyLeft - Step, out var e, out _, out _) && e == key; keyLeft -= Step) { }
                for (showRight = keyRight; showRight < MaxAzimuth && Cast(showRight + Step, out _, out _, out var q) && q >= MinSquareness; showRight += Step) { }
                for (showLeft = keyLeft; showLeft > -MaxAzimuth && Cast(showLeft - Step, out _, out _, out var q) && q >= MinSquareness; showLeft -= Step) { }
                showRight = Mathf.Max(showRight, MinShowDegrees);
                showLeft = Mathf.Min(showLeft, -MinShowDegrees);
            }
            else
            {
                // one window on the wall plane: its upper and lower edge stand in for the wall's top and the floor line
                up = shape.windowCentre.y + shape.windowHalf.y - shape.eye.y;
                down = shape.eye.y - (shape.windowCentre.y - shape.windowHalf.y);
                keyRight = showRight = Mathf.Atan2(shape.windowHalf.x, wallDistance) * Mathf.Rad2Deg;
                keyLeft = showLeft = -keyRight;
            }
            // where the core goes: the key wall, widened to what always shows
            float targetLeft = Mathf.Max(Mathf.Min(keyLeft, -MinShowDegrees), showLeft), targetRight = Mathf.Min(Mathf.Max(keyRight, MinShowDegrees), showRight);
            var centre = (targetLeft + targetRight) / 2f;
            WallSpan((keyLeft + keyRight) / 2f, out var keyUp, out var keyDown);

            var n = Mathf.CeilToInt(2f * halfSpan / Step) + 1;
            azimuth = new float[n];
            zoom = new float[n];
            wallUp = new float[n];
            wallDown = new float[n];

            // the largest zoom, up to what the wall's height allows, at which the core's two ends stay on that stretch
            float high = Mathf.Clamp(Mathf.Min(keyUp / above, keyDown / below), MinZoom, 1f), low = MinZoom;
            if (!Fits(high))
            {
                for (var i = 0; i < 20; i++)
                {
                    var middle = (low + high) / 2f;
                    if (Fits(middle)) low = middle;
                    else high = middle;
                }
                high = low;
            }
            m0 = high;
            March(m0, true);
            for (var i = 0; i < n; i++) WallSpan(azimuth[i], out wallUp[i], out wallDown[i]);

            if (room)
            {
                // the same two places with no warp: the picture's own degrees on the room
                if (keyRight + Step < halfSpan && Cast(keyRight + Step, out _, out var r0, out var q0)) wallPerDegreeCornerBefore = r0 / Mathf.Max(q0, 0.02f) * Mathf.Deg2Rad;
                if (keyRight + Step < halfSpan && Cast(halfSpan, out _, out var r1, out var q1)) wallPerDegreeEdgeBefore = r1 / Mathf.Max(q1, 0.02f) * Mathf.Deg2Rad;
            }

            bool Fits(float m)
            {
                March(m, false);
                return coreLeft >= targetLeft - 1e-3f && coreRight <= targetRight + 1e-3f;
            }

            // from the picture's middle outward: every Step of picture takes the local zoom's worth of room
            void March(float m, bool whole)
            {
                var most = m * ZoomRange;
                var inSight = 0f;
                if (whole)
                {
                    var middle = Mathf.Clamp(Mathf.RoundToInt(halfSpan / Step), 0, n - 1);
                    azimuth[middle] = centre;
                    zoomMin = zoomMax = zoom[middle] = Mathf.Min(m / Visibility(centre), most);
                    wallPerDegreeCornerAfter = wallPerDegreeEdgeAfter = 0f;
                }
                foreach (var side in new[] { 1, -1 })
                {
                    float a = centre, wall = m, reference = -1f;
                    var first = true;
                    for (var k = 1; k * Step <= (whole ? halfSpan : core) + 1e-3f; k++)
                    {
                        var theta = k * Step;
                        if (theta > core + 1e-3f)
                        {
                            if (reference < 0f) reference = Density(a);
                            if (room && reference > 0f)
                            {
                                // as much picture per metre of wall as at the core's edge, within the range, eased
                                var asked = Mathf.Clamp(m * Density(a) / reference, m / ZoomRange, Mathf.Min(1f, most));
                                wall += (asked - wall) * Mathf.Min(1f, wall * Step / SmoothDegrees);
                            }
                        }
                        // little picture where the panel hides it
                        var visible = Visibility(a);
                        var z = Mathf.Min(wall / visible, most);
                        a += side * z * Step;
                        if (theta <= core + 1e-3f)
                        {
                            inSight += Step * Mathf.Clamp01((visible - 1f / ZoomRange) / (1f - 1f / ZoomRange));
                            if (side > 0) coreRight = a;
                            else coreLeft = a;
                        }
                        if (!whole) continue;
                        var at = Mathf.Clamp(Mathf.RoundToInt((side * theta + halfSpan) / Step), 0, n - 1);
                        azimuth[at] = a;
                        zoom[at] = z;
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
                coreInSight = inSight / (2f * core);
            }
        }

        /// <summary>The room azimuth (degrees from the key wall's direction) a picture azimuth is shown at.</summary>
        public float RoomAzimuth(float pictureDegrees)
        {
            var at = Mathf.Clamp((pictureDegrees + halfSpan) / Step, 0f, azimuth.Length - 1);
            int i = Mathf.Min((int)at, azimuth.Length - 2);
            return Mathf.Lerp(azimuth[i], azimuth[i + 1], at - i);
        }

        /// <summary>Across, where the place ends in the room (degrees from the key wall's direction): where what can
        /// show has faded out, or the picture's own edge (inside its ragged rim) if that comes first.</summary>
        public float EndLeft => Mathf.Max(showLeft - EdgeDegrees, RoomAzimuth(-(halfSpan - ZumiPlaces.VignetteInsetDegrees)));
        public float EndRight => Mathf.Min(showRight + EdgeDegrees, RoomAzimuth(halfSpan - ZumiPlaces.VignetteInsetDegrees));

        /// <summary>Where a point of the place's mesh (its own frame: the eye at the origin, x right, y up, z ahead)
        /// is shown: the unit direction in the same frame, the local zoom there, and how much of it shows by where it
        /// lands in the room across (1 within what can show, 0 past its soft edge), and the degrees from the eye's
        /// level up to the top of the wall and down to the floor line along where it lands: the shader cuts there per
        /// pixel, since a large triangle that crosses the wall's top would smear a fade done per vertex.</summary>
        public void Map(Vector3 p, out Vector3 direction, out float localZoom, out float shows, out Vector2 wallEdges)
        {
            var d = p.magnitude;
            var theta = Mathf.Atan2(p.x, p.z) * Mathf.Rad2Deg;
            var phi = Mathf.Asin(Mathf.Clamp(p.y / Mathf.Max(d, 1e-6f), -1f, 1f)) * Mathf.Rad2Deg;
            var at = Mathf.Clamp((theta + halfSpan) / Step, 0f, azimuth.Length - 1);
            int i = Mathf.Min((int)at, azimuth.Length - 2);
            var a = Mathf.Lerp(azimuth[i], azimuth[i + 1], at - i);
            localZoom = Mathf.Lerp(zoom[i], zoom[i + 1], at - i);
            // up and down: the local zoom over the core's height, then what brings the picture's edge to the wall's
            float inner = phi >= 0f ? above : below, reach = Mathf.Abs(phi);
            wallEdges = new Vector2(Mathf.Lerp(wallUp[i], wallUp[i + 1], at - i), Mathf.Lerp(wallDown[i], wallDown[i + 1], at - i));
            var wall = phi >= 0f ? wallEdges.x : wallEdges.y;
            // the zoom bends from the local zoom to the wall's over BendDegrees, not at a corner: a kink there would
            // show as a crease along every large triangle that straddles it
            var stretch = Mathf.Max(edgeUp - inner - BendDegrees / 2f, 1f);
            var outer = Mathf.Clamp((wall - localZoom * edgeUp) / stretch + localZoom, localZoom / ZoomRange, localZoom * ZoomRange);
            var beyond = reach - inner;
            var bent = beyond <= 0f ? 0f : beyond < BendDegrees ? beyond * beyond / (2f * BendDegrees) : beyond - BendDegrees / 2f;
            var elevation = localZoom * reach + (outer - localZoom) * bent;
            var e = Mathf.Clamp(Mathf.Sign(phi) * elevation, -89f, 89f) * Mathf.Deg2Rad;
            var ar = a * Mathf.Deg2Rad;
            direction = new Vector3(Mathf.Sin(ar) * Mathf.Cos(e), Mathf.Sin(e), Mathf.Cos(ar) * Mathf.Cos(e));
            var past = Mathf.Max(a - showRight, showLeft - a);
            var u = 1f - Mathf.Clamp01(past / EdgeDegrees);
            shows = u * u * (3f - 2f * u);
        }

        // how much of a room azimuth the panel leaves in sight: the share of the wall's height there that it does
        // not cover, 1 outside the panel's width; never under 1 / ZoomRange, the most the zoom can answer
        float Visibility(float a)
        {
            var x = Mathf.Abs(a - panelAt) / (PanelHalfDegrees + PanelEaseDegrees);
            if (x >= 1f) return 1f;
            var inside = 0.5f * (1f + Mathf.Cos(Mathf.PI * x));
            WallSpan(a, out var over, out var under);
            var open = 1f - (Mathf.Min(over, PanelHalfDegrees) + Mathf.Min(under, PanelHalfDegrees)) / Mathf.Max(over + under, 1e-3f);
            return Mathf.Max(1f - inside * (1f - open), 1f / ZoomRange);
        }

        // along a room azimuth: degrees from the eye's level up to the top of the wall and down to the floor line
        void WallSpan(float a, out float over, out float under)
        {
            over = under = 0f;
            if (!Cast(a, out _, out var r, out _)) return;
            over = Mathf.Atan2(up, r) * Mathf.Rad2Deg;
            under = Mathf.Atan2(down, r) * Mathf.Rad2Deg;
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
