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

    /// <summary>A flat rectangle of the room: a wall, or the window on it a place is seen through.</summary>
    public struct RoomQuad
    {
        public string name;
        /// <summary>Its middle; normal points into the room.</summary>
        public Vector3 centre, normal, right, up;
        public Vector2 size;
    }

    /// <summary>
    /// What a place is fitted to, as plain numbers (read off the main thread): where the seat's eye is, which way the key
    /// wall lies, and the one window on it the place is seen through.
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
        public float floorY;
        /// <summary>The window on the key wall: its middle and its half sizes across (along right) and up, in metres.</summary>
        public Vector3 windowCentre;
        public Vector2 windowHalf;

        /// <summary>Metres from the eye to the key wall's plane along a unit direction (infinity where it never meets
        /// it), and whether the line of sight crosses the plane inside the window.</summary>
        public bool Window(Vector3 dir, out float metres)
        {
            var toward = Vector3.Dot(dir, forward);
            metres = toward > 1e-4f ? wallDistance / toward : float.PositiveInfinity;
            if (float.IsInfinity(metres)) return false;
            var at = eye + dir * metres - windowCentre;
            return Mathf.Abs(Vector3.Dot(at, right)) <= windowHalf.x && Mathf.Abs(at.y) <= windowHalf.y;
        }
    }

    /// <summary>
    /// The reader's room, for every part that shows something in it. It answers: is there a scanned room (Scanned) or
    /// not (None: no scan, permission refused, the load failed; a normal outcome); where the seat is; which wall is the
    /// key wall, the nearest one behind the panel as the seat sees it: on the seat's forward, or failing that on the
    /// nearest bearing to either side, and facing the seat (without a room, or with no such wall: a wall plane
    /// VirtualWallDistance ahead of the seat); the one window on it a place is seen through (RoomShape, Portals); the
    /// furniture as boxes; and the level surfaces things can
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
        /// <summary>The window a place is seen through, as the angles it spans from the seat's eye, centred on the
        /// panel's direction: the panel at 1 m spans 55 degrees on its long side, so 100 leaves 22 or more on either
        /// side of it. Clamped to the key wall's extent when the wall is smaller.</summary>
        public const float WindowWidthDegrees = 100f, WindowHeightDegrees = 56f;
        /// <summary>Metres above the floor the window's lower edge never goes below (the window moves up to keep it).</summary>
        public const float WindowSill = 0.2f;
        /// <summary>Directions further than this from the key wall's normal never meet it usefully: the window's side
        /// edges are cut there.</summary>
        const float MaxWindowAzimuth = 80f;
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
        /// <summary>What a place is seen through: the one window on the key wall.</summary>
        public IReadOnlyList<RoomQuad> Portals => portals;
        /// <summary>Degrees the window spans from the seat's eye, across and up (smaller than the defaults when the key
        /// wall cuts it).</summary>
        public Vector2 WindowSpan { get; private set; }
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
            Debug.Log(Invariant($"[Zumi] room: {Mode}{(why != null ? $" ({why})" : "")}, key wall {KeyWallName} {KeyWallDistance:F2} m away, window {Shape.windowHalf.x * 2f:F2} x {Shape.windowHalf.y * 2f:F2} m ({WindowSpan.x:F0} x {WindowSpan.y:F0} deg), floor {FloorCount} table {TableCount} shelf {ShelfCount}, {boxes.Count} boxes"));
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
            Shape = new RoomShape { eye = eye, forward = -normal, right = Vector3.Cross(Vector3.up, -normal), wallDistance = distance, floorY = floorY };
            KeyWallNormal = normal;
            KeyWallPoint = eye - normal * distance;
            KeyWallName = keyWall.name;
            KeyWallAhead = WallHit(keyWall, eye, ahead, out var straight) ? straight : distance / Mathf.Max(Vector3.Dot(ahead, -normal), 1e-3f);
            Bounds = room.GetRoomBounds();

            // the wall's extent in the window's frame: across along Shape.right from KeyWallPoint, up in world y
            var wallQuad = Quad(keyWall);
            var across = Vector3.Dot(wallQuad.centre - KeyWallPoint, Shape.right);
            var halfAcross = Mathf.Abs(Vector3.Dot(wallQuad.right, Shape.right)) * wallQuad.size.x / 2f;
            var halfUp = Mathf.Abs(wallQuad.up.y) * wallQuad.size.y / 2f;
            Window(eye, ahead, new Vector2(across - halfAcross, across + halfAcross), new Vector2(wallQuad.centre.y - halfUp, wallQuad.centre.y + halfUp));

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
            Shape = new RoomShape { eye = eye, forward = ahead, right = Vector3.Cross(Vector3.up, ahead), wallDistance = VirtualWallDistance, floorY = floorY };
            KeyWallNormal = -ahead;
            KeyWallPoint = eye + ahead * VirtualWallDistance;
            KeyWallName = "virtual";
            KeyWallAhead = VirtualWallDistance;
            Bounds = default;
            Window(eye, ahead, new Vector2(float.NegativeInfinity, float.PositiveInfinity), new Vector2(floorY, float.PositiveInfinity));
            surfaces.Add(new RoomSurface
            {
                kind = SurfaceKind.Floor, name = "FLOOR", height = floorY, unbounded = true, centre = Flat(eye), axis = Vector2.right,
                area = float.PositiveInfinity, freeArea = float.PositiveInfinity,
            });
        }

        // ---- the window ----------------------------------------------------------------------------------------

        // The window on the key wall's plane: WindowWidthDegrees across about the panel's direction (the seat's
        // forward), WindowHeightDegrees up about the eye's level at the distance along that direction, lifted to keep
        // its lower edge at WindowSill, then cut to the wall's extent: across (metres along Shape.right from
        // KeyWallPoint) and up (world y).
        void Window(Vector3 eye, Vector3 ahead, Vector2 wallAcross, Vector2 wallUp)
        {
            var d = Shape.wallDistance;
            var panelAt = Mathf.Atan2(Vector3.Dot(ahead, Shape.right), Vector3.Dot(ahead, Shape.forward)) * Mathf.Rad2Deg;
            float Across(float deg) => d * Mathf.Tan(Mathf.Clamp(deg, -MaxWindowAzimuth, MaxWindowAzimuth) * Mathf.Deg2Rad);
            float left = Mathf.Max(Across(panelAt - WindowWidthDegrees / 2f), wallAcross.x), right = Mathf.Min(Across(panelAt + WindowWidthDegrees / 2f), wallAcross.y);
            var reach = d / Mathf.Cos(Mathf.Clamp(panelAt, -MaxWindowAzimuth, MaxWindowAzimuth) * Mathf.Deg2Rad);
            var half = reach * Mathf.Tan(WindowHeightDegrees / 2f * Mathf.Deg2Rad);
            var bottom = Mathf.Max(eye.y - half, Shape.floorY + WindowSill);
            var top = Mathf.Min(bottom + 2f * half, wallUp.y);
            bottom = Mathf.Max(bottom, wallUp.x);
            var centre = KeyWallPoint + Shape.right * ((left + right) / 2f);
            centre.y = (bottom + top) / 2f;
            var size = new Vector2(Mathf.Max(right - left, 0f), Mathf.Max(top - bottom, 0f));
            Shape.windowCentre = centre;
            Shape.windowHalf = size / 2f;
            portals.Add(new RoomQuad { name = "window", centre = centre, normal = KeyWallNormal, right = Shape.right, up = Vector3.up, size = size });
            WindowSpan = new Vector2(Mathf.Atan2(right, d) - Mathf.Atan2(left, d), Mathf.Atan2(top - eye.y, reach) - Mathf.Atan2(bottom - eye.y, reach)) * Mathf.Rad2Deg;
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
