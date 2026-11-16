using System;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;
using UnityEngine;
using Zumi.Format;
#if UNITY_ANDROID && !UNITY_EDITOR
using UnityEngine.Networking;
#endif

namespace Zumi
{
    /// <summary>
    /// An episode that ships inside the app, under StreamingAssets. In the editor and on desktop that is a folder and
    /// the .zumi is read in place. On Quest StreamingAssets is inside the APK, which cannot be opened as a file, so
    /// the episode is copied once to persistentDataPath and read there; a stamp next to the copy (the APK's size and
    /// date, the copy's size) says whether it is still the one this install shipped.
    /// </summary>
    public sealed class ZumiShippedEpisode : IEpisodeSource
    {
        readonly string streamingPath;
        ZumiZipFile zip;

        public EpisodeSourceState State { get; private set; } = EpisodeSourceState.Closed;
        public string Error { get; private set; }
        public ZumiManifest Manifest { get; private set; }

        /// <param name="streamingPath">Path under StreamingAssets, e.g. Episodes/dan-buck.zumi.</param>
        public ZumiShippedEpisode(string streamingPath) => this.streamingPath = streamingPath;

        public async Task Open(CancellationToken cancel)
        {
            State = EpisodeSourceState.Opening;
            try
            {
                var file = await LocalFile(cancel);
                (zip, Manifest) = await Task.Run(() =>
                {
                    var z = new ZumiZipFile(file);
                    var json = z.Read("manifest.json", cancel) ?? throw new InvalidDataException("no manifest.json");
                    return (z, JsonConvert.DeserializeObject<ZumiManifest>(Encoding.UTF8.GetString(json)));
                }, cancel);
                State = EpisodeSourceState.Ready;
            }
            catch (Exception e)
            {
                Error = $"{streamingPath}: {e.Message}";
                State = EpisodeSourceState.Failed;
            }
        }

        public Task<byte[]> Read(string path, CancellationToken cancel)
        {
            var z = zip;
            if (z == null || !z.Has(path)) return Task.FromResult<byte[]>(null);
            return Task.Run(() => z.Read(path, cancel), cancel);
        }

        public void Dispose()
        {
            zip = null;
            Manifest = null;
            State = EpisodeSourceState.Closed;
        }

#if UNITY_ANDROID && !UNITY_EDITOR
        async Task<string> LocalFile(CancellationToken cancel)
        {
            var copy = Path.Combine(Application.persistentDataPath, streamingPath);
            var stampFile = copy + ".stamp";
            var apk = new FileInfo(Application.dataPath);
            var shipped = $"{apk.Length}:{apk.LastWriteTimeUtc.Ticks}";
            if (File.Exists(copy) && File.Exists(stampFile) && File.ReadAllText(stampFile) == $"{shipped}:{new FileInfo(copy).Length}")
                return copy;

            Directory.CreateDirectory(Path.GetDirectoryName(copy));
            var part = copy + ".part";
            // straight to disk: the download handler never holds the file
            using (var request = UnityWebRequest.Get(Path.Combine(Application.streamingAssetsPath, streamingPath)))
            {
                request.downloadHandler = new DownloadHandlerFile(part) { removeFileOnAbort = true };
                var sent = request.SendWebRequest();
                while (!sent.isDone)
                {
                    if (cancel.IsCancellationRequested) request.Abort();
                    await Task.Yield();
                }
                cancel.ThrowIfCancellationRequested();
                if (request.result != UnityWebRequest.Result.Success) throw new IOException(request.error);
            }
            if (File.Exists(copy)) File.Delete(copy);
            File.Move(part, copy);
            File.WriteAllText(stampFile, $"{shipped}:{new FileInfo(copy).Length}");
            return copy;
        }
#else
        Task<string> LocalFile(CancellationToken cancel) => Task.FromResult(Path.Combine(Application.streamingAssetsPath, streamingPath));
#endif
    }
}
