using System;
using System.Collections.Generic;
using UnityEngine;

namespace Zumi
{
    /// <summary>
    /// Where a place's props stand in the reader's room. The file gives each prop the kind of surface it rests on, its
    /// height and its box, never a position; this is the rule that finds one. The same room and seat always give the
    /// same answer: nothing here is random and every search runs in a fixed order.
    ///
    /// A prop's footprint is the circle as wide as its box's wider side. It may stand where that circle lies wholly on a surface and
    /// touches none of: the scanned furniture on that surface, another prop, the seat (SeatRadius around it), the
    /// reader's way from the seat to the panel (PathHalfWidth to either side), and the panel's view: the cone from the
    /// seat's eye PanelClearDegrees around its forward out to PanelDepth, unless the prop's top stays below that cone.
    /// It must be in view: within MaxYawDegrees of the seat's forward and MaxPitchDegrees below the eye, and in the
    /// space the reader looks through, ahead of the seat and short of the window's plane: between the reader and the
    /// frames or between the frames and the place, never beyond the window or out at the sides. Of the spots left, the
    /// one whose bearing from the seat is nearest the edge of the panel's view (PanelClearDegrees) wins, so props flank
    /// the panel:
    ///   floor  at the foot of a wall (without a room: of the wall plane the place stands on, under the window's
    ///          sides), then as near the key wall as possible; in a scanned room whose walls are all taken, on the
    ///          open floor by the same ranking
    ///   table  on a scanned table top, then as near the seat as possible
    ///   shelf  the same on a scanned storage top
    /// Only furniture stands on the reader's floor (owner, 2026-11-16). Furniture stands on a surface of its own kind
    /// when one has room for it, and otherwise switches to another kind: a floor piece to a table top then a shelf top.
    /// Anything else rests on a real table or shelf top (its own kind first, then the other; a floor prop that is not
    /// furniture, a potted plant, tries a table then a shelf), never on the window's sill: a prop in the hole broke the
    /// place's drawing (owner, 2026-11-16). A prop that is not furniture and finds no free table or shelf floats
    /// FloatLift above a free floor spot, found as a floor piece's is, bobbing gently over a soft shadow (owner,
    /// 2026-11-16). No prop comes within PortalClearance of the window (its hole, its reveal, the wall round it, the
    /// space in front of it). A prop with nowhere at all is not shown, and the result says why.
    /// </summary>
    public static class ZumiPropPlacer
    {
        /// <summary>Metres around the seat nothing stands in.</summary>
        public const float SeatRadius = 0.45f;
        /// <summary>Metres to either side of the line from the seat to the panel that stay free.</summary>
        public const float PathHalfWidth = 0.45f;
        /// <summary>Degrees around the seat's forward kept clear of props: the panel's 27.5 and a margin.</summary>
        public const float PanelClearDegrees = 32f;
        /// <summary>Metres from the seat that cone is kept clear to: the panel's layers lie 1 to 3 m away. Farther off a
        /// prop may stand behind the panel, which then covers part of it as it covers the place.</summary>
        public const float PanelDepth = 3f;
        /// <summary>A prop stands within this many degrees of the seat's forward (inside the headset's view looking at
        /// the panel), with its middle no more than MaxPitchDegrees below the eye.</summary>
        public const float MaxYawDegrees = 50f, MaxPitchDegrees = 45f;
        /// <summary>Metres between two props, and between a prop and furniture.</summary>
        public const float PropGap = 0.05f;
        /// <summary>Metres between a floor prop and the wall it stands by.</summary>
        public const float WallGap = 0.05f;
        /// <summary>Metres between a prop and the edge of the top it stands on.</summary>
        public const float EdgeGap = 0.02f;
        /// <summary>What a spot behind the panel costs, in the degrees spots are ranked by: it is taken only when no
        /// spot beside the panel is within that many degrees of bearing (or their worth in distance).</summary>
        public const float BehindPanelCost = 30f;
        /// <summary>Metres every prop keeps from the window: the hole, the reveal and the wall round it, and the space
        /// in front of it. A prop in or at the hole broke the place's drawing (owner, 2026-11-16).</summary>
        public const float PortalClearance = 0.3f;
        /// <summary>Metres a floating prop's bottom hovers over the floor.</summary>
        public const float FloatLift = 0.15f;
        const float FloorStep = 0.1f, OpenFloorStep = 0.2f, TopStep = 0.05f, VirtualWallReach = 4f;

