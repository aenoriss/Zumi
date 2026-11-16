using Newtonsoft.Json.Linq;
using UnityEngine;

namespace Zumi
{
    public enum ZumiColour { Rainbow, Mint, Sky, Lilac, Pink, Peach, Butter }

    /// <summary>
    /// One Zumi: colour, blush, the random layers and eyes on the viewer. The motion itself is the Animator
    /// (Zumi.controller): Base plays the expressions, and the additive layers Eyes (blink, look_around), Body
    /// (sway, squash), Talk and Breathe sit on top. This script only decides when they fire.
    /// </summary>
    public class ZumiMascot : MonoBehaviour
    {
        [Header("Look")]
        public ZumiColour colour = ZumiColour.Rainbow;
        [Tooltip("Pick a colour at random on spawn (the MR scene's spawner uses the Zumi Random variant)")]
        public bool randomColour;
        public Material bodyMaterial;
        public Material faceMaterial;
        public Material blushMaterial;

        [Header("Behaviour")]
        public TextAsset expressionsJson;
        [Tooltip("neutral, happy, laugh, wow, aww, sad, shocked, annoyed, thinking, sleepy, wink")]
        public string expression = "neutral";
        [Tooltip("Freeze the expression at the end of its peak instead of returning to neutral")]
        public bool hold;
        public bool talking;
        public bool autoBlink = true;
        public bool autoBody = true;
        public bool breathe = true;
        public bool lookAtViewer = true;
        [Range(0.1f, 2f)] public float speed = 1f;

        [Header("Baked by the controller builder")]
        public string[] holdClips;
        public float[] holdTimes;

        // player hues from design/mascot/zumi-mascot.json "readers": light (tip), base, deep (bottom)
        static readonly System.Collections.Generic.Dictionary<ZumiColour, string[]> Hues = new()
        {
            { ZumiColour.Mint, new[] { "#D2F6E6", "#9EE5C8", "#6CCDA6" } },
            { ZumiColour.Sky, new[] { "#D6E9FF", "#9CCBFF", "#6FA9EE" } },
            { ZumiColour.Lilac, new[] { "#E8DCFF", "#C7A8FF", "#9F80E8" } },
            { ZumiColour.Pink, new[] { "#FFD9EA", "#FFA8CF", "#EE7CB2" } },
            { ZumiColour.Peach, new[] { "#FFE3D1", "#FFC3A0", "#EE9C6E" } },
            { ZumiColour.Butter, new[] { "#FFF7D2", "#FFE89A", "#E6C45C" } },
        };
        const int Base = 0, Eyes = 1, Body = 2, Talk = 3, Breathe = 4;
        static readonly int ExprSpeed = Animator.StringToHash("ExprSpeed");

        Animator animator;
        SkinnedMeshRenderer body;
        SkinnedMeshRenderer[] eyes;
        Renderer[] blushes;
        Transform rig;
        MaterialPropertyBlock block;
        JObject cfg;
        string playing = "neutral";
        float nextBlink, nextBody, talk, blush;
        Vector2 look;
        int lookR, lookL, lookU, lookD;

        void Awake()
        {
            cfg = JObject.Parse(expressionsJson.text);
            blush = (float)cfg["blushNeutral"];
            animator = GetComponentInChildren<Animator>();
            var smrs = GetComponentsInChildren<SkinnedMeshRenderer>();
            body = System.Array.Find(smrs, r => r.name.StartsWith("Zumi body"));
            eyes = System.Array.FindAll(smrs, r => r.name.StartsWith("Zumi eye"));
            blushes = System.Array.FindAll(GetComponentsInChildren<Renderer>(), r => r.name.StartsWith("Zumi blush"));
            rig = body.transform.parent;
            var m = eyes[0].sharedMesh;
            lookR = m.GetBlendShapeIndex("look_right"); lookL = m.GetBlendShapeIndex("look_left");
            lookU = m.GetBlendShapeIndex("look_up"); lookD = m.GetBlendShapeIndex("look_down");

            body.sharedMaterial = bodyMaterial;
            foreach (var r in smrs) if (r != body) r.sharedMaterial = faceMaterial;
            foreach (var b in blushes) b.sharedMaterial = blushMaterial;
            if (randomColour) colour = (ZumiColour)Random.Range(0, System.Enum.GetValues(typeof(ZumiColour)).Length);
            ApplyColour();
            nextBlink = Random.Range(1f, 4f);
            nextBody = Random.Range(3f, 10f);
        }

        void OnValidate()
        {
            if (body) ApplyColour();
        }

