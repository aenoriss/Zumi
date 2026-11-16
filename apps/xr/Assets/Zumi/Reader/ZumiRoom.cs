using System.Collections.Generic;
using System.Threading.Tasks;
using Meta.XR.MRUtilityKit;
using UnityEngine;
using UnityEngine.XR;
using static System.FormattableString;

namespace Zumi
{
    public enum RoomMode { None, Scanned }
    public enum SurfaceKind { Floor, Table, Shelf }

    /// <summary>A flat, level surface things can stand on: a rectangle on the ground plan (or the floor's outline) at a height.</summary>
    public sealed class RoomSurface
    {
        public SurfaceKind kind;
        /// <summary>The scene label it came from (FLOOR, TABLE, STORAGE) and its number among them.</summary>
        public string name;
        /// <summary>World y of the surface.</summary>
        public float height;
        /// <summary>On the ground plan (x, z): the rectangle's middle, the unit direction of its first side, its half sizes.</summary>
        public Vector2 centre, axis, half;
        /// <summary>A scanned floor: the room's outline, which the rectangle only bounds. Null otherwise.</summary>
        public Vector2[] polygon;
        /// <summary>The floor without a scanned room: it has no edge.</summary>
        public bool unbounded;
        /// <summary>Square metres; the free part is what no furniture stands on. Infinity for an unbounded floor.</summary>
        public float area, freeArea;
        internal int box = -1;

        /// <summary>How far outside the surface a point of the ground plan is; 0 on it.</summary>
        public float Outside(Vector2 p)
        {
            if (unbounded) return 0f;
            if (polygon != null) return ZumiRoom.InPolygon(polygon, p) ? 0f : ZumiRoom.EdgeDistance(polygon, p);
            var d = p - centre;
            var over = new Vector2(Mathf.Abs(Vector2.Dot(d, axis)) - half.x, Mathf.Abs(Vector2.Dot(d, ZumiRoom.Perp(axis))) - half.y);
            return new Vector2(Mathf.Max(over.x, 0f), Mathf.Max(over.y, 0f)).magnitude;
        }

        /// <summary>Whether a disc of that radius lies wholly on the surface.</summary>
        public bool Holds(Vector2 p, float radius)
        {
            if (unbounded) return true;
            if (polygon != null) return ZumiRoom.InPolygon(polygon, p) && ZumiRoom.EdgeDistance(polygon, p) >= radius;
            var d = p - centre;
            return Mathf.Abs(Vector2.Dot(d, axis)) <= half.x - radius && Mathf.Abs(Vector2.Dot(d, ZumiRoom.Perp(axis))) <= half.y - radius;
        }
    }

    /// <summary>A piece of scanned furniture as a box: its footprint on the ground plan and the heights it spans.</summary>
    public struct RoomBox
    {
        public string label;
        public Vector3 centre, size;
        public Quaternion rotation;
        public Vector2 footCentre, footAxis, footHalf;
        public float bottom, top;

        /// <summary>Metres from a ground-plan point to the footprint; 0 inside it.</summary>
        public float Distance(Vector2 p)
        {
            var d = p - footCentre;
            var over = new Vector2(Mathf.Abs(Vector2.Dot(d, footAxis)) - footHalf.x, Mathf.Abs(Vector2.Dot(d, ZumiRoom.Perp(footAxis))) - footHalf.y);
            return new Vector2(Mathf.Max(over.x, 0f), Mathf.Max(over.y, 0f)).magnitude;
        }
    }

    /// <summary>A flat rectangle of the room a place is seen through: a wall, the ceiling, or the window that stands in for them.</summary>
    public struct RoomQuad
    {
        public string name;
        /// <summary>Its middle; normal points into the room.</summary>
        public Vector3 centre, normal, right, up;
        public Vector2 size;
    }

    /// <summary>
    /// What a place is fitted to, as plain numbers (read off the main thread): where the seat's eye is, which way the key
    /// wall lies, and how far the room reaches from the eye in any direction.
    /// </summary>
    public sealed class RoomShape
    {
        public RoomMode mode;
        public int serial;
        public Vector3 eye;
        /// <summary>Level, from the eye to the key wall and square to it; right is to the right of someone facing it.</summary>
        public Vector3 forward, right;
        /// <summary>Metres from the eye to the key wall along forward.</summary>
        public float wallDistance;
        public float floorY, ceilingY;
        /// <summary>Scanned: the walls' corners on the ground plan, in order.</summary>
        public Vector2[] outline;
        /// <summary>No room: the window on the wall plane, its middle and its half sizes across and up.</summary>
        public Vector3 windowCentre;
        public Vector2 windowHalf;

