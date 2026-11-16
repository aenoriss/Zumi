using UnityEngine;

namespace Zumi
{
    /// <summary>
    /// The reader's one fixed seat: where the eyes were when reading began, level, facing the way the reader faced.
    /// This object's transform is the seat (its position the seat's eye, +z the seat's forward); the panel, the voices
    /// and the music are placed around it and stay in the room when the head moves, which is what gives a panel its
    /// parallax. Taken once, when the head has a pose; Reseat takes it again where the head is now.
    /// </summary>
    public class ZumiSeat : MonoBehaviour
    {
        /// <summary>A head lower than this has no pose yet (the first frames on the headset).</summary>
        public const float MinHeadHeight = 0.5f;
        /// <summary>Seconds after which a head still that low is taken as it is.</summary>
        public const float SettleSeconds = 2f;

        public bool Taken { get; private set; }
        /// <summary>The seat's eye, in world space.</summary>
        public Vector3 Position => transform.position;
        public Vector3 Forward => transform.forward;
        public Quaternion Rotation => transform.rotation;
        /// <summary>How many times the seat was taken: 1 after the start, one more per Reseat.</summary>
        public int Seatings { get; private set; }
        /// <summary>While held the seat is not taken by itself: the creation flow takes it when a book opens.</summary>
        public bool Held { get; set; }

        void Update()
        {
            if (Taken || Held || !Camera.main) return;
            if (Camera.main.transform.position.y > MinHeadHeight || Time.timeSinceLevelLoad > SettleSeconds) Take();
        }

        /// <summary>Moves the seat to where the head is now. Nothing happens before the head has a camera.</summary>
        public void Reseat()
        {
            if (Camera.main) Take();
        }

        void Take()
        {
            var head = Camera.main.transform;
            var forward = Vector3.ProjectOnPlane(head.forward, Vector3.up);
            transform.SetPositionAndRotation(head.position, Quaternion.LookRotation(forward.sqrMagnitude > 1e-4f ? forward : Vector3.forward));
            Taken = true;
            Seatings++;
            Debug.Log($"[Zumi] seat: taken at {transform.position:F2}, facing {transform.eulerAngles.y:F0}°");
        }
    }
}
