using Meta.XR.MRUtilityKit;
using UnityEngine;
using UnityEngine.XR;

namespace Zumi
{
    /// <summary>
    /// The Effect Mesh draws MRUK's room (walls, floor, furniture) so the editor without a headset, which has no
    /// passthrough, shows the space the Zumis spawn in. With a headset (a Quest build, or the editor over Link)
    /// passthrough shows the real room, so the mesh stays hidden; re-applied while the room loads, since MRUK
    /// builds the meshes a moment after Play starts.
    /// </summary>
    [RequireComponent(typeof(EffectMesh))]
    public class ZumiEditorRoom : MonoBehaviour
    {
        EffectMesh mesh;

        void Awake() => mesh = GetComponent<EffectMesh>();

        void Update()
        {
            var headset = XRSettings.isDeviceActive;
            if (mesh.HideMesh != headset) mesh.HideMesh = headset;
            if (headset && Time.timeSinceLevelLoad > 20f) enabled = false;
        }
    }
}