        /// <summary>Whether a line of sight from the eye along a unit direction leaves the room through an opening a
        /// place is seen through: any direction in a scanned room, only the window's without one.</summary>
        public bool Through(Vector3 dir)
        {
            if (mode == RoomMode.Scanned) return true;
            var t = Distance(dir);
            if (float.IsInfinity(t)) return false;
            var at = eye + dir * t - windowCentre;
            return Mathf.Abs(Vector3.Dot(at, right)) <= windowHalf.x && Mathf.Abs(at.y) <= windowHalf.y;
        }

        /// <summary>Metres from the eye to the room's edge along a unit direction: its walls, floor and ceiling when it is
        /// scanned, the one wall plane otherwise. Infinity where the direction meets none.</summary>
        public float Distance(Vector3 dir) => Distance(dir, out _);

        /// <summary>The same, and whether that edge is a wall (without a room: the wall plane) rather than the floor or
        /// the ceiling.</summary>
        public float Distance(Vector3 dir, out bool wall)
        {
            wall = false;
            if (mode == RoomMode.None)
            {
                var toward = Vector3.Dot(dir, forward);
                wall = toward > 1e-4f;
                return wall ? wallDistance / toward : float.PositiveInfinity;
            }
            var t = float.PositiveInfinity;
            if (dir.y > 1e-6f) t = (ceilingY - eye.y) / dir.y;
            else if (dir.y < -1e-6f) t = (floorY - eye.y) / dir.y;
            Vector2 o = new(eye.x, eye.z), d = new(dir.x, dir.z);
            for (int i = 0, j = outline.Length - 1; i < outline.Length; j = i++)
            {
                Vector2 a = outline[j], e = outline[i] - a;
                var cross = d.x * e.y - d.y * e.x;
                if (Mathf.Abs(cross) < 1e-8f) continue;
                var along = ((a.x - o.x) * e.y - (a.y - o.y) * e.x) / cross;
                var on = ((a.x - o.x) * d.y - (a.y - o.y) * d.x) / cross;
                if (along > 1e-4f && on >= 0f && on <= 1f && along < t)
                {
                    t = along;
                    wall = true;
                }
            }
            return t;
        }
    }

    /// <summary>
    /// The reader's room, for every part that shows something in it. It answers: is there a scanned room (Scanned) or
    /// not (None: no scan, permission refused, the load failed; a normal outcome); where the seat is; which wall is the
    /// key wall, the nearest one behind the panel as the seat sees it: on the seat's forward, or failing that on the
    /// nearest bearing to either side, and facing the seat (without a room, or with no such wall: a wall plane
    /// VirtualWallDistance ahead of the seat); how far the room reaches (RoomShape); what a place is seen through (the
    /// walls ahead and the ceiling, never the floor; without a room one window); the furniture as boxes; and the level surfaces things can
    /// stand on, by kind. It is worked out again when the seat is taken again and when the scanned room arrives,
    /// changes or goes. It also asks MRUK for the room: from the headset when one is on (never starting the system's
    /// room scan by itself), from one of MRUK's sample rooms in the editor without a headset.
    /// </summary>
    [RequireComponent(typeof(ZumiSeat))]
    public class ZumiRoom : MonoBehaviour
    {
        /// <summary>Without a scanned room: metres from the seat's eye to the wall plane the place stands on, 1 m behind
        /// the panel.</summary>
        public const float VirtualWallDistance = 2.0f;
        /// <summary>Without a scanned room: the window on that plane, in metres. 3.4 by 2.1 at 2 m is 81 by 55 degrees:
        /// the 55-degree panel leaves 13 degrees of it showing on either side.</summary>
        public const float WindowWidth = 3.4f, WindowHeight = 2.1f;
        /// <summary>The window's lower edge is never nearer the floor than this.</summary>
        public const float WindowSill = 0.2f;
        /// <summary>A table or storage top counts as a surface between these heights above the floor.</summary>
        public const float MinTopHeight = 0.3f, MaxTableHeight = 1.3f, MaxShelfHeight = 1.8f;
        /// <summary>A wall this many degrees to either side of the seat's forward can still be the key wall.</summary>
        public const float KeyWallSweepDegrees = 60f;
        /// <summary>The key wall faces the seat at least this much: the cosine of the angle between the seat's forward
        /// and the way into the wall (0.5: within 60 degrees).</summary>
        public const float MinKeyWallFacing = 0.5f;
        const float FreeAreaCell = 0.05f;

