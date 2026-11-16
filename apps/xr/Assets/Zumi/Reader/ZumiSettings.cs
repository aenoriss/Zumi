using UnityEngine;

namespace Zumi
{
    /// <summary>
    /// What the reader keeps between launches (PlayerPrefs): the two comfort settings of the hand menu and whether
    /// the hint about that menu was already given. A setting nobody ever changed has no entry: the scene's value holds.
    /// </summary>
    public static class ZumiSettings
    {
        const string MotionKey = "zumi.motion", RoomEffectsKey = "zumi.roomEffects", MenuHintKey = "zumi.menuHintSeen";

        public static bool TryMotion(out bool on)
        {
            on = PlayerPrefs.GetInt(MotionKey, 1) != 0;
            return PlayerPrefs.HasKey(MotionKey);
        }

        public static void SaveMotion(bool on) => Save(MotionKey, on ? 1 : 0);

        public static bool TryRoomEffects(out RoomEffects effects)
        {
            effects = (RoomEffects)Mathf.Clamp(PlayerPrefs.GetInt(RoomEffectsKey, 0), 0, (int)RoomEffects.Off);
            return PlayerPrefs.HasKey(RoomEffectsKey);
        }

        public static void SaveRoomEffects(RoomEffects effects) => Save(RoomEffectsKey, (int)effects);

        public static bool MenuHintSeen
        {
            get => PlayerPrefs.GetInt(MenuHintKey, 0) != 0;
            set => Save(MenuHintKey, value ? 1 : 0);
        }

        /// <summary>As on a first launch: no setting kept, the hint not given yet.</summary>
        public static void Forget()
        {
            PlayerPrefs.DeleteKey(MotionKey);
            PlayerPrefs.DeleteKey(RoomEffectsKey);
            PlayerPrefs.DeleteKey(MenuHintKey);
            PlayerPrefs.Save();
        }

        static void Save(string key, int value)
        {
            PlayerPrefs.SetInt(key, value);
            PlayerPrefs.Save();
        }
    }
}
