using System;
using UnityEngine;
using UnityEngine.XR;
using Zumi.Format;

namespace Zumi
{
    /// <summary>
    /// The open place's light on the reader's room (episode.places.meshes[].light), eased so the room changes slowly:
    /// every value moves toward its target with a time constant of EaseSeconds (95 % of the way in 3 s), in real time.
    ///
    /// The real room is graded through the passthrough layer: each colour times (1 + room.brightness), then tinted toward
    /// room.tint by room.tintStrength. Meta's layer takes one colour control at a time (a grey map, brightness-contrast-
    /// saturation, or a colour table); only a colour table can tint and brighten a colour image, so the grade is a
    /// 16-cube table, and a change is the layer's own blend between two tables: the one for the grade as it is now and
    /// the one it is heading for. No place open, or room effects not Full: back to the room's own colours, then no
    /// table at all. The panel and the place are drawn by the app, so the grade never touches them.
    ///
    /// The props are lit with the same place's light (Zumi/Prop): its ambient's three colours, its key light from its
    /// direction in the place's frame (never lower than KeyPitchFloor above the horizon) times the place's fade, and a
    /// fixed share of their own texture. With no place open the ambient is white and there is no key light.
    /// </summary>
    [RequireComponent(typeof(ZumiPlaces), typeof(ZumiRoom))]
    public class ZumiRoomLight : MonoBehaviour
    {
        public const float EaseSeconds = 1f;
        public const float KeyPitchFloor = 5f;
        /// <summary>A prop shows this share of its texture as its own light, this much of the ambient, and the key light
        /// (colour times strength) by this much where it faces it.</summary>
        public const float SelfLight = 0.45f, AmbientGain = 0.4f, KeyGain = 0.6f;
        /// <summary>The colour table's side: 16 steps a channel.</summary>
        public const int TableSide = 16;

        static readonly int Sky = Shader.PropertyToID("_ZumiSky"), Horizon = Shader.PropertyToID("_ZumiHorizon"), Ground = Shader.PropertyToID("_ZumiGround"),
                            KeyDir = Shader.PropertyToID("_ZumiKeyDir"), Key = Shader.PropertyToID("_ZumiKey"), PropLight = Shader.PropertyToID("_ZumiPropLight");

        ZumiPlaces places;
        ZumiRoom room;
        OVRPassthroughLayer layer;
        OVRPassthroughColorLut tableFrom, tableTo;
        readonly Color32[] coloursFrom = new Color32[TableSide * TableSide * TableSide], coloursTo = new Color32[TableSide * TableSide * TableSide];
        Vector3 gainFrom = Vector3.one, gainTo = Vector3.one;
        Color sky = Color.white, horizon = Color.white, ground = Color.white, key = Color.black;
        bool tableOn;

        // ---- read-only state for tests and tools ---------------------------------------------------------------

        /// <summary>What the real room's colours are multiplied by now, per channel; (1, 1, 1) is untouched.</summary>
        public Vector3 GradeGain => Vector3.Lerp(gainFrom, gainTo, GradeWeight);
        /// <summary>What it is heading for.</summary>
        public Vector3 GradeTargetGain => gainTo;
        /// <summary>The blend between the two colour tables: 0 the one it left, 1 the one it is heading for.</summary>
        public float GradeWeight { get; private set; } = 1f;
        /// <summary>What the two tables, blended as the layer blends them, turn a mid grey (136 of 255) into.</summary>
        public Vector3 GradeMidGrey
        {
            get
            {
                var i = 8 + 8 * TableSide + 8 * TableSide * TableSide;
                Color a = coloursFrom[i], b = coloursTo[i];
                var c = Color.Lerp(a, b, GradeWeight);
                return new Vector3(c.r, c.g, c.b);
            }
        }
        /// <summary>Whether the passthrough layer is being driven; in the editor without a headset it is not.</summary>
        public bool GradeOnPassthrough { get; private set; }
        public string GradeNote { get; private set; } = "no headset: the grade is computed, the passthrough layer is not driven";
        /// <summary>The key light on the props now: its colour times its strength and the place's fade, and where it comes from.</summary>
        public Vector3 KeyLight => new(key.r, key.g, key.b);
        public Vector3 KeyDirection { get; private set; } = Vector3.up;
        public Vector3 AmbientSky => new(sky.r, sky.g, sky.b);
        public Vector3 AmbientGround => new(ground.r, ground.g, ground.b);

        void Start()
        {
            places = GetComponent<ZumiPlaces>();
            room = GetComponent<ZumiRoom>();
            layer = FindAnyObjectByType<OVRPassthroughLayer>();
            Fill(coloursFrom, Vector3.one);
            Fill(coloursTo, Vector3.one);
            Shader.SetGlobalVector(PropLight, new Vector4(SelfLight, AmbientGain, 0f, 0f));
        }