        public sealed class Request
        {
            public string name;
            public SurfaceKind kind;
            /// <summary>Only furniture may stand on the floor; anything else floats over it when no top has room.</summary>
            public bool furniture;
            /// <summary>Metres: its footprint circle's radius, and its height.</summary>
            public float radius, height;
            /// <summary>Metres: half its box across and half front to back.</summary>
            public Vector2 half;
        }

        public sealed class Result
        {
            public string name;
            public bool placed;
            /// <summary>Why it is not placed; null when it is.</summary>
            public string reason;
            public SurfaceKind on;
            public string surface;
            /// <summary>Where the point under its middle rests, in world space.</summary>
            public Vector3 position;
            /// <summary>Its turn about the vertical: the side the place's view shows faces the seat.</summary>
            public Quaternion rotation;
            public float radius;
            /// <summary>It found no top and hovers FloatLift over the floor (position is under its bottom, in the air).</summary>
            public bool floating;
        }

        /// <summary>One result per request, in the requests' order.</summary>
        public static List<Result> Place(ZumiRoom room, Vector3 seatEye, Vector3 seatForward, IReadOnlyList<Request> requests)
        {
            var order = new List<int>();
            for (var i = 0; i < requests.Count; i++) order.Add(i);
            order.Sort((a, b) =>
            {
                var byKind = requests[a].kind.CompareTo(requests[b].kind);
                if (byKind != 0) return byKind;
                var bySize = requests[b].radius.CompareTo(requests[a].radius);
                return bySize != 0 ? bySize : string.CompareOrdinal(requests[a].name, requests[b].name);
            });

            var results = new Result[requests.Count];
            var standing = new List<Result>();
            Vector2 seat = ZumiRoom.Flat(seatEye), ahead = ZumiRoom.Flat(seatForward).normalized;
            foreach (var index in order)
            {
                var request = requests[index];
                var result = results[index] = new Result { name = request.name, radius = request.radius };
                var tried = new List<string>();
                // its own kind, then the others
                foreach (var kind in request.furniture ? Kinds(request.kind) : Tops(request.kind))
                {
                    if (result.placed) break;
                    tried.Add(kind.ToString().ToLowerInvariant());
                    if (!Best(room, kind, request, seatEye, seat, ahead, standing, out var surface, out var at)) continue;
                    result.placed = true;
                    result.on = kind;
                    result.surface = surface.name;
                    result.position = new Vector3(at.x, surface.height, at.y);
                    var away = at - seat;
                    result.rotation = Quaternion.LookRotation(new Vector3(away.x, 0f, away.y));
                    standing.Add(result);
                }
                // not furniture, and no top had room: it floats over the floor
                if (!result.placed && !request.furniture)
                {
                    tried.Add("floor to float over");
                    if (Best(room, SurfaceKind.Floor, request, seatEye, seat, ahead, standing, out var floor, out var spot, FloatLift))
                    {
                        result.placed = result.floating = true;
                        result.on = SurfaceKind.Floor;
                        result.surface = floor.name;
                        result.position = new Vector3(spot.x, floor.height + FloatLift, spot.y);
                        var away = spot - seat;
                        result.rotation = Quaternion.LookRotation(new Vector3(away.x, 0f, away.y));
                        standing.Add(result);
                    }
                }
                if (result.placed) continue;
                result.reason = $"no {string.Join(" or ", tried)} in view with room for it, clear of the window";
            }
            return new List<Result>(results);
        }