        [Tooltip("In the editor without a headset: which of MRUK's sample rooms stands in for the scanned room; -1: none (the no-room mode)")]
        [SerializeField] int editorRoom = 1;

        ZumiSeat seat;
        int signature = int.MinValue;
        bool loading;
        string loadNote;
        readonly List<RoomSurface> surfaces = new();
        readonly List<RoomBox> boxes = new();
        readonly List<RoomQuad> portals = new();
        readonly List<string> surfaceLines = new();

        public RoomMode Mode { get; private set; }
        /// <summary>Why there is no scanned room; null when there is one.</summary>
        public string ModeReason { get; private set; } = "the seat is not taken";
        /// <summary>How many times the room was worked out; 0 before the seat is taken. Whatever is fitted to the room
        /// is fitted again when this changes.</summary>
        public int Serial { get; private set; }
        public RoomShape Shape { get; private set; }
        /// <summary>The key wall: the foot of the seat eye's perpendicular on it, and its normal, into the room.</summary>
        public Vector3 KeyWallPoint { get; private set; }
        public Vector3 KeyWallNormal { get; private set; }
        public float KeyWallDistance => Shape?.wallDistance ?? 0f;
        public string KeyWallName { get; private set; }
        /// <summary>Metres from the seat's eye to the key wall along the seat's own forward: under 1 the panel is in the wall.</summary>
        public float KeyWallAhead { get; private set; }
        public float FloorY => Shape?.floorY ?? 0f;
        /// <summary>The room's box (a scanned room's walls, floor and ceiling); empty without one.</summary>
        public Bounds Bounds { get; private set; }
        public IReadOnlyList<RoomSurface> Surfaces => surfaces;
        public IReadOnlyList<RoomBox> Boxes => boxes;
        public IReadOnlyList<RoomQuad> Portals => portals;
        /// <summary>The lowest point of anything a place is seen through, in metres above the floor.</summary>
        public float PortalFloorClearance { get; private set; }

        // ---- read-only state for tests and tools ---------------------------------------------------------------
        public string ModeName => Mode.ToString();
        public int PortalCount => portals.Count;
        /// <summary>Openings that lie flat and face up, as a floor would: always 0, a place is never seen through the floor.</summary>
        public int FloorOpenings
        {
            get
            {
                var n = 0;
                foreach (var q in portals) if (q.normal.y > 0.7f) n++;
                return n;
            }
        }
        public int FloorCount => Count(SurfaceKind.Floor);
        public int TableCount => Count(SurfaceKind.Table);
        public int ShelfCount => Count(SurfaceKind.Shelf);
        /// <summary>One line per surface: "table TABLE 1 h 0.74 area 0.52 free 0.52".</summary>
        public IReadOnlyList<string> SurfaceLines => surfaceLines;

        int Count(SurfaceKind kind)
        {
            var n = 0;
            foreach (var s in surfaces) if (s.kind == kind) n++;
            return n;
        }