        void LateUpdate()
        {
            var light = places.OpenLight;
            var ease = 1f - Mathf.Exp(-Time.unscaledDeltaTime / EaseSeconds);

            // the real room's grade
            var target = Vector3.one;
            if (light?.room != null && places.RoomEffects == RoomEffects.Full)
            {
                var tint = Color.Lerp(Color.white, Hex(light.room.tint), light.room.tintStrength);
                target = new Vector3(tint.r, tint.g, tint.b) * (1f + light.room.brightness);
            }
            var changed = (target - gainTo).sqrMagnitude > 1e-8f;
            if (changed)
            {
                gainFrom = GradeGain;
                gainTo = target;
                GradeWeight = 0f;
                Fill(coloursFrom, gainFrom);
                Fill(coloursTo, gainTo);
            }
            var moving = GradeWeight < 1f;
            GradeWeight = GradeWeight > 0.999f ? 1f : GradeWeight + (1f - GradeWeight) * ease;
            if (changed || moving) Drive(changed);

            // the props' light
            Color wantSky = Color.white, wantHorizon = Color.white, wantGround = Color.white, wantKey = Color.black;
            if (light != null)
            {
                if (light.ambient != null)
                {
                    wantSky = Lit(light.ambient.sky);
                    wantHorizon = Lit(light.ambient.horizon);
                    wantGround = Lit(light.ambient.ground);
                }
                if (light.key != null && room.Shape != null)
                {
                    wantKey = Lit(light.key.color) * (light.key.strength * KeyGain * places.Fade);
                    float yaw = light.key.yaw * Mathf.Deg2Rad, pitch = Mathf.Max(KeyPitchFloor, light.key.pitch) * Mathf.Deg2Rad;
                    KeyDirection = (room.Shape.forward * (Mathf.Cos(yaw) * Mathf.Cos(pitch)) + room.Shape.right * (Mathf.Sin(yaw) * Mathf.Cos(pitch)) + Vector3.up * Mathf.Sin(pitch)).normalized;
                }
            }
            sky = Color.Lerp(sky, wantSky, ease);
            horizon = Color.Lerp(horizon, wantHorizon, ease);
            ground = Color.Lerp(ground, wantGround, ease);
            key = Color.Lerp(key, wantKey, ease);
            Shader.SetGlobalColor(Sky, sky);
            Shader.SetGlobalColor(Horizon, horizon);
            Shader.SetGlobalColor(Ground, ground);
            Shader.SetGlobalColor(Key, key);
            Shader.SetGlobalVector(KeyDir, KeyDirection);
        }

        // the passthrough layer: only with a headset, where there is passthrough to grade
        void Drive(bool tablesChanged)
        {
            GradeOnPassthrough = false;
            if (!layer || !XRSettings.isDeviceActive) return;
            try
            {
                if (GradeWeight >= 1f && gainTo == Vector3.one)
                {
                    if (tableOn) layer.DisableColorMap();
                    tableOn = false;
                    GradeOnPassthrough = true;
                    GradeNote = null;
                    return;
                }
                if (tableFrom == null)
                {
                    tableFrom = new OVRPassthroughColorLut(coloursFrom, OVRPassthroughColorLut.ColorChannels.Rgb);
                    tableTo = new OVRPassthroughColorLut(coloursTo, OVRPassthroughColorLut.ColorChannels.Rgb);
                }
                else if (tablesChanged)
                {
                    tableFrom.UpdateFrom(coloursFrom);
                    tableTo.UpdateFrom(coloursTo);
                }
                layer.SetColorLut(tableFrom, tableTo, GradeWeight);
                tableOn = true;
                GradeOnPassthrough = true;
                GradeNote = null;
            }
            catch (Exception e)
            {
                GradeNote = e.Message;
            }
        }

        // a colour table for one gain: red changes fastest, then green, then blue
        static void Fill(Color32[] table, Vector3 gain)
        {
            var i = 0;
            for (var b = 0; b < TableSide; b++)
                for (var g = 0; g < TableSide; g++)
                    for (var r = 0; r < TableSide; r++)
                        table[i++] = new Color32(Level(r, gain.x), Level(g, gain.y), Level(b, gain.z), 255);
        }

        static byte Level(int step, float gain) => (byte)Mathf.Clamp(Mathf.RoundToInt(step * 255f / (TableSide - 1) * gain), 0, 255);

        static Color Hex(string hex) => ColorUtility.TryParseHtmlString(hex, out var c) ? c : Color.white;

        // a light colour of the file (sRGB) in the space the shaders work in
        static Color Lit(string hex) => QualitySettings.activeColorSpace == ColorSpace.Linear ? Hex(hex).linear : Hex(hex);

        void OnDestroy()
        {
            if (layer && tableOn) layer.DisableColorMap();
            tableFrom?.Dispose();
            tableTo?.Dispose();
        }
    }
}
