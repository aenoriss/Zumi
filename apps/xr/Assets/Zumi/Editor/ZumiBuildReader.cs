using System.IO;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEditor.Android;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace Zumi.EditorTools
{
    /// <summary>Builds the reader APK for the headset: the Pepper&amp;Carrot episode (internal R&amp;D only, never shipped)
    /// is moved out of StreamingAssets for the build and back afterwards.</summary>
    static class ZumiBuildReader
    {
        const string Held = "Assets/StreamingAssets/Episodes/pepper-carrot-39.zumi";
        const string Aside = "EpisodesHeld/pepper-carrot-39.zumi";
        const string Apk = "Builds/zumi-reader.apk";
        const string ReleaseApk = "Builds/zumi-release.apk";
        static readonly string[] Scenes = { "Assets/Zumi/ZumiMR.unity" };

        [MenuItem("Zumi/Build Reader APK")]
        static void Build()
        {
            var report = BuildWithoutHeld(Apk, BuildOptions.Development);
            var s = report.summary;
            Debug.Log($"[ZumiBuild] {s.result}: {s.totalErrors} errors, {s.totalSize / 1048576} MB, {s.totalTime.TotalMinutes:F1} min -> {Apk}");
        }

        /// <summary>The store build: signed with the owner's keystore (set, with its passwords, in Publishing Settings;
        /// this never reads them), no development, debugging or profiler, and the next version code.</summary>
        [MenuItem("Zumi/Build Release APK")]
        static void BuildRelease()
        {
            if (!PlayerSettings.Android.useCustomKeystore
                || string.IsNullOrEmpty(PlayerSettings.Android.keystoreName)
                || string.IsNullOrEmpty(PlayerSettings.Android.keyaliasName))
            {
                Debug.LogError("[ZumiBuild] release refused: turn on Custom Keystore in Player > Publishing Settings, choose the keystore and alias and type both passwords");
                return;
            }
            // Unity keeps a keystore outside the project relative to the user's home ("Desktop/x.keystore")
            var home = System.Environment.GetFolderPath(System.Environment.SpecialFolder.UserProfile);
            if (!File.Exists(PlayerSettings.Android.keystoreName) && !File.Exists(Path.Combine(home, PlayerSettings.Android.keystoreName)))
            {
                Debug.LogError($"[ZumiBuild] release refused: keystore not found at {PlayerSettings.Android.keystoreName}");
                return;
            }

            PlayerSettings.Android.bundleVersionCode += 1;
            AssetDatabase.SaveAssets();
            var name = PlayerSettings.bundleVersion;
            var code = PlayerSettings.Android.bundleVersionCode;
            Debug.Log($"[ZumiBuild] release {name} ({code}) starting");

            var report = BuildWithoutHeld(ReleaseApk, BuildOptions.None);
            var s = report.summary;
            var mb = File.Exists(ReleaseApk) ? new FileInfo(ReleaseApk).Length / 1048576f : 0f;
            var line = $"[ZumiBuild] release {name} ({code}) {s.result}: {s.totalErrors} errors, {mb:F1} MB, {s.totalTime.TotalMinutes:F1} min -> {ReleaseApk}";
            if (s.result == BuildResult.Succeeded) Debug.Log(line);
            else Debug.LogError(line);
        }

        static BuildReport BuildWithoutHeld(string apk, BuildOptions options)
        {
            Directory.CreateDirectory("EpisodesHeld");
            var moved = Move(Held, Aside);
            try
            {
                return BuildPipeline.BuildPlayer(new BuildPlayerOptions
                {
                    scenes = Scenes,
                    locationPathName = apk,
                    target = BuildTarget.Android,
                    options = options,
                });
            }
            finally
            {
                if (moved) Move(Aside, Held);
                AssetDatabase.Refresh();
            }
        }

        static bool Move(string from, string to)
        {
            if (!File.Exists(from)) return false;
            File.Move(from, to);
            if (File.Exists(from + ".meta")) File.Move(from + ".meta", to + ".meta");
            return true;
        }
    }

    /// <summary>Unity adds the microphone permissions because the Voice SDK (in the Meta all-in-one package) references
    /// Microphone; the reader never records, so they are taken out of the generated manifest.</summary>
    class ZumiStripUnusedPermissions : IPostGenerateGradleAndroidProject
    {
        static readonly string[] Unused =
        {
            "android.permission.RECORD_AUDIO",
            "android.permission.MODIFY_AUDIO_SETTINGS",
            "android.permission.BLUETOOTH",
        };

        public int callbackOrder => 1000;

        public void OnPostGenerateGradleAndroidProject(string path)
        {
            var manifest = Path.Combine(path, "src", "main", "AndroidManifest.xml");
            if (!File.Exists(manifest)) return;
            var xml = File.ReadAllText(manifest);
            foreach (var p in Unused)
                xml = Regex.Replace(xml, $@"[ \t]*<uses-permission[^>]*android:name=""{Regex.Escape(p)}""[^>]*/>\r?\n?", "");
            File.WriteAllText(manifest, xml);
        }
    }
}
