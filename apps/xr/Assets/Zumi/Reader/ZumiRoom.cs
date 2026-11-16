using System.Collections.Generic;
using System.Threading.Tasks;
using Meta.XR.MRUtilityKit;
using UnityEngine;
using UnityEngine.XR;
using static System.FormattableString;

namespace Zumi
{
    public enum RoomMode { None, Scanned }
    /// <summary>Ledge: the bottom of the window's reveal on a real wall, the strip of wall thickness at its sill.</summary>
    public enum SurfaceKind { Floor, Table, Shelf, Ledge }

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
        /// <summary>Level: the place's own forward and right, centred on the window (the panel's direction), not on
        /// the wall's square. Facing the wall at an angle put the place's middle off the hole's middle, so the place
        /// ended inside the hole on one side (owner, 2026-11-16: "the hole is wider than the scene").</summary>
        public Vector3 placeForward, placeRight;
        /// <summary>Metres from the eye to the key wall along forward.</summary>
        public float wallDistance;
        public float floorY;
        /// <summary>The planes the window lies on, each a point and its normal into the room, as MRUK gives the walls:
        /// the key wall, and the side walls at its left [0] and right [1] edges the window may fold onto (sideOk), with
        /// the corner each shares with the key wall (a point of the corner line at the eye's height, and metres along
        /// the walls laid flat there) and the way along the side wall from that corner into the room.</summary>
        public Vector3 keyPoint, keyNormal;
        public readonly bool[] sideOk = new bool[2];
        public readonly Vector3[] sidePoint = new Vector3[2], sideNormal = new Vector3[2], cornerPoint = new Vector3[2], sideAlong = new Vector3[2];
        public readonly float[] cornerAlong = new float[2];
        /// <summary>The window, following the wall: a rounded rectangle on the walls laid flat, from and to in metres
        /// along them (from keyPoint along right, on round a corner along a side wall), bottom and top in world y; its
        /// corners' radius and the width of its soft edge, in metres (ZumiOutline in ZumiOpening.hlsl).</summary>
        public Vector4 rect;
        public float corner, softEdge;
        /// <summary>Cut into a real wall; false: standing free.</summary>
        public bool onWall;

        /// <summary>Metres from the eye along a unit direction to where it leaves the room through the window's planes
        /// (infinity where it never does), and whether it leaves there inside the window.</summary>
        public bool Window(Vector3 dir, out float metres)
        {
            metres = float.PositiveInfinity;
            Exit(keyPoint, keyNormal, dir, ref metres);
            for (var s = 0; s < 2; s++)
                if (sideOk[s]) Exit(sidePoint[s], sideNormal[s], dir, ref metres);
            if (float.IsInfinity(metres)) return false;
            var at = eye + dir * metres;
            // on the walls laid flat (ZumiFlat in ZumiOpening.hlsl), then the rounded rectangle's signed distance
            var along = Vector3.Dot(at - keyPoint, right);
            var past = Vector3.Dot(at - keyPoint, keyNormal);
            if (past > 1e-3f)
            {
                var s = along < (rect.x + rect.y) / 2f ? 0 : 1;
                if (sideOk[s]) along = cornerAlong[s] + (s == 0 ? -1f : 1f) * past / Mathf.Max(Vector3.Dot(sideAlong[s], keyNormal), 1e-3f);
            }
            var p = new Vector2(along, at.y);
            var c = new Vector2(rect.x + rect.y, rect.z + rect.w) / 2f;
            var h = new Vector2(rect.y - rect.x, rect.w - rect.z) / 2f;
            var r = Mathf.Min(corner, Mathf.Min(h.x, h.y));
            var q = new Vector2(Mathf.Abs(p.x - c.x), Mathf.Abs(p.y - c.y)) - (h - Vector2.one * r);
            return Vector2.Max(q, Vector2.zero).magnitude + Mathf.Min(Mathf.Max(q.x, q.y), 0f) - r <= 0f;
        }