        async void Start()
        {
            seat = GetComponent<ZumiSeat>();
            var mruk = MRUK.Instance;
            if (!mruk)
            {
                loadNote = "no MRUK in the scene";
                return;
            }
            // MRUK set to load by itself is left to it
            if (mruk.SceneSettings.LoadSceneOnStartup) return;
            if (!XRSettings.isDeviceActive)
            {
                LoadEditorRoom(editorRoom);
                return;
            }
            loading = true;
#if UNITY_ANDROID && !UNITY_EDITOR
            if (!await ScenePermission())
            {
                loading = false;
                loadNote = "the scene permission was refused";
                return;
            }
#endif
            // no scan is an answer, not a reason to send the reader off to scan the room
            var result = await mruk.LoadSceneFromDevice(requestSceneCaptureIfNoDataFound: false);
            loading = false;
            loadNote = result == MRUK.LoadDeviceResult.Success ? null : $"the headset has no room: {result}";
        }

#if UNITY_ANDROID && !UNITY_EDITOR
        static Task<bool> ScenePermission()
        {
            if (UnityEngine.Android.Permission.HasUserAuthorizedPermission(OVRPermissionsRequester.ScenePermission)) return Task.FromResult(true);
            var answer = new TaskCompletionSource<bool>();
            var callbacks = new UnityEngine.Android.PermissionCallbacks();
            callbacks.PermissionGranted += _ => answer.TrySetResult(true);
            callbacks.PermissionDenied += _ => answer.TrySetResult(false);
            UnityEngine.Android.Permission.RequestUserPermission(OVRPermissionsRequester.ScenePermission, callbacks);
            return answer.Task;
        }
#endif

        /// <summary>Loads one of MRUK's sample rooms in place of a scanned room; a negative index takes the room away
        /// (the no-room mode). For the editor, tools and tests: on the headset the room is the scanned one.</summary>
        public async void LoadEditorRoom(int index)
        {
            var mruk = MRUK.Instance;
            if (!mruk) return;
            var prefabs = mruk.SceneSettings.RoomPrefabs;
            if (index < 0 || prefabs == null || index >= prefabs.Length)
            {
                mruk.ClearScene();
                loadNote = "no room was asked for";
                return;
            }
            loading = true;
            var result = await mruk.LoadSceneFromPrefab(prefabs[index]);
            loading = false;
            loadNote = result == MRUK.LoadDeviceResult.Success ? null : $"sample room {index}: {result}";
        }

        void Update()
        {
            if (!seat.Taken) return;
            var now = Signature(out var room);
            if (now == signature) return;
            signature = now;
            Evaluate(room);
        }

        // changes when the seat is taken again and when the scanned room arrives, changes or goes
        int Signature(out MRUKRoom room)
        {
            room = null;
            var mruk = MRUK.Instance;
            if (mruk && mruk.IsInitialized && mruk.Rooms.Count > 0) room = mruk.GetCurrentRoom();
            unchecked
            {
                var h = seat.Seatings * 397 + (loading ? 1 : 0);
                if (room) h = h * 31 + room.GetHashCode() + room.Anchors.Count * 7919;
                return h;
            }
        }

        void Evaluate(MRUKRoom room)
        {
            Serial++;
            surfaces.Clear();
            boxes.Clear();
            portals.Clear();
            Vector3 eye = seat.Position, ahead = seat.Forward;
            string why = null;
            if (!room) why = loading ? "the room is loading" : loadNote ?? "no scanned room";
            else if (!Scanned(room, eye, ahead, out why))
            {
                surfaces.Clear();
                boxes.Clear();
                portals.Clear();
            }
            if (why != null) Virtual(eye, ahead);
            Mode = why == null ? RoomMode.Scanned : RoomMode.None;
            ModeReason = why;
            Shape.mode = Mode;
            Shape.serial = Serial;

            PortalFloorClearance = float.PositiveInfinity;
            foreach (var q in portals)
                PortalFloorClearance = Mathf.Min(PortalFloorClearance, q.centre.y - Mathf.Abs(q.up.y) * q.size.y / 2f - Mathf.Abs(q.right.y) * q.size.x / 2f - Shape.floorY);
            surfaceLines.Clear();
            foreach (var s in surfaces)
                surfaceLines.Add(Invariant($"{s.kind.ToString().ToLowerInvariant()} {s.name} h {s.height - Shape.floorY:F2} area {s.area:F2} free {s.freeArea:F2}"));
            Debug.Log(Invariant($"[Zumi] room: {Mode}{(why != null ? $" ({why})" : "")}, key wall {KeyWallName} {KeyWallDistance:F2} m away, {portals.Count} openings, floor {FloorCount} table {TableCount} shelf {ShelfCount}, {boxes.Count} boxes"));
        }

        // ---- a scanned room ------------------------------------------------------------------------------------

