using UnityEngine;

namespace Zumi
{
    /// <summary>
    /// The mascot with one line beside it, low in the view, following the head lazily. One switch (On) turns every
    /// caption off, for an edit that adds its own titles. Show(text) brings a line, Hide() takes it away.
    /// </summary>
    public class ZumiCaption : MonoBehaviour
    {
        /// <summary>Metres ahead of the eyes and below them.</summary>
        public const float Ahead = 0.75f, Below = 0.3f;
        public const float FadeSeconds = 0.35f, FollowPerSecond = 2.5f, Cap = 0.016f, MascotHeight = 0.11f;

        /// <summary>The one switch: off, no caption is ever shown.</summary>
        public bool On { get; set; } = true;
        /// <summary>The line on show, or null.</summary>
        public string Line => alpha > 0.01f && wanted ? text : null;

        Shader flat;
        GameObject mascotPrefab;
        Transform root;
        TextMesh label;
        Transform plate;
        ZumiDraw.Parts parts;
        string text;
        bool wanted;
        float alpha;

        public void Init(Shader flatShader, GameObject mascot)
        {
            flat = flatShader;
            mascotPrefab = mascot;
        }

        /// <summary>Brings a line; below: metres under the eyes (Below by default; less to keep it off a desk the
        /// reader looks down at).</summary>
        public void Show(string line, float below = Below)
        {
            drop = below;
            wanted = true;
            if (line == text && next == null) return;
            // a line already up fades out first, then the new one fades in
            if (root && alpha > 0.01f) next = line;
            else Build(line);
        }

        float drop = Below;
        string next;
        /// <summary>A caption wider than this wraps onto a second line.</summary>
        public const float WrapWidth = 0.36f;

        static string Wrap(string line)
        {
            if (ZumiDraw.Width(line, Cap) <= WrapWidth) return line;
            // the space nearest the middle
            var best = -1;
            for (var i = 0; i < line.Length; i++)
                if (line[i] == ' ' && (best < 0 || Mathf.Abs(i - line.Length / 2) < Mathf.Abs(best - line.Length / 2))) best = i;
            return best < 0 ? line : line.Substring(0, best) + "\n" + line.Substring(best + 1);
        }

        public void Hide() => wanted = false;

        void Build(string line)
        {
            text = line;
            if (root) Destroy(root.gameObject);
            parts?.Destroy();
            parts = new ZumiDraw.Parts { blended = true, queue = 3600 };
            root = new GameObject("Caption").transform;
            var shown = Wrap(line);
            var lines = shown.Split('\n');
            var widest = 0f;
            foreach (var l in lines) widest = Mathf.Max(widest, ZumiDraw.Width(l, Cap));
            var width = widest + 0.06f;
            var height = Cap * (1.6f * lines.Length + 1.6f);
            plate = ZumiDraw.Shape(flat, parts, "Plate", root, 0f, ZumiDraw.Plate, 0, ZumiDraw.Rounded(width, height, Mathf.Min(height / 2f, Cap * 1.6f)));
            plate.localPosition = new Vector3(MascotHeight * 0.45f, 0f, 0f);
            label = ZumiDraw.Text(flat, parts, "Line", root, new Vector3(MascotHeight * 0.45f, 0f, -0.002f), Cap, ZumiDraw.Ink, 2, shown);
            label.anchor = TextAnchor.MiddleCenter;
            label.alignment = TextAlignment.Center;
            // the mascot stands at the plate's left end
            var stand = new GameObject("Mascot stand").transform;
            stand.SetParent(root, false);
            stand.localPosition = new Vector3(MascotHeight * 0.45f - width / 2f - MascotHeight * 0.5f, -MascotHeight * 0.45f, -0.01f);
            ZumiFlowKit.Mascot(mascotPrefab, stand, MascotHeight, "happy");
            root.gameObject.SetActive(false);
            Place(true);
        }

        void LateUpdate()
        {
            if (!root) return;
            // the old line has faded: the next one is built and fades in
            if (next != null && alpha <= 0.001f)
            {
                var line = next;
                next = null;
                Build(line);
            }
            var shown = On && wanted && next == null;
            alpha = Mathf.MoveTowards(alpha, shown ? 1f : 0f, Time.deltaTime / FadeSeconds);
            var visible = alpha > 0.001f;
            if (root.gameObject.activeSelf != visible)
            {
                root.gameObject.SetActive(visible);
                if (visible) Place(true);
            }
            if (!visible) return;
            parts.SetAlpha(alpha);
            Place(false);
        }

        void Place(bool snap)
        {
            var head = ZumiFlowKit.LevelHead();
            var at = head.position + head.rotation * new Vector3(0f, -drop, Ahead);
            var rot = ZumiFlowKit.Facing(at, head.position);
            var k = snap ? 1f : 1f - Mathf.Exp(-FollowPerSecond * Time.deltaTime);
            root.SetPositionAndRotation(Vector3.Lerp(root.position, at, k), Quaternion.Slerp(root.rotation, rot, k));
        }

        void OnDestroy()
        {
            if (root) Destroy(root.gameObject);
            parts?.Destroy();
        }
    }
}
