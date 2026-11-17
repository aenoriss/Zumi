using System.IO;
using UnityEditor;
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

        [MenuItem("Zumi/Build Reader APK")]
        static void Build()
        {
            Directory.CreateDirectory("EpisodesHeld");
            var moved = Move(Held, Aside);
            try
            {
                var report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
                {
                    scenes = new[] { "Assets/Zumi/ZumiMR.unity" },
                    locationPathName = Apk,
                    target = BuildTarget.Android,
                    options = BuildOptions.Development,
                });
                var s = report.summary;
                Debug.Log($"[ZumiBuild] {s.result}: {s.totalErrors} errors, {s.totalSize / 1048576} MB, {s.totalTime.TotalMinutes:F1} min -> {Apk}");
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
}