        void Exit(Vector3 point, Vector3 normal, Vector3 dir, ref float metres)
        {
            var toward = Vector3.Dot(dir, normal);
            if (toward > -1e-4f) return;
            var t = Vector3.Dot(point - eye, normal) / toward;
            if (t > 0f) metres = Mathf.Min(metres, t);
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
        /// <summary>The window a place is seen through, at most, as the angles it spans from the seat's eye, centred on
        /// the panel's direction: the panel at 1 m spans 55 degrees on its long side, so 100 leaves 22 on either side
        /// of it. One opening on the key wall, cut to the wall less WindowInset: it never runs past the wall's edges or
        /// onto the ceiling. Its edge is a rounded mask in the place's shader (Zumi/Place), touching the rectangle's
        /// middle of each side.</summary>
        public const float WindowWidthDegrees = 100f, WindowHeightDegrees = 66f;
        /// <summary>The free-standing window's least size (no room, or no wall that can hold it): half of each to
        /// either side of the panel's direction (the panel's 27.5 plus 4.5), and up in all (the default's
        /// proportion). On a real wall it does not apply (MinWallWindowDegrees).</summary>
        public const float MinWindowWidthDegrees = 64f, MinWindowHeightDegrees = 41.6f;
        /// <summary>The least a real wall must show, across and up, to hold the window; below it the window stands
        /// free. The free window's minimum (MinWindow*) no longer applies on a wall.</summary>
        public const float MinWallWindowDegrees = 12f;
        /// <summary>Metres the window keeps from the key wall's side edges and its top.</summary>
        public const float WindowInset = 0.15f;
        /// <summary>Metres above the floor the window's lower edge never goes below (the window moves up to keep it).</summary>
        public const float WindowSill = 0.2f;
        /// <summary>Directions further than this from the key wall's normal never meet it usefully: the window's side
        /// edges are cut there.</summary>
        const float MaxWindowAzimuth = 80f;
        /// <summary>A key wall nearer than this to the seat's eye cannot hold the window: it stands free.</summary>
        public const float MinKeyWallDistance = 1.2f;  // the panel stands 1.0 m out: a wall just behind it still holds the window
        /// <summary>The window may fold round a corner onto the wall next to the key wall, at most this far along it
        /// and this many degrees past the corner as the seat sees it (the lesser), and only onto a side wall that faces
        /// the seat within MaxBleedFacingDegrees of square (a grazing wall reads as stretched). Never onto the ceiling
        /// or the floor.</summary>
        // MaxBleedFacingDegrees was 60: a side wall meeting the key wall at a right angle faces a seat 4.3 m from a
        // 3.3 m wall at about 69 degrees, so in most rooms the window never folded (owner, on the headset,
        // 2026-11-16: "it doesn't bleed to nearby walls"). At 80 nearly every real corner folds; the fold stays short
        // (BleedMetres, BleedDegrees), which keeps the grazing stretch small.
        public const float BleedMetres = 0.5f, BleedDegrees = 20f, MaxBleedFacingDegrees = 80f;
        /// <summary>Metres a side wall's end may be from the key wall's edge and still be the wall round that corner.</summary>
        const float CornerSlack = 0.25f;
        /// <summary>Metres round the window on the key wall the rim (the broken wall's cracks) may reach.</summary>
        const float RimMargin = 0.6f;
        /// <summary>On a real wall: the window's corners' radius, and the width of its soft edge (the plain fade), in
        /// metres.</summary>
        public const float WallCorner = 0.45f, WallSoftEdge = 0.4f;
        /// <summary>Metres the broken wall is thick: how far the reveal (Zumi/Reveal) goes back into it, and how deep
        /// the window's ledge is.</summary>
        public const float WallThickness = 0.15f;
        /// <summary>Least length of the ledge's flat part, in metres; shorter, there is no ledge.</summary>
        const float MinLedgeLength = 0.1f;
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
        readonly List<RoomQuad> portals = new(), rims = new();
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
        /// <summary>The key wall's own normal as MRUK gives it (KeyWallNormal is it made level).</summary>
        public Vector3 KeyWallPlane { get; private set; }
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
        /// <summary>Where the window's edge is drawn (Zumi/Breach): round the window on the key wall within its
        /// extent, and the folds.</summary>
        public IReadOnlyList<RoomQuad> Rims => rims;
        /// <summary>Degrees the window spans from the seat's eye, across and up (smaller than the defaults when the key
        /// wall cuts it).</summary>
        public Vector2 WindowSpan { get; private set; }
        /// <summary>The window is cut into a real wall (a broken wall can show); false: it stands free (no room, or a
        /// key wall that cannot hold it), and its edge is a rift.</summary>
        public bool WindowOnWall { get; private set; }
        /// <summary>How far the window folds onto each side wall, metres along it: "left 0.42 m, right none".</summary>
        public string BleedLine { get; private set; } = "none";
        /// <summary>The lowest point of anything a place is seen through, in metres above the floor.</summary>
        public float PortalFloorClearance { get; private set; }
        /// <summary>The window's ledge: the flat bottom of its reveal on the key wall, the sill's straight part (between
        /// the rounded corners, short of a fold) by the wall's thickness, from the wall's face into it. Null when the
        /// window is not on a real wall or its sill has no straight part.</summary>
        public RoomSurface Ledge { get; private set; }

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

        /// <summary>The most of the window the places can fill: across and up, in degrees about the panel's direction
        /// and the eye's level, where every place of the episode still shows at full strength (inside its vignette).
        /// The window never runs past it: the hole on the wall was bigger than the scene behind it, which faded out
        /// well inside the hole's edge (owner, 2026-11-16). Set by ZumiPlaces once the episode is known.</summary>
        public Vector2 ContentSpan { get; private set; } = new Vector2(WindowWidthDegrees, WindowHeightDegrees);
        int contentSerial;

        public void LimitToContent(Vector2 span)
        {
            if (span == ContentSpan) return;
            ContentSpan = span;
            contentSerial++;
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
                var h = (seat.Seatings * 397 + (loading ? 1 : 0)) * 31 + contentSerial;
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
            rims.Clear();
            Ledge = null;
            BleedLine = "none";
            Vector3 eye = seat.Position, ahead = seat.Forward;
            string why = null;
            if (!room) why = loading ? "the room is loading" : loadNote ?? "no scanned room";
            else if (!Scanned(room, eye, ahead, out why))
            {
                surfaces.Clear();
                boxes.Clear();
                portals.Clear();
                rims.Clear();
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
            Debug.Log(Invariant($"[Zumi] room: {Mode}{(why != null ? $" ({why})" : "")}, key wall {KeyWallName} {KeyWallDistance:F2} m away, window {WindowSpan.x:F0} x {WindowSpan.y:F0} deg ({(WindowOnWall ? "on the wall" : "free")}, folds {BleedLine}), floor {FloorCount} table {TableCount} shelf {ShelfCount}, {boxes.Count} boxes"));
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
            // level, for the seat's bearings; the wall's plane is the anchor's own (KeyWallPlane), and KeyWallPoint is
            // on it at the eye's height, straight ahead of the eye along the level normal
            var normal = Vector3.ProjectOnPlane(keyWall.transform.forward, Vector3.up).normalized;
            var keyPlane = keyWall.transform.forward;
            var distance = Vector3.Dot(keyWall.transform.position - eye, keyPlane) / Mathf.Min(Vector3.Dot(-normal, keyPlane), -1e-3f);
            if (distance < 0.3f)
            {
                why = "the seat is against the wall";
                return false;
            }
            Bounds = room.GetRoomBounds();
            Shape = new RoomShape { eye = eye, forward = -normal, right = Vector3.Cross(Vector3.up, -normal), wallDistance = distance, floorY = floorY,
                                    placeForward = -normal, placeRight = Vector3.Cross(Vector3.up, -normal) };
            KeyWallNormal = normal;
            KeyWallPlane = keyPlane;
            KeyWallPoint = eye - normal * distance;
            KeyWallName = keyWall.name;
            KeyWallAhead = WallHit(keyWall, eye, ahead, out var straight) ? straight : distance / Mathf.Max(Vector3.Dot(ahead, -normal), 1e-3f);
            var held = distance >= MinKeyWallDistance ? OnWall(room, keyWall, eye, ahead, floorY, ceilingY) : Invariant($"{keyWall.name} is {distance:F2} m away");
            if (held != null)
            {
                // a wall that cannot hold the window keeps none of it: the window stands free, as without a room
                portals.Clear();
                Free(eye, ahead, floorY, $"free ({held})");
            }

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
            if (Ledge != null) surfaces.Add(Ledge);
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
            Bounds = default;
            Free(eye, ahead, floorY, "virtual");
            surfaces.Add(new RoomSurface
            {
                kind = SurfaceKind.Floor, name = "FLOOR", height = floorY, unbounded = true, centre = Flat(eye), axis = Vector2.right,
                area = float.PositiveInfinity, freeArea = float.PositiveInfinity,
            });
        }

        // ---- the window ----------------------------------------------------------------------------------------

        // a plane square to the seat's forward, VirtualWallDistance ahead: the key wall without a room, or when the
        // scanned one cannot hold the window. Its window is the default one; its edge is a rift
        void Free(Vector3 eye, Vector3 ahead, float floorY, string name)
        {
            Shape = new RoomShape { eye = eye, forward = ahead, right = Vector3.Cross(Vector3.up, ahead), wallDistance = VirtualWallDistance, floorY = floorY,
                                    placeForward = ahead, placeRight = Vector3.Cross(Vector3.up, ahead) };
            KeyWallNormal = KeyWallPlane = -ahead;
            KeyWallPoint = eye + ahead * VirtualWallDistance;
            KeyWallName = name;
            KeyWallAhead = VirtualWallDistance;
            Window(eye, ahead, float.NegativeInfinity, float.PositiveInfinity, null, null, float.PositiveInfinity, false);
            rims.Clear();
            rims.AddRange(portals);
        }

        sealed class Side
        {
            /// <summary>The corner the side wall shares with the key wall, where their planes meet at the eye's height;
            /// a point of the side wall (the anchor's) and its normal into the room, as MRUK gives them; the way along
            /// the side wall from the corner into the room, level; how far the window may go along it; metres along
            /// the key wall from KeyWallPoint to the corner.</summary>
            public Vector3 corner, point, normal, along;
            public float metres, at;
        }

        // The window on a real key wall: as far as the wall reaches (less WindowInset at an edge with no wall round the
        // corner, or one the window may not fold onto), folding round a corner onto a side wall by the bleed allowed
        // there, up to the ceiling less WindowInset
        string OnWall(MRUKRoom room, MRUKAnchor keyWall, Vector3 eye, Vector3 ahead, float floorY, float ceilingY)
        {
            var key = Quad(keyWall);
            var across = Vector3.Dot(key.centre - KeyWallPoint, Shape.right);
            var half = Mathf.Abs(Vector3.Dot(key.right, Shape.right)) * key.size.x / 2f;
            var wallTop = Mathf.Min(key.centre.y + Mathf.Abs(key.up.y) * key.size.y / 2f, ceilingY);
            var left = SideAt(room, keyWall, eye, KeyWallPoint + Shape.right * (across - half));
            var right = SideAt(room, keyWall, eye, KeyWallPoint + Shape.right * (across + half));
            // a fold bends on the corner line itself, where the two walls' planes meet
            var held = Window(eye, ahead, left != null ? left.at : across - half + WindowInset, right != null ? right.at : across + half - WindowInset,
                              left, right, wallTop - WindowInset, true);
            if (held != null) return held;
            // the rim's room on the key wall: RimMargin round the window, never past the wall
            rims.Clear();
            var w = portals[0];
            var mid = Vector3.Dot(w.centre - KeyWallPoint, Shape.right);
            float x0 = Mathf.Max(across - half, mid - w.size.x / 2f - RimMargin), x1 = Mathf.Min(across + half, mid + w.size.x / 2f + RimMargin);
            float y0 = Mathf.Max(floorY, w.centre.y - w.size.y / 2f - RimMargin), y1 = Mathf.Min(wallTop, w.centre.y + w.size.y / 2f + RimMargin);
            rims.Add(Strip("window", KeyWallPoint + Shape.right * x0, KeyWallPoint + Shape.right * x1, KeyWallPoint, KeyWallPlane, y0, y1));
            for (var i = 1; i < portals.Count; i++) rims.Add(portals[i]);

            // the ledge: the sill's straight part on the key wall, kept a wall's thickness off a fold (the sill bends
            // into the side wall there), from the wall's face back into the wall
            float from = Mathf.Max(Shape.rect.x + Shape.corner, mid - w.size.x / 2f + (Shape.sideOk[0] ? WallThickness : 0f));
            float to = Mathf.Min(Shape.rect.y - Shape.corner, mid + w.size.x / 2f - (Shape.sideOk[1] ? WallThickness : 0f));
            if (to - from >= MinLedgeLength)
            {
                var centre = KeyWallPoint + Shape.right * ((from + to) / 2f) - KeyWallNormal * (WallThickness / 2f);
                Ledge = new RoomSurface
                {
                    kind = SurfaceKind.Ledge, name = "LEDGE", height = Shape.rect.z, centre = Flat(centre), axis = Flat(Shape.right).normalized,
                    half = new Vector2((to - from) / 2f, WallThickness / 2f),
                };
            }
            return null;
        }

        // the wall round the key wall's corner (a point of its edge), and how far the window may fold onto it; null when
        // there is none or it faces the seat too obliquely
        Side SideAt(MRUKRoom room, MRUKAnchor keyWall, Vector3 eye, Vector3 corner)
        {
            foreach (var wall in room.WallAnchors)
            {
                if (wall == keyWall || !IsWall(wall)) continue;
                var q = Quad(wall);
                var r = Vector3.ProjectOnPlane(q.right, Vector3.up).normalized;
                foreach (var end in new[] { -1f, 1f })
                {
                    var tip = q.centre + r * (end * q.size.x / 2f);
                    if ((Flat(tip) - Flat(corner)).magnitude > CornerSlack) continue;
                    var along = -r * end;
                    if (Vector3.Dot(along, KeyWallNormal) <= 0f) continue;
                    var normal = Vector3.ProjectOnPlane(q.normal, Vector3.up).normalized;
                    if (Vector3.Angle(normal, Vector3.ProjectOnPlane(eye - corner, Vector3.up)) > MaxBleedFacingDegrees) return null;
                    // the corner line: along the key wall, at the eye's height, to where it meets the side wall's plane
                    var toward = Vector3.Dot(Shape.right, q.normal);
                    if (Mathf.Abs(toward) < 1e-3f) return null;
                    var at = Vector3.Dot(q.centre - KeyWallPoint, q.normal) / toward;
                    var meet = KeyWallPoint + Shape.right * at;
                    var metres = BleedMetres;
                    var from = Azimuth(eye, meet);
                    while (metres > 0.05f && Mathf.Abs(Azimuth(eye, meet + along * metres) - from) > BleedDegrees) metres -= 0.02f;
                    return new Side { corner = meet, point = q.centre, normal = q.normal, along = along, metres = metres, at = at };
                }
            }
            return null;
        }

        // degrees from Shape.forward to a point as the eye sees it, positive to the right
        float Azimuth(Vector3 eye, Vector3 point)
        {
            var v = point - eye;
            return Mathf.Atan2(Vector3.Dot(v, Shape.right), Vector3.Dot(v, Shape.forward)) * Mathf.Rad2Deg;
        }

        // The window as an ellipse in angles from the eye: WindowWidthDegrees across about the panel's direction,
        // WindowHeightDegrees up about the eye's level, lifted to keep the sill, cut to what the walls hold (left and
        // right: metres along Shape.right from KeyWallPoint on the key wall; a side folds on past its corner; topY the
        // ceiling's inset), with the planes it lies on and the quads that mark the stencil. Null when what is left
        // still shows MinWindow around the panel's direction; otherwise why not, and no window is kept.
        string Window(Vector3 eye, Vector3 ahead, float left, float right, Side sideL, Side sideR, float topY, bool onWall)
        {
            var d = Shape.wallDistance;
            var panelAt = Azimuth(eye, eye + ahead);
            var azLeft = sideL != null ? Azimuth(eye, sideL.corner + sideL.along * sideL.metres) : Mathf.Atan2(left, d) * Mathf.Rad2Deg;
            var azRight = sideR != null ? Azimuth(eye, sideR.corner + sideR.along * sideR.metres) : Mathf.Atan2(right, d) * Mathf.Rad2Deg;
            var width = Mathf.Min(WindowWidthDegrees, ContentSpan.x);
            azLeft = Mathf.Max(azLeft, panelAt - width / 2f, -MaxWindowAzimuth);
            azRight = Mathf.Min(azRight, panelAt + width / 2f, MaxWindowAzimuth);
            var reach = d / Mathf.Cos(Mathf.Clamp(panelAt, -MaxWindowAzimuth, MaxWindowAzimuth) * Mathf.Deg2Rad);
            var bottomY = Shape.floorY + WindowSill;
            var elLow = Mathf.Max(-WindowHeightDegrees / 2f, Mathf.Atan2(bottomY - eye.y, reach) * Mathf.Rad2Deg);
            var elHigh = Mathf.Min(elLow + WindowHeightDegrees, Mathf.Atan2(topY - eye.y, reach) * Mathf.Rad2Deg);
            float toLeft = panelAt - azLeft, toRight = azRight - panelAt;
            // On a real wall the window stays on the wall at whatever size the wall holds: the owner's rule is that the
            // opening's edge sticks to the real wall, and refusing a wall below the free window's minimum sent most
            // rooms to the free-standing rift, which sticks to nothing (2026-11-16). Only a wall too small to show
            // anything (MinWallWindowDegrees) is refused.
            if (onWall ? toLeft + toRight < MinWallWindowDegrees : Mathf.Min(toLeft, toRight) < MinWindowWidthDegrees / 2f)
                return Invariant($"the wall holds {Mathf.Max(toLeft + toRight, 0f):F0} deg across");
            if (elHigh - elLow < (onWall ? MinWallWindowDegrees : MinWindowHeightDegrees))
                return Invariant($"the wall holds {Mathf.Max(elHigh - elLow, 0f):F0} deg up");

            WindowOnWall = Shape.onWall = onWall;
            // the place is centred on the window's middle, so it reaches as far to either side of the hole
            var centre = Quaternion.AngleAxis((azLeft + azRight) / 2f, Vector3.up);
            Shape.placeForward = centre * Shape.forward;
            Shape.placeRight = Vector3.Cross(Vector3.up, Shape.placeForward);
            Shape.keyPoint = KeyWallPoint;
            Shape.keyNormal = KeyWallPlane;
            WindowSpan = new Vector2(azRight - azLeft, elHigh - elLow);
            // up: the angles at the panel's distance, within the sill and the ceiling's inset
            float low = Mathf.Max(bottomY, eye.y + reach * Mathf.Tan(elLow * Mathf.Deg2Rad)), high = Mathf.Min(topY, eye.y + reach * Mathf.Tan(elHigh * Mathf.Deg2Rad));

            // the stencil's quads: on the key wall between the window's sides (or the corners), then the folds
            float x0 = Mathf.Max(left, d * Mathf.Tan(azLeft * Mathf.Deg2Rad)), x1 = Mathf.Min(right, d * Mathf.Tan(azRight * Mathf.Deg2Rad));
            float flatFrom = x0, flatTo = x1;
            portals.Add(Strip("window", KeyWallPoint + Shape.right * x0, KeyWallPoint + Shape.right * x1, KeyWallPoint, KeyWallPlane, low, high));
            var lines = new string[2];
            for (var s = 0; s < 2; s++)
            {
                var side = s == 0 ? sideL : sideR;
                var limit = s == 0 ? azLeft : azRight;
                Shape.sideOk[s] = false;
                lines[s] = $"{(s == 0 ? "left" : "right")} none";
                if (side == null) continue;
                // along the side wall to where the ellipse's side meets it
                float lo = 0f, hi = side.metres, from = Azimuth(eye, side.corner);
                for (var i = 0; i < 14; i++)
                {
                    var mid = (lo + hi) / 2f;
                    if (Mathf.Abs(Azimuth(eye, side.corner + side.along * mid) - from) < Mathf.Abs(limit - from)) lo = mid;
                    else hi = mid;
                }
                if (lo < 0.02f) continue;
                Shape.sideOk[s] = true;
                Shape.sidePoint[s] = side.point;
                Shape.sideNormal[s] = side.normal;
                Shape.cornerPoint[s] = side.corner;
                Shape.cornerAlong[s] = side.at;
                Shape.sideAlong[s] = side.along;
                portals.Add(Strip(s == 0 ? "fold left" : "fold right", side.corner, side.corner + side.along * lo, side.point, side.normal, low, high));
                lines[s] = Invariant($"{(s == 0 ? "left" : "right")} {lo:F2} m");
                if (s == 0) flatFrom = x0 - lo;
                else flatTo = x1 + lo;
            }
            BleedLine = $"{lines[0]}, {lines[1]}";
            Shape.rect = new Vector4(flatFrom, flatTo, low, high);
            // on a wall its corners are gently rounded; standing free it is nearly an ellipse
            var half = Mathf.Min(flatTo - flatFrom, high - low) / 2f;
            Shape.corner = onWall ? Mathf.Min(WallCorner, half) : 0.9f * half;
            Shape.softEdge = onWall ? Mathf.Min(WallSoftEdge, half) : 0.45f * half;
            return null;
        }

        // a quad on a wall between two points of it, from low to high, exactly on the wall's plane (a point of it and
        // its normal, as MRUK gives them)
        static RoomQuad Strip(string name, Vector3 a, Vector3 b, Vector3 point, Vector3 normal, float low, float high)
        {
            var centre = (a + b) / 2f;
            centre.y = (low + high) / 2f;
            centre -= normal * Vector3.Dot(centre - point, normal);
            var right = Vector3.Cross(Vector3.up, -normal).normalized;
            return new RoomQuad
            {
                name = name, centre = centre, normal = normal, right = right, up = Vector3.Cross(-normal, right),
                size = new Vector2((Flat(b) - Flat(a)).magnitude, Mathf.Max(high - low, 0f)),
            };
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
