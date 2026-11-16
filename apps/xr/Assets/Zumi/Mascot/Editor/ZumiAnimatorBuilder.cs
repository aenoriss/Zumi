using System.Collections.Generic;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

namespace Zumi.Editor
{
    /// <summary>
    /// Builds Zumi.controller from the clips in zumi-mascot.glb and wires it into Zumi.prefab. Run it again after
    /// re-exporting the GLB. Additive layers, because each glTF clip animates every shape key of its mesh: an
    /// override layer playing a blink would also zero the smile underneath.
    /// </summary>
    public static class ZumiAnimatorBuilder
    {
        const string Dir = "Assets/Zumi/Mascot/";
        const string Glb = Dir + "zumi-mascot.glb";
        const string ControllerPath = Dir + "Zumi.controller";
        const string PrefabPath = Dir + "Zumi.prefab";

        [MenuItem("Zumi/Build Mascot Animator")]
        public static void Build()
        {
            var importer = AssetImporter.GetAtPath(Glb);
            var so = new SerializedObject(importer);
            var method = so.FindProperty("importSettings.animationMethod");
            if (method.enumNames[method.enumValueIndex] != "Mecanim")
            {
                method.enumValueIndex = System.Array.IndexOf(method.enumNames, "Mecanim");
                so.ApplyModifiedPropertiesWithoutUndo();
                importer.SaveAndReimport();
            }
            var clips = AssetDatabase.LoadAllAssetsAtPath(Glb).OfType<AnimationClip>().ToDictionary(c => c.name);

            AssetDatabase.DeleteAsset(ControllerPath);
            var ctrl = AnimatorController.CreateAnimatorControllerAtPath(ControllerPath);
            ctrl.AddParameter("ExprSpeed", AnimatorControllerParameterType.Float);
            ctrl.parameters = ctrl.parameters.Select(p => { if (p.name == "ExprSpeed") p.defaultFloat = 1f; return p; }).ToArray();

            // Base: expressions; each plays once and returns to neutral
            var sm = ctrl.layers[0].stateMachine;
            var neutral = sm.AddState("neutral");
            neutral.motion = clips["neutral"];
            sm.defaultState = neutral;
            foreach (var name in new[] { "happy", "laugh", "wow", "aww", "sad", "shocked", "annoyed", "thinking", "sleepy", "wink" })
            {
                var s = sm.AddState(name);
                s.motion = clips[name];
                s.speedParameter = "ExprSpeed";
                s.speedParameterActive = true;
                Exit(s, neutral, 0.1f);
            }

            AddLayer(ctrl, "Eyes", 1f, clips, oneShots: new[] { "blink", "look_around" });
            AddLayer(ctrl, "Body", 1f, clips, oneShots: new[] { "sway", "squash" });
            AddLayer(ctrl, "Talk", 0f, clips, loop: "talk");
            AddLayer(ctrl, "Breathe", 1f, clips, loop: "breathe");

            // hold: where each expression's plateau ends (last frame at 98% of its peak)
            var names = new List<string>();
            var times = new List<float>();
            foreach (var c in clips.Values)
            {
                var curves = AnimationUtility.GetCurveBindings(c).Where(b => b.propertyName.StartsWith("blendShape."))
                    .Select(b => AnimationUtility.GetEditorCurve(c, b)).ToArray();
                float Mag(float t) => curves.Sum(k => k.Evaluate(t));
                var peak = 0f;
                for (var t = 0f; t <= c.length; t += 1 / 30f) peak = Mathf.Max(peak, Mag(t));
                var hold = c.length;
                for (var t = 0f; t <= c.length; t += 1 / 30f) if (Mag(t) >= 0.98f * peak) hold = t;
                names.Add(c.name); times.Add(hold);
            }

            var root = PrefabUtility.LoadPrefabContents(PrefabPath);
            var model = root.transform.GetChild(0).gameObject;
            var animator = model.GetComponent<Animator>();
            if (!animator) animator = model.AddComponent<Animator>();
            animator.runtimeAnimatorController = ctrl;
            animator.cullingMode = AnimatorCullingMode.AlwaysAnimate;
            animator.applyRootMotion = false;
            var legacy = model.GetComponent<Animation>();
            if (legacy) Object.DestroyImmediate(legacy, true);
            var mascot = root.GetComponent<ZumiMascot>();
            mascot.holdClips = names.ToArray();
            mascot.holdTimes = times.ToArray();
            PrefabUtility.SaveAsPrefabAsset(root, PrefabPath);
            PrefabUtility.UnloadPrefabContents(root);
            AssetDatabase.SaveAssets();
            Debug.Log($"Zumi animator built: {clips.Count} clips, {ctrl.layers.Length} layers");
        }

        static void AddLayer(AnimatorController ctrl, string name, float weight, Dictionary<string, AnimationClip> clips,
                             string[] oneShots = null, string loop = null)
        {
            ctrl.AddLayer(new AnimatorControllerLayer
            {
                name = name,
                defaultWeight = weight,
                blendingMode = AnimatorLayerBlendingMode.Additive,
                stateMachine = new AnimatorStateMachine { name = name, hideFlags = HideFlags.HideInHierarchy },
            });
            var sm = ctrl.layers[^1].stateMachine;
            AssetDatabase.AddObjectToAsset(sm, ctrl);
            if (loop != null)
            {
                var s = sm.AddState(loop);
                s.motion = clips[loop];
                Exit(s, s, 0f);
                return;
            }
            var empty = sm.AddState("empty");
            sm.defaultState = empty;
            foreach (var shot in oneShots)
            {
                var s = sm.AddState(shot);
                s.motion = clips[shot];
                Exit(s, empty, 0f);
            }
        }

        static void Exit(AnimatorState from, AnimatorState to, float duration)
        {
            var t = from.AddTransition(to);
            t.hasExitTime = true;
            t.exitTime = 1f;
            t.hasFixedDuration = true;
            t.duration = duration;
        }
    }
}
