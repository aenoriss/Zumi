using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Text;
using System.Threading;

namespace Zumi
{
    /// <summary>
    /// A .zumi on disk, read one member at a time. The central directory is parsed once (a few kB: where each member
    /// starts, its size, whether it is deflated); a read opens the file, seeks to the member and returns only that
    /// member's bytes, so the archive itself is never in memory. Each read has its own FileStream: reads may run on
    /// any thread, several at once. Stored and deflated members only, which is all the format's writer makes.
    /// </summary>
    public sealed class ZumiZipFile
    {
        readonly struct Member
        {
            public readonly long headerOffset, packedSize, size;
            public readonly bool deflated;

            public Member(long headerOffset, long packedSize, long size, bool deflated)
            {
                this.headerOffset = headerOffset;
                this.packedSize = packedSize;
                this.size = size;
                this.deflated = deflated;
            }
        }

        const uint EndSignature = 0x06054b50, End64LocatorSignature = 0x07064b50, End64Signature = 0x06064b50;
        const uint CentralSignature = 0x02014b50, LocalSignature = 0x04034b50;
        const int EndSize = 22, MaxComment = 65535, CentralSize = 46, LocalSize = 30;
        const int ReadBuffer = 1 << 16;

        readonly string file;
        readonly Dictionary<string, Member> members = new(StringComparer.Ordinal);

        public string File => file;
        public int Count => members.Count;

        /// <summary>Reads the directory. Throws IOException or InvalidDataException when the file is not a zip.</summary>
        public ZumiZipFile(string file)
        {
            this.file = file;
            using var s = OpenStream();
            ReadDirectory(s);
        }

        public bool Has(string path) => !string.IsNullOrEmpty(path) && members.ContainsKey(path);

        /// <summary>The member's bytes in an array of exactly its size; null when there is no such member.</summary>
        public byte[] Read(string path, CancellationToken cancel = default)
        {
            if (string.IsNullOrEmpty(path) || !members.TryGetValue(path, out var m)) return null;
            if (m.size > int.MaxValue) throw new InvalidDataException($"{path}: {m.size} bytes, over what one array holds");
            using var s = OpenStream();
            var header = new byte[LocalSize];
            s.Seek(m.headerOffset, SeekOrigin.Begin);
            Fill(s, header, LocalSize, cancel);
            if (BitConverter.ToUInt32(header, 0) != LocalSignature) throw new InvalidDataException($"{path}: no local header at {m.headerOffset}");
            s.Seek(BitConverter.ToUInt16(header, 26) + BitConverter.ToUInt16(header, 28), SeekOrigin.Current);
            var bytes = new byte[m.size];
            if (!m.deflated) Fill(s, bytes, bytes.Length, cancel);
            else
            {
                using var inflate = new DeflateStream(s, CompressionMode.Decompress, leaveOpen: true);
                Fill(inflate, bytes, bytes.Length, cancel);
            }
            return bytes;
        }

        FileStream OpenStream() => new(file, FileMode.Open, FileAccess.Read, FileShare.Read, ReadBuffer, FileOptions.RandomAccess);

        // in slices, so a cancelled read of a large member stops within one slice
        static void Fill(Stream s, byte[] into, int count, CancellationToken cancel)
        {
            var done = 0;
            while (done < count)
            {
                cancel.ThrowIfCancellationRequested();
                var n = s.Read(into, done, Math.Min(count - done, 1 << 20));
                if (n <= 0) throw new EndOfStreamException("the archive ends inside a member");
                done += n;
            }
        }

        void ReadDirectory(FileStream s)
        {
            // the end record is the last thing in the file, before an optional comment
            var tailSize = (int)Math.Min(s.Length, EndSize + MaxComment);
            var tail = new byte[tailSize];
            s.Seek(-tailSize, SeekOrigin.End);
            Fill(s, tail, tailSize, default);
            var end = -1;
            for (var i = tailSize - EndSize; i >= 0; i--)
                if (BitConverter.ToUInt32(tail, i) == EndSignature) { end = i; break; }
            if (end < 0) throw new InvalidDataException("not a zip: no end record");
            long count = BitConverter.ToUInt16(tail, end + 10);
            long size = BitConverter.ToUInt32(tail, end + 12);
            long offset = BitConverter.ToUInt32(tail, end + 16);
            // a zip64 archive (over 4 GB or 65535 members) keeps the real numbers in a record the locator points at
            if (count == ushort.MaxValue || size == uint.MaxValue || offset == uint.MaxValue)
            {
                var locator = end - 20;
                if (locator < 0 || BitConverter.ToUInt32(tail, locator) != End64LocatorSignature) throw new InvalidDataException("zip64 locator missing");
                var end64 = new byte[56];
                s.Seek(BitConverter.ToInt64(tail, locator + 8), SeekOrigin.Begin);
                Fill(s, end64, end64.Length, default);
                if (BitConverter.ToUInt32(end64, 0) != End64Signature) throw new InvalidDataException("zip64 end record missing");
                count = BitConverter.ToInt64(end64, 32);
                size = BitConverter.ToInt64(end64, 40);
                offset = BitConverter.ToInt64(end64, 48);
            }

            var dir = new byte[size];
            s.Seek(offset, SeekOrigin.Begin);
            Fill(s, dir, dir.Length, default);
            var at = 0;
            for (long i = 0; i < count; i++)
            {
                if (at + CentralSize > dir.Length || BitConverter.ToUInt32(dir, at) != CentralSignature) throw new InvalidDataException($"directory entry {i} is damaged");
                var method = BitConverter.ToUInt16(dir, at + 10);
                long packed = BitConverter.ToUInt32(dir, at + 20);
                long plain = BitConverter.ToUInt32(dir, at + 24);
                int nameLength = BitConverter.ToUInt16(dir, at + 28), extraLength = BitConverter.ToUInt16(dir, at + 30);
                int commentLength = BitConverter.ToUInt16(dir, at + 32);
                long header = BitConverter.ToUInt32(dir, at + 42);
                var name = Encoding.UTF8.GetString(dir, at + CentralSize, nameLength);
                // zip64 extra field: the 8-byte values of whichever 4-byte fields are saturated, in this order
                for (int x = at + CentralSize + nameLength, stop = x + extraLength; x + 4 <= stop;)
                {
                    int id = BitConverter.ToUInt16(dir, x), length = BitConverter.ToUInt16(dir, x + 2);
                    if (id == 1)
                    {
                        var v = x + 4;
                        if (plain == uint.MaxValue) { plain = BitConverter.ToInt64(dir, v); v += 8; }
                        if (packed == uint.MaxValue) { packed = BitConverter.ToInt64(dir, v); v += 8; }
                        if (header == uint.MaxValue) header = BitConverter.ToInt64(dir, v);
                    }
                    x += 4 + length;
                }
                if (method != 0 && method != 8) throw new InvalidDataException($"{name}: compression method {method} (only stored and deflated are read)");
                if (!name.EndsWith("/")) members[name] = new Member(header, packed, plain, method == 8);
                at += CentralSize + nameLength + extraLength + commentLength;
            }
        }
    }
}