        bool Scanned(MRUKRoom room, Vector3 eye, Vector3 ahead, out string why)
        {
            why = null;
            // one floor and one ceiling: the scan's simple model, the only one MRUK loads today
            MRUKAnchor floorAnchor = room.FloorAnchors.Count > 0 ? room.FloorAnchors[0] : null, ceilingAnchor = room.CeilingAnchors.Count > 0 ? room.CeilingAnchors[0] : null;
            if (!floorAnchor || !ceilingAnchor)
            {
                why = "the scanned room has no floor or ceiling";
                return false;
            }
            var corners = room.GetRoomOutline();
            if (corners == null || corners.Count < 3)
            {
                why = "the scanned room has no outline";
                return false;
            }
            var outline = new Vector2[corners.Count];
            for (var i = 0; i < outline.Length; i++) outline[i] = Flat(corners[i]);
            float floorY = floorAnchor.transform.position.y, ceilingY = ceilingAnchor.transform.position.y;
            if (!InPolygon(outline, Flat(eye)) || eye.y <= floorY || eye.y >= ceilingY)
            {
                why = "the seat is outside the scanned room";
                return false;
            }

            // the key wall: the nearest wall on the seat's forward, or failing that on the nearest bearing to either side
            MRUKAnchor keyWall = null;
            for (var step = 0; keyWall == null && step * 5f <= KeyWallSweepDegrees; step++)
                foreach (var sign in new[] { 1f, -1f })
                {
                    if (keyWall != null || (step == 0 && sign < 0f)) continue;
                    var dir = Quaternion.AngleAxis(sign * step * 5f, Vector3.up) * ahead;
                    var nearest = float.PositiveInfinity;
                    foreach (var wall in room.WallAnchors)
                    {
                        // a wall the seat only grazes is not one a place can be watched on
                        if (!IsWall(wall) || Vector3.Dot(-wall.transform.forward, ahead) < MinKeyWallFacing) continue;
                        if (!WallHit(wall, eye, dir, out var t) || t >= nearest) continue;
                        nearest = t;
                        keyWall = wall;
                    }
                }
            if (keyWall == null)
            {
                why = "no wall ahead of the seat";
                return false;
            }
            var normal = Vector3.ProjectOnPlane(keyWall.transform.forward, Vector3.up).normalized;
            var distance = Vector3.Dot(keyWall.transform.position - eye, -normal);
            if (distance < 0.3f)
            {
                why = "the seat is against the wall";
                return false;
            }
            Shape = new RoomShape { eye = eye, forward = -normal, right = Vector3.Cross(Vector3.up, -normal), wallDistance = distance, floorY = floorY, ceilingY = ceilingY, outline = outline };
            KeyWallNormal = normal;
            KeyWallPoint = eye - normal * distance;
            KeyWallName = keyWall.name;
            KeyWallAhead = WallHit(keyWall, eye, ahead, out var straight) ? straight : distance / Mathf.Max(Vector3.Dot(ahead, -normal), 1e-3f);
            Bounds = room.GetRoomBounds();

            // what the place is seen through: the walls ahead of the seat's eye and the ceiling, never the floor
            foreach (var wall in room.WallAnchors)
            {
                if (!IsWall(wall)) continue;
                var quad = Quad(wall);
                var inFront = false;
                for (var c = 0; c < 4; c++)
                {
                    var corner = quad.centre + quad.right * ((c & 1) == 0 ? -0.5f : 0.5f) * quad.size.x + quad.up * ((c & 2) == 0 ? -0.5f : 0.5f) * quad.size.y;
                    inFront |= Vector3.Dot(corner - eye, Shape.forward) > 0f;
                }
                if (inFront) portals.Add(quad);
            }
            if (ceilingAnchor.PlaneRect.HasValue) portals.Add(Quad(ceilingAnchor));

            foreach (var anchor in room.Anchors)
            {
                if (!anchor.VolumeBounds.HasValue) continue;
                boxes.Add(Box(anchor));
            }

            var floor = new RoomSurface { kind = SurfaceKind.Floor, name = "FLOOR", height = floorY, polygon = outline };
            Vector2 min = outline[0], max = outline[0];
            foreach (var p in outline) { min = Vector2.Min(min, p); max = Vector2.Max(max, p); }
            floor.centre = (min + max) / 2f;
            floor.axis = Vector2.right;
            floor.half = (max - min) / 2f;
            surfaces.Add(floor);
            int tables = 0, shelves = 0;
            for (var i = 0; i < boxes.Count; i++)
            {
                var box = boxes[i];
                var up = box.top - floorY;
                var table = box.label.Contains("TABLE") && up >= MinTopHeight && up <= MaxTableHeight;
                var shelf = box.label.Contains("STORAGE") && up >= MinTopHeight && up <= MaxShelfHeight;
                if (!table && !shelf) continue;
                surfaces.Add(new RoomSurface
                {
                    kind = table ? SurfaceKind.Table : SurfaceKind.Shelf, name = table ? $"TABLE {++tables}" : $"STORAGE {++shelves}",
                    height = box.top, centre = box.footCentre, axis = box.footAxis, half = box.footHalf, box = i,
                });
            }
            foreach (var s in surfaces) Measure(s);
            return true;
        }