        void ApplyColour()
        {
            block ??= new MaterialPropertyBlock();
            body.GetPropertyBlock(block);
            block.SetFloat("_Rainbow", colour == ZumiColour.Rainbow ? 1 : 0);
            if (Hues.TryGetValue(colour, out var hex))
            {
                block.SetColor("_Light", Hex(hex[0]));
                block.SetColor("_Base", Hex(hex[1]));
                block.SetColor("_Deep", Hex(hex[2]));
            }
            var b = body.sharedMesh.bounds;
            block.SetFloat("_YMin", b.min.y);
            block.SetFloat("_YMax", b.max.y);
            body.SetPropertyBlock(block);
        }

        static Color Hex(string h) => ColorUtility.TryParseHtmlString(h, out var c) ? c : Color.magenta;

        public void Play(string name)
        {
            animator.SetFloat(ExprSpeed, 1f);
            animator.CrossFadeInFixedTime(name, 0.15f, Base);
            expression = playing = name;
        }

        public void Shot(string name)
        {
            var layer = name is "blink" or "look_around" ? Eyes : Body;
            animator.Play(name, layer, 0f);
        }

        bool Idle(int layer) => animator.GetCurrentAnimatorStateInfo(layer).IsName("empty") && !animator.IsInTransition(layer);

        float HoldTime(string clip)
        {
            var i = System.Array.IndexOf(holdClips, clip);
            return i < 0 ? float.MaxValue : holdTimes[i];
        }

        void Update()
        {
            if (expression != playing) Play(expression);
            animator.speed = speed;
            var dt = Time.deltaTime * speed;

            var state = animator.GetCurrentAnimatorStateInfo(Base);
            var live = playing != "neutral" && !state.IsName("neutral");
            if (!live && playing != "neutral" && !animator.IsInTransition(Base)) playing = expression = "neutral";
            var info = cfg["expressions"][live ? playing : "neutral"];
            if (live) animator.SetFloat(ExprSpeed, hold && state.normalizedTime * state.length >= HoldTime(playing) ? 0f : 1f);

            nextBlink -= dt;
            if (nextBlink <= 0f)
            {
                if (autoBlink && Idle(Eyes) && !(live && (bool?)info["closedEyes"] == true)) Shot("blink");
                nextBlink = Range("blink");
            }
            nextBody -= dt;
            if (nextBody <= 0f)
            {
                if (autoBody && Idle(Body) && !(live && (bool?)info["calm"] == true)) Shot(Random.value < 0.5f ? "sway" : "squash");
                nextBody = Range("body");
            }
            talk = Mathf.Clamp01(talk + (talking ? dt : -dt) / 0.12f);
            animator.SetLayerWeight(Talk, talk);
            animator.SetLayerWeight(Breathe, breathe ? 1f : 0f);

            // blush eases toward the mood's level while the expression shows
            var neutral = (float)cfg["blushNeutral"];
            var level = live ? (float?)info["blush"] ?? neutral : neutral;
            blush += (level - blush) * (1f - Mathf.Exp(-dt * 4f));
            var c = blushMaterial.GetColor("_Color");
            c.a = blush;
            foreach (var b in blushes)
            {
                b.GetPropertyBlock(block);
                block.SetColor("_Color", c);
                b.SetPropertyBlock(block);
            }
        }

        float Range(string layer) => Random.Range((float)cfg["layers"][layer]["every"][0], (float)cfg["layers"][layer]["every"][1]);

        // after the Animator: eyes on the viewer's head, on top of whatever the clip looks at. The model faces +Z
        // and glTF's +x became -x, so the viewer's right (look_right) is local -x
        void LateUpdate()
        {
            var target = Vector2.zero;
            var cam = Camera.main;
            if (lookAtViewer && cam)
            {
                var h = rig.InverseTransformPoint(cam.transform.position).normalized;
                target = new Vector2(-h.x, h.y) * 1.6f;
            }
            look = Vector2.Lerp(look, target, 1f - Mathf.Exp(-Time.deltaTime * speed * 8f));
            foreach (var e in eyes)
            {
                Max(e, lookR, look.x); Max(e, lookL, -look.x);
                Max(e, lookU, look.y); Max(e, lookD, -look.y);
            }
        }

        // glTFast imports each shape key with its full weight at 1 (not Unity's usual 100), and the clips write 0..1:
        // 0.8 at most, as in the web viewer. At 80 the eyes slid off the body
        static void Max(SkinnedMeshRenderer r, int i, float v) =>
            r.SetBlendShapeWeight(i, Mathf.Max(r.GetBlendShapeWeight(i), Mathf.Clamp01(v) * 0.8f));
    }
}