        /// <summary>Whether a prop's box (footprint circle of radius round p, from height up by its height) comes within
        /// PortalClearance of any window quad: the hole, the reveal behind it and the wall round it.</summary>
        public static bool NearPortal(ZumiRoom room, Vector2 p, float bottom, float radius, float height)
        {
            foreach (var q in room.Portals)
            {
                var from = p - ZumiRoom.Flat(q.centre);
                var normal = ZumiRoom.Flat(q.normal).normalized;
                var across = ZumiRoom.Flat(q.right).normalized;
                // in front of the wall by less than the clearance (or behind it, where the reveal is)
                if (Vector2.Dot(from, normal) - radius >= PortalClearance) continue;
                if (Mathf.Abs(Vector2.Dot(from, across)) - radius >= q.size.x / 2f + PortalClearance) continue;
                float low = q.centre.y - q.size.y / 2f - PortalClearance, high = q.centre.y + q.size.y / 2f + PortalClearance;
                if (bottom + height <= low || bottom >= high) continue;
                return true;
            }
            return false;
        }

        // what is not furniture rests on a top: its own kind first, then the other
        static SurfaceKind[] Tops(SurfaceKind own) => own == SurfaceKind.Shelf
            ? new[] { SurfaceKind.Shelf, SurfaceKind.Table }
            : new[] { SurfaceKind.Table, SurfaceKind.Shelf };

        static SurfaceKind[] Kinds(SurfaceKind own) => own switch
        {
            SurfaceKind.Shelf => new[] { SurfaceKind.Shelf, SurfaceKind.Table, SurfaceKind.Floor },
            SurfaceKind.Table => new[] { SurfaceKind.Table, SurfaceKind.Shelf, SurfaceKind.Floor },
            _ => new[] { SurfaceKind.Floor, SurfaceKind.Table, SurfaceKind.Shelf },
        };

        static bool Best(ZumiRoom room, SurfaceKind kind, Request request, Vector3 eye, Vector2 seat, Vector2 ahead,
                         List<Result> standing, out RoomSurface on, out Vector2 at, float lift = 0f)
        {
            on = null;
            at = default;
            var best = float.PositiveInfinity;
            var shape = room.Shape;
            Vector2 wallAhead = ZumiRoom.Flat(shape.forward), eyeFlat = ZumiRoom.Flat(shape.eye);
            // a scanned floor is tried twice: at the foot of its walls, and only if nothing is free there, in the open
            for (var open = 0; open < 2 && on == null; open++)
                foreach (var surface in room.Surfaces)
                {
                    if (surface.kind != kind || (open == 1 && surface.polygon == null)) continue;
                    foreach (var p in open == 1 ? OpenFloor(surface) : Candidates(shape, surface, request))
                    {
                        if (!Free(room, surface, p, request, eye, seat, ahead, standing, lift, out var yaw, out var behindPanel)) continue;
                        // beside the panel as the seat sees it rather than behind it; then by the key wall (floor) or
                        // near the seat (tops)
                        var cost = Mathf.Abs(yaw - PanelClearDegrees) + (behindPanel ? BehindPanelCost : 0f) + (kind == SurfaceKind.Floor
                            ? 10f * Mathf.Max(shape.wallDistance - Vector2.Dot(p - eyeFlat, wallAhead), 0f)
                            : 5f * (p - seat).magnitude);
                        if (cost >= best) continue;
                        best = cost;
                        on = surface;
                        at = p;
                    }
                }
            return on != null;
        }

        static IEnumerable<Vector2> OpenFloor(RoomSurface floor)
        {
            for (var x = -floor.half.x; x <= floor.half.x; x += OpenFloorStep)
                for (var y = -floor.half.y; y <= floor.half.y; y += OpenFloorStep)
                    yield return floor.centre + floor.axis * x + ZumiRoom.Perp(floor.axis) * y;
        }