        // an opening the scan closed with an invisible wall is the room's edge like any wall: the place shows on it too
        static bool IsWall(MRUKAnchor anchor) =>
            anchor.PlaneRect.HasValue && anchor.HasAnyLabel(MRUKAnchor.SceneLabels.WALL_FACE | MRUKAnchor.SceneLabels.INVISIBLE_WALL_FACE);

        static RoomQuad Quad(MRUKAnchor anchor)
        {
            var rect = anchor.PlaneRect.Value;
            var t = anchor.transform;
            return new RoomQuad
            {
                name = anchor.name, centre = t.TransformPoint(rect.center.x, rect.center.y, 0f), normal = t.forward, right = t.right, up = t.up,
                size = new Vector2(rect.width * t.lossyScale.x, rect.height * t.lossyScale.y),
            };
        }

        // metres along a ray from origin to the wall's rectangle; false when it misses or leaves through its back
        static bool WallHit(MRUKAnchor wall, Vector3 origin, Vector3 dir, out float t)
        {
            var quad = Quad(wall);
            t = 0f;
            var toward = Vector3.Dot(dir, quad.normal);
            if (toward > -1e-4f) return false;
            t = Vector3.Dot(quad.centre - origin, quad.normal) / toward;
            if (t <= 0f) return false;
            var at = origin + dir * t - quad.centre;
            return Mathf.Abs(Vector3.Dot(at, quad.right)) <= quad.size.x / 2f && Mathf.Abs(Vector3.Dot(at, quad.up)) <= quad.size.y / 2f;
        }

        static RoomBox Box(MRUKAnchor anchor)
        {
            var bounds = anchor.VolumeBounds.Value;
            var t = anchor.transform;
            // the anchor's axis that stands up; the other two span the footprint
            var axes = new[] { t.right, t.up, t.forward };
            var upright = 0;
            for (var i = 1; i < 3; i++)
                if (Mathf.Abs(axes[i].y) > Mathf.Abs(axes[upright].y)) upright = i;
            int a = (upright + 1) % 3, b = (upright + 2) % 3;
            var size = Vector3.Scale(bounds.size, t.lossyScale);
            var centre = t.TransformPoint(bounds.center);
            var along = Flat(axes[a]).normalized;
            // the second side square to the first on the ground plan: a box that leans is taken as standing straight
            return new RoomBox
            {
                label = anchor.Label.ToString(), centre = centre, size = size, rotation = t.rotation,
                footCentre = Flat(centre), footAxis = along, footHalf = new Vector2(size[a], size[b]) / 2f,
                bottom = centre.y - size[upright] / 2f, top = centre.y + size[upright] / 2f,
            };
        }

        // ---- no room -------------------------------------------------------------------------------------------

