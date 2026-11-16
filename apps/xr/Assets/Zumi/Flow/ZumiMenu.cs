using System;
using UnityEngine;

namespace Zumi
{
    /// <summary>
    /// The app's first moment: the mascot over the word "Zumi" (LogoSeconds), placed once from where the head was
    /// (Anchor), level; then LogoDone, and the carousel (ZumiCarousel) is the home screen.
    /// </summary>
    public class ZumiMenu : MonoBehaviour
    {
        public const float LogoSeconds = 2.2f, LogoFadeSeconds = 0.45f, LogoDistance = 1.0f, LogoCap = 0.06f, LogoMascot = 0.22f;

        /// <summary>"logo", "hidden".</summary>
        public string State { get; private set; } = "hidden";
        public Pose Anchor { get; private set; }

        Shader flat;
        GameObject mascotPrefab;
        Transform logo;
        readonly ZumiDraw.Parts logoParts = new() { blended = true, queue = 3500 };
        float logoSince = -1f;
        public event Action LogoDone;

        public void Init(Shader flatShader, GameObject mascot)
        {
            flat = flatShader;
            mascotPrefab = mascot;
        }

        /// <summary>The logo, then LogoDone.</summary>
        public void StartLogo()
        {
            Anchor = ZumiFlowKit.LevelHead();
            BuildLogo();
            logoSince = Time.time;
            State = "logo";
        }

        void Update()
        {
            if (!logo) return;
            var t = Time.time - logoSince;
            var a = Mathf.Min(Mathf.Clamp01(t / LogoFadeSeconds), Mathf.Clamp01((LogoSeconds - t) / LogoFadeSeconds));
            logoParts.SetAlpha(a);
            logo.localScale = Vector3.one * Mathf.Lerp(0.92f, 1f, ZumiFlowKit.Smooth(t / LogoSeconds));
            if (t < LogoSeconds) return;
            Destroy(logo.gameObject);
            logoParts.Destroy();
            logo = null;
            State = "hidden";
            LogoDone?.Invoke();
        }

        void BuildLogo()
        {
            logo = new GameObject("Logo").transform;
            var at = Anchor.position + Anchor.rotation * new Vector3(0f, 0f, LogoDistance);
            logo.SetPositionAndRotation(at, ZumiFlowKit.Facing(at, Anchor.position));
            var stand = new GameObject("Mascot stand").transform;
            stand.SetParent(logo, false);
            stand.localPosition = new Vector3(0f, -0.02f, 0f);
            ZumiFlowKit.Mascot(mascotPrefab, stand, LogoMascot, "happy");
            var width = ZumiDraw.Width("Zumi", LogoCap) + 0.08f;
            ZumiDraw.Shape(flat, logoParts, "Plate", logo, 0.02f, ZumiDraw.Plate, 0, ZumiDraw.Moved(ZumiDraw.Rounded(width, LogoCap * 2.2f, LogoCap * 1.1f), new Vector2(0f, -0.07f)));
            ZumiDraw.Text(flat, logoParts, "Word", logo, new Vector3(0f, -0.07f, 0.018f), LogoCap, ZumiDraw.Ink, 2, "Zumi");
            logoParts.SetAlpha(0f);
        }

        void OnDestroy() => logoParts.Destroy();
    }
}