        static IEnumerable<Vector2> Candidates(RoomShape shape, RoomSurface surface, Request request)
        {
            var radius = request.radius;
            if (surface.kind != SurfaceKind.Floor)
            {
                var reach = surface.half - Vector2.one * (radius + EdgeGap);
                if (reach.x < 0f || reach.y < 0f) yield break;
                for (var x = -reach.x; x <= reach.x + 1e-4f; x += TopStep)
                    for (var y = -reach.y; y <= reach.y + 1e-4f; y += TopStep)
                        yield return surface.centre + surface.axis * x + ZumiRoom.Perp(surface.axis) * y;
                yield break;
            }
            // off a real wall by its box's corner, whichever way it turns to face the seat; the wall plane without a
            // room is nothing a corner can go through
            var inset = (surface.polygon != null ? request.half.magnitude : radius) + WallGap;
            if (surface.polygon == null)
            {
                // no room: along the foot of the wall plane the place stands on
                Vector2 ahead = ZumiRoom.Flat(shape.forward), across = ZumiRoom.Flat(shape.right);
                var foot = ZumiRoom.Flat(shape.eye) + ahead * (shape.wallDistance - inset);
                for (var k = 0; k * FloorStep <= VirtualWallReach; k++)
                {
                    yield return foot + across * (k * FloorStep);
                    if (k > 0) yield return foot - across * (k * FloorStep);
                }
                yield break;
            }
            var outline = surface.polygon;
            for (int i = 0, j = outline.Length - 1; i < outline.Length; j = i++)
            {
                Vector2 a = outline[j], edge = outline[i] - a;
                var length = edge.magnitude;
                if (length < 2f * inset) continue;
                var along = edge / length;
                var inward = ZumiRoom.Perp(along);
                if (!ZumiRoom.InPolygon(outline, a + along * (length / 2f) + inward * 0.01f)) inward = -inward;
                for (var u = inset; u <= length - inset + 1e-4f; u += FloorStep) yield return a + along * u + inward * inset;
            }
        }

        static bool Free(ZumiRoom room, RoomSurface surface, Vector2 p, Request request, Vector3 eye, Vector2 seat, Vector2 ahead,
                         List<Result> standing, float lift, out float yaw, out bool behindPanel)
        {
            var bottom = surface.height + lift;
            yaw = 0f;
            behindPanel = false;
            var radius = request.radius;
            // a hair under the gap the candidates are generated at, so a prop set against a wall is not refused by rounding
            if (!surface.Holds(p, radius + (surface.kind == SurfaceKind.Floor ? WallGap : EdgeGap) - 1e-3f)) return false;
            if (room.Blocked(surface, p, radius + PropGap)) return false;
            var from = p - seat;
            var distance = from.magnitude;
            if (distance < SeatRadius + radius) return false;
            // its box, turned to face the seat, has all four corners on the surface too
            Vector2 back = from / distance, side = ZumiRoom.Perp(back);
            for (var c = 0; c < 4; c++)
                if (!surface.Holds(p + side * ((c & 1) == 0 ? -request.half.x : request.half.x) + back * ((c & 2) == 0 ? -request.half.y : request.half.y), 0f)) return false;
            var panel = seat + ahead * ZumiPanelPresenter.ReadingDistance;
            var onPath = Mathf.Clamp01(Vector2.Dot(from, panel - seat) / (panel - seat).sqrMagnitude);
            if ((seat + (panel - seat) * onPath - p).magnitude < PathHalfWidth + radius) return false;
            yaw = Vector2.Angle(from, ahead);
            if (yaw > MaxYawDegrees) return false;
            // ahead of the seat and short of the window's plane, with its box
            var shape = room.Shape;
            if (Vector2.Dot(from, ahead) < SeatRadius) return false;
            if (Vector2.Dot(p - ZumiRoom.Flat(shape.eye), ZumiRoom.Flat(shape.forward)) > shape.wallDistance - radius - WallGap) return false;
            if (NearPortal(room, p, bottom, request.half.magnitude, request.height)) return false;
            if (Mathf.Atan2(bottom + request.height / 2f - eye.y, distance) * Mathf.Rad2Deg < -MaxPitchDegrees) return false;
            var edgeYaw = yaw - Mathf.Asin(Mathf.Min(1f, radius / distance)) * Mathf.Rad2Deg;
            var topPitch = Mathf.Atan2(bottom + request.height - eye.y, Mathf.Max(distance - radius, 0.05f)) * Mathf.Rad2Deg;
            behindPanel = edgeYaw < PanelClearDegrees && topPitch > -PanelClearDegrees;
            if (behindPanel && distance - radius < PanelDepth) return false;
            foreach (var other in standing)
                if ((ZumiRoom.Flat(other.position) - p).magnitude < radius + other.radius + PropGap) return false;
            return true;
        }
    }
}