        void Virtual(Vector3 eye, Vector3 ahead)
        {
            // the tracked floor: the rig's tracking origin is at floor level
            var rig = FindAnyObjectByType<OVRCameraRig>();
            var floorY = rig && rig.trackingSpace ? rig.trackingSpace.position.y : 0f;
            Shape = new RoomShape
            {
                eye = eye, forward = ahead, right = Vector3.Cross(Vector3.up, ahead), wallDistance = VirtualWallDistance,
                floorY = floorY, ceilingY = float.PositiveInfinity, outline = System.Array.Empty<Vector2>(),
            };
            KeyWallNormal = -ahead;
            KeyWallPoint = eye + ahead * VirtualWallDistance;
            KeyWallName = "virtual";
            KeyWallAhead = VirtualWallDistance;
            Bounds = default;
            var centre = KeyWallPoint;
            centre.y = Mathf.Max(eye.y, floorY + WindowSill + WindowHeight / 2f);
            Shape.windowCentre = centre;
            Shape.windowHalf = new Vector2(WindowWidth, WindowHeight) / 2f;
            portals.Add(new RoomQuad { name = "window", centre = centre, normal = -ahead, right = Shape.right, up = Vector3.up, size = new Vector2(WindowWidth, WindowHeight) });
            surfaces.Add(new RoomSurface
            {
                kind = SurfaceKind.Floor, name = "FLOOR", height = floorY, unbounded = true, centre = Flat(eye), axis = Vector2.right,
                area = float.PositiveInfinity, freeArea = float.PositiveInfinity,
            });
        }

        // ---- surfaces ------------------------------------------------------------------------------------------

        /// <summary>Whether furniture stands on that surface within radius of a point: on the floor every box that
        /// reaches down to it, on a top every other box that rises through it.</summary>
        public bool Blocked(RoomSurface surface, Vector2 p, float radius)
        {
            for (var i = 0; i < boxes.Count; i++)
            {
                if (i == surface.box) continue;
                var box = boxes[i];
                var stands = surface.kind == SurfaceKind.Floor ? box.bottom < surface.height + MinTopHeight : box.top > surface.height + 0.02f && box.bottom < surface.height + 1f;
                if (stands && box.Distance(p) <= radius) return true;
            }
            return false;
        }

        /// <summary>The surface under a point: the highest one at or below it (5 cm of slack) that holds its ground-plan
        /// position; null over none.</summary>
        public RoomSurface SupportAt(Vector3 point)
        {
            RoomSurface best = null;
            foreach (var s in surfaces)
                if (s.height <= point.y + 0.05f && s.Outside(Flat(point)) <= 0f && (best == null || s.height > best.height)) best = s;
            return best;
        }

        void Measure(RoomSurface s)
        {
            int cells = 0, free = 0;
            for (var x = -s.half.x + FreeAreaCell / 2f; x < s.half.x; x += FreeAreaCell)
                for (var y = -s.half.y + FreeAreaCell / 2f; y < s.half.y; y += FreeAreaCell)
                {
                    var p = s.centre + s.axis * x + Perp(s.axis) * y;
                    if (s.polygon != null && !InPolygon(s.polygon, p)) continue;
                    cells++;
                    if (!Blocked(s, p, 0f)) free++;
                }
            s.area = cells * FreeAreaCell * FreeAreaCell;
            s.freeArea = free * FreeAreaCell * FreeAreaCell;
        }

        // ---- the ground plan -----------------------------------------------------------------------------------

        public static Vector2 Flat(Vector3 v) => new(v.x, v.z);
        public static Vector2 Perp(Vector2 v) => new(-v.y, v.x);

        public static bool InPolygon(Vector2[] polygon, Vector2 p)
        {
            var inside = false;
            for (int i = 0, j = polygon.Length - 1; i < polygon.Length; j = i++)
                if (polygon[i].y > p.y != polygon[j].y > p.y &&
                    p.x < (polygon[j].x - polygon[i].x) * (p.y - polygon[i].y) / (polygon[j].y - polygon[i].y) + polygon[i].x) inside = !inside;
            return inside;
        }

        /// <summary>Metres from a point to the nearest edge of a polygon.</summary>
        public static float EdgeDistance(Vector2[] polygon, Vector2 p)
        {
            var nearest = float.PositiveInfinity;
            for (int i = 0, j = polygon.Length - 1; i < polygon.Length; j = i++)
            {
                Vector2 a = polygon[j], e = polygon[i] - a;
                var u = Mathf.Clamp01(Vector2.Dot(p - a, e) / Mathf.Max(e.sqrMagnitude, 1e-9f));
                nearest = Mathf.Min(nearest, (a + e * u - p).magnitude);
            }
            return nearest;
        }
    }
}
