using UnityEngine;
using UnityEngine.XR;

namespace Zumi
{
    /// <summary>
    /// Without a headset (the editor in Play without XR, SmithXR's skip_xr) the head has no pose and sits on the floor,
    /// so the room, the Zumis and the reader were seen from 0 m. This puts the head at a standing eye height then.
    /// Only the head: MRUK places the room in the tracking space, so moving that would lift the floor with it. Only a
    /// head with no pose at all (exactly at the origin): one a headset or SmithXR's set_head placed is left alone.
    /// </summary>
    [RequireComponent(typeof(OVRCameraRig))]
    public class ZumiDesktopHead : MonoBehaviour
    {
        [Tooltip("Eye height without a headset, metres (standing adult ~1.6, seated ~1.2)")]
        public float eyeHeight = 1.6f;

        OVRCameraRig rig;

        void Awake() => rig = GetComponent<OVRCameraRig>();

        // the rig does not update its anchors without a headset, so nothing else moves the head between frames
        void LateUpdate()
        {
            if (XRSettings.isDeviceActive) return;
            foreach (var eye in new[] { rig.centerEyeAnchor, rig.leftEyeAnchor, rig.rightEyeAnchor })
                if (eye && eye.localPosition.sqrMagnitude < 1e-8f) eye.localPosition = Vector3.up * eyeHeight;
        }
    }
}
