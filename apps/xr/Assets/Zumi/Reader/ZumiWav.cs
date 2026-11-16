using System;
using System.IO;
using System.Text;

namespace Zumi
{
    /// <summary>
    /// A 16-bit PCM WAV file's samples, read from its bytes in memory (Unity decodes compressed audio only from a
    /// file or a URL, which is why the format ships PCM). Read runs off the main thread; the AudioClip is made from
    /// the result on it.
    /// </summary>
    public sealed class ZumiWav
    {
        public int channels;
        public int sampleRate;
        /// <summary>Samples per channel.</summary>
        public int frames;
        /// <summary>One array per channel, -1..1.</summary>
        public float[][] samples;

        public double Seconds => sampleRate > 0 ? (double)frames / sampleRate : 0d;

        public static ZumiWav Read(byte[] file)
        {
            if (file == null || file.Length < 44 || Tag(file, 0) != "RIFF" || Tag(file, 8) != "WAVE") throw new InvalidDataException("not a WAV file");
            int channels = 0, rate = 0, bits = 0, format = 0;
            // chunks follow the 12-byte header: a tag, a length, the data, padded to an even length
            for (var at = 12; at + 8 <= file.Length;)
            {
                var tag = Tag(file, at);
                var length = BitConverter.ToInt32(file, at + 4);
                var body = at + 8;
                if (tag == "fmt ")
                {
                    format = BitConverter.ToUInt16(file, body);
                    channels = BitConverter.ToUInt16(file, body + 2);
                    rate = BitConverter.ToInt32(file, body + 4);
                    bits = BitConverter.ToUInt16(file, body + 14);
                }
                else if (tag == "data")
                {
                    if (format != 1 || bits != 16 || channels < 1) throw new InvalidDataException($"only 16-bit PCM is read (format {format}, {bits} bits, {channels} channels)");
                    length = Math.Min(length < 0 ? int.MaxValue : length, file.Length - body);
                    var wav = new ZumiWav { channels = channels, sampleRate = rate, frames = length / (2 * channels), samples = new float[channels][] };
                    for (var c = 0; c < channels; c++)
                    {
                        var one = wav.samples[c] = new float[wav.frames];
                        for (int i = 0, p = body + 2 * c; i < one.Length; i++, p += 2 * channels)
                            one[i] = (short)(file[p] | file[p + 1] << 8) / 32768f;
                    }
                    return wav;
                }
                at = body + length + (length & 1);
            }
            throw new InvalidDataException("no samples in the WAV file");
        }

        static string Tag(byte[] file, int at) => Encoding.ASCII.GetString(file, at, 4);
    }
}
