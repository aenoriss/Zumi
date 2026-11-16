using System;
using System.Threading;
using System.Threading.Tasks;
using Zumi.Format;

namespace Zumi
{
    public enum EpisodeSourceState { Closed, Opening, Ready, Failed }

    /// <summary>
    /// Where an episode's files come from. The reader asks for the manifest once and then for one file at a time, by
    /// its path in the .zumi; it never sees the archive. Episodes ship inside the app today (ZumiShippedEpisode); a
    /// download replaces that class and nothing else.
    /// </summary>
    public interface IEpisodeSource : IDisposable
    {
        EpisodeSourceState State { get; }
        /// <summary>Why it is Failed; null otherwise.</summary>
        string Error { get; }
        /// <summary>Null until Ready.</summary>
        ZumiManifest Manifest { get; }

        /// <summary>Call from the main thread. Never throws: it ends Ready or Failed.</summary>
        Task Open(CancellationToken cancel);

        /// <summary>A file's bytes, read off the main thread; null when the episode has no such file.</summary>
        Task<byte[]> Read(string path, CancellationToken cancel);
    }
}
