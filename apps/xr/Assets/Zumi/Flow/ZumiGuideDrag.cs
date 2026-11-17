using System;
using Oculus.Interaction;
using Oculus.Interaction.Grab;
using Oculus.Interaction.GrabAPI;
using Oculus.Interaction.HandGrab;
using Oculus.Interaction.Surfaces;
using UnityEngine;

namespace Zumi
{
    /// <summary>
    /// The scan guide's grip: a hand grab (pinch or palm) or a ray and a pinch takes it, and the guide slides with the
    /// hand in its table's plane only: the hand's motion, flattened, moves it; its height and turn never change, and
    /// Clamp keeps it on the table. It follows the hand smoothly rather than jumping. The Interaction SDK's Grabbable
    /// calls this as its one-grab transformer.
    /// </summary>
    public class ZumiGuideDrag : MonoBehaviour, ITransformer
    {
        /// <summary>How fast the guide closes on where the hand puts it (per second, exponential).</summary>
        public const float Follow = 18f;

        public Transform Guide { get; private set; }
        /// <summary>Where the guide is going; the guide eases to it.</summary>
        public Vector3 Target { get; private set; }
        public bool Dragging { get; private set; }
        public bool Hovered => (hand && hand.State != InteractableState.Normal) || (ray && ray.State != InteractableState.Normal);
        /// <summary>Metres the guide has been slid since it was laid.</summary>
        public float Slid { get; private set; }

        Func<Vector3, Vector3> clamp;
        IGrabbable grabbable;
        HandGrabInteractable hand;
        RayInteractable ray;
        Vector3 grabFrom, guideFrom;

        /// <summary>The grip on an inactive object (the SDK's parts read their fields when they wake): a box the size
        /// given, grabbable by hand and by ray, moving the guide.</summary>
        public static ZumiGuideDrag Make(GameObject grip, Transform guide, Vector3 size, Func<Vector3, Vector3> clamp)
        {
            var drag = grip.AddComponent<ZumiGuideDrag>();
            drag.Guide = guide;
            drag.clamp = clamp;
            drag.Target = guide.position;
            var box = grip.AddComponent<BoxCollider>();
            box.size = size;
            var body = grip.AddComponent<Rigidbody>();
            body.isKinematic = true;
            body.useGravity = false;
            var grabbable = grip.AddComponent<Grabbable>();
            grabbable.InjectOptionalRigidbody(body);
            grabbable.InjectOptionalThrowWhenUnselected(false);
            grabbable.InjectOptionalTargetTransform(guide);
            grabbable.InjectOptionalOneGrabTransformer(drag);
            grabbable.MaxGrabPoints = 1;
            drag.hand = grip.AddComponent<HandGrabInteractable>();
            drag.hand.InjectAllHandGrabInteractable(GrabTypeFlags.Pinch | GrabTypeFlags.Palm, body, GrabbingRule.DefaultPinchRule, GrabbingRule.DefaultPalmRule);
            drag.hand.InjectOptionalPointableElement(grabbable);
            var surface = grip.AddComponent<ColliderSurface>();
            surface.InjectAllColliderSurface(box);
            drag.ray = grip.AddComponent<RayInteractable>();
            drag.ray.InjectAllRayInteractable(surface);
            drag.ray.InjectOptionalPointableElement(grabbable);
            return drag;
        }

        public void Initialize(IGrabbable target) => grabbable = target;

        public void BeginTransform()
        {
            grabFrom = grabbable.GrabPoints[0].position;
            guideFrom = Target;
            Dragging = true;
            Debug.Log($"[ZumiScan] guide grabbed at {Guide.position:F3}");
        }

        public void UpdateTransform()
        {
            var moved = grabbable.GrabPoints[0].position - grabFrom;
            moved.y = 0f;
            var to = clamp(guideFrom + moved);
            to.y = guideFrom.y;
            Target = to;
        }

        public void EndTransform()
        {
            Dragging = false;
            Debug.Log($"[ZumiScan] guide let go at {Target:F3}");
        }

        void Update()
        {
            if (!Guide) return;
            var p = Guide.position;
            var next = Vector3.Lerp(p, Target, 1f - Mathf.Exp(-Follow * Time.deltaTime));
            next.y = Target.y;
            Slid += (next - p).magnitude;
            Guide.position = next;
        }
    }
}
