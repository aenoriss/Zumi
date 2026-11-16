using Oculus.Interaction;
using Oculus.Interaction.Grab;
using Oculus.Interaction.GrabAPI;
using Oculus.Interaction.HandGrab;
using UnityEngine;

namespace Zumi
{
    /// <summary>
    /// A small prop of a place that a hand can pick up: a pinch or a palm grab (Interaction SDK HandGrab) takes it,
    /// and when it is let go it glides back to where it stood (Home, set by ZumiPlaces when it places it). Furniture
    /// never gets one. It fades with its place like any prop: this only moves it.
    /// </summary>
    public class ZumiGrabbableProp : MonoBehaviour
    {
        public const float ReturnSeconds = 0.7f;

        public Pose Home { get; private set; }
        public bool Held => grabbable && grabbable.SelectingPointsCount > 0;
        /// <summary>How many times it was picked up.</summary>
        public int Pickups { get; private set; }
        public bool Returning => returnFrom >= 0f;

        Grabbable grabbable;
        bool wasHeld;
        float returnFrom = -1f;
        Pose released;

        /// <summary>Makes a prop's object grabbable, its collider fitted to its mesh. Called once per prop.</summary>
        public static ZumiGrabbableProp Attach(GameObject prop, Bounds localBounds)
        {
            var grab = prop.GetComponent<ZumiGrabbableProp>();
            if (grab) return grab;
            var was = prop.activeSelf;
            prop.SetActive(false);
            grab = prop.AddComponent<ZumiGrabbableProp>();
            grab.grabbable = MakeGrabbable(prop, localBounds);
            prop.SetActive(was);
            return grab;
        }

        /// <summary>A kinematic body, a box collider and the Interaction SDK's Grabbable with a HandGrabInteractable
        /// (pinch and palm). The object must be inactive: the SDK's parts read their fields when they wake.</summary>
        public static Grabbable MakeGrabbable(GameObject go, Bounds localBounds)
        {
            var box = go.AddComponent<BoxCollider>();
            box.center = localBounds.center;
            box.size = Vector3.Max(localBounds.size, Vector3.one * 0.02f / Mathf.Max(go.transform.lossyScale.x, 1e-4f));
            var body = go.AddComponent<Rigidbody>();
            body.isKinematic = true;
            body.useGravity = false;
            var grabbable = go.AddComponent<Grabbable>();
            grabbable.InjectOptionalRigidbody(body);
            grabbable.InjectOptionalThrowWhenUnselected(false);
            var hand = go.AddComponent<HandGrabInteractable>();
            hand.InjectAllHandGrabInteractable(GrabTypeFlags.Pinch | GrabTypeFlags.Palm, body, GrabbingRule.DefaultPinchRule, GrabbingRule.DefaultPalmRule);
            hand.InjectOptionalPointableElement(grabbable);
            return grabbable;
        }

        /// <summary>Where the prop stands; it goes back there when let go.</summary>
        public void SetHome(Vector3 position, Quaternion rotation)
        {
            Home = new Pose(position, rotation);
            returnFrom = -1f;
        }

        void Update()
        {
            var held = Held;
            if (held && !wasHeld)
            {
                Pickups++;
                returnFrom = -1f;
                Debug.Log($"[Zumi] props: {name} picked up");
            }
            if (!held && wasHeld)
            {
                released = new Pose(transform.position, transform.rotation);
                returnFrom = Time.time;
            }
            wasHeld = held;
            if (returnFrom < 0f) return;
            var t = (Time.time - returnFrom) / ReturnSeconds;
            var k = ZumiFlowKit.Smooth(t);
            // a little arc, so it is carried back rather than slid
            var lift = Mathf.Sin(Mathf.Clamp01(t) * Mathf.PI) * 0.05f;
            transform.SetPositionAndRotation(Vector3.Lerp(released.position, Home.position, k) + Vector3.up * lift, Quaternion.Slerp(released.rotation, Home.rotation, k));
            if (t >= 1f) returnFrom = -1f;
        }
    }
}
