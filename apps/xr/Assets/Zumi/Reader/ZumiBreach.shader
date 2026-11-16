// The edge around a place's window, one quad per wall the window lies on (ZumiPlaces), on the outline the place is cut
// to (ZumiOpening.hlsl): a rounded rectangle following the wall, unbroken across a fold onto a side wall. Kept subtle.
//   broken wall (in a real wall): it only darkens (black at a low alpha), so it reads on a wall of any colour seen
//     through passthrough. The hole's inner side: the wall is _Edge.y metres thick; where the line of sight enters the
//     hole but meets the wall's back face outside it, it sees the inner side, a little darker the deeper, worked out
//     per pixel from the eye so it moves with the head as a real hole's would. On the wall a faint line along the
//     notched edge, a faint contact shadow and a few hairline cracks. At full strength on the key wall only: past the
//     corner it eases, within _Edge.w metres along the side wall, to _Edge.z of itself (0: none on a side wall).
//   rift (_Rift: standing free, no wall): only a faint pale rim, shimmering slowly, where the place's soft edge ends.
// The whole figure grows from the middle by _Open while the place fades in. No stencil: it is on the wall.
Shader "Zumi/Breach"
{
    Properties
    {
        _Opacity ("Opacity", Range(0, 1)) = 1
        _Open ("Open", Range(0, 1)) = 1
        [Toggle] _Rift ("Rift (standing free)", Float) = 0
        _Key ("Key wall point", Vector) = (0, 0, 2, 0)
        _KeyN ("Key wall normal (into the room)", Vector) = (0, 0, -1, 0)
        _KeyR ("Key wall right", Vector) = (1, 0, 0, 0)
        _SideL ("Left side wall point (w: folds)", Vector) = (0, 0, 0, 0)
        _SideLN ("Left side wall normal", Vector) = (1, 0, 0, 0)
        _SideR ("Right side wall point (w: folds)", Vector) = (0, 0, 0, 0)
        _SideRN ("Right side wall normal", Vector) = (-1, 0, 0, 0)
        _Rect ("Window along the walls (from, to) and up (bottom, top), metres", Vector) = (-2, 2, 0.2, 2.4)
        _Round ("Corner radius, soft edge width (metres)", Vector) = (0.45, 0.4, 0, 0)
        _Edge ("-, wall thickness, side-wall break, corner fade", Vector) = (0, 0.15, 0, 0.15)
    }
    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "Queue" = "Transparent-96" "RenderType" = "Transparent" }
        Pass
        {
            Tags { "LightMode" = "SRPDefaultUnlit" }
            Blend SrcAlpha OneMinusSrcAlpha, One OneMinusSrcAlpha
            ZWrite Off
            ZTest LEqual
            Cull Off
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            CBUFFER_START(UnityPerMaterial)
                float _Opacity;
                float _Open;
                float _Rift;
                float4 _Key, _KeyN, _KeyR, _SideL, _SideLN, _SideR, _SideRN, _Rect, _Round, _Edge;
            CBUFFER_END
            #include "ZumiOpening.hlsl"
            struct A { float4 pos : POSITION; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 pos : SV_POSITION; float3 world : TEXCOORD0; UNITY_VERTEX_OUTPUT_STEREO };
            V vert(A i)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.world = TransformObjectToWorld(i.pos.xyz);
                o.pos = TransformWorldToHClip(o.world);
                return o;
            }

            half4 frag(V i) : SV_Target
            {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                float3 eye = GetCameraPositionWS();
                float3 ray = i.world - eye;
                float open = max(_Open, 1e-3);
                float3 w0 = ZumiExit(eye, ray, 0.0);
                float2 p0 = ZumiFlat(w0);

                UNITY_BRANCH
                if (_Rift > 0.5)
                {
                    float u;
                    float2 c = float2(_Rect.x + _Rect.y, _Rect.z + _Rect.w) * 0.5;
                    float d = ZumiOutline(c + (p0 - c) / open, u);
                    float ring = exp(-pow((d + 0.04) / 0.035, 2.0)) + 0.3 * exp(-pow((d + 0.15) / 0.1, 2.0));
                    float shimmer = 0.45 + 0.55 * ZumiJag(frac(u + _Time.y * 0.015), 37.0, 5.0) * (0.5 + ZumiJag(frac(u - _Time.y * 0.011), 23.0, 9.0));
                    return half4(0.82, 0.92, 1.0, saturate(0.15 * ring * shimmer) * saturate(_Opacity * 1.5));
                }

                float m0 = ZumiBroken(p0, open);
                float m1 = ZumiBroken(ZumiFlat(ZumiExit(eye, ray, _Edge.y)), open);
                float aa = max(fwidth(m0), 1e-4);
                float alpha = 0.0;

                // the hole's inner side: entered at the front, blocked at the back
                float inside = 1.0 - smoothstep(-aa, 0.0, m0);
                float blocked = smoothstep(-1.5 * max(fwidth(m1), 1e-4), 0.0, m1);
                float deep = saturate(m0 / min(m0 - m1, -1e-4));
                alpha = max(alpha, inside * blocked * lerp(0.05, 0.28, deep));

                // on the wall: a faint line along the edge, a faint contact shadow
                float onWall = smoothstep(-aa, 0.0, m0);
                alpha = max(alpha, onWall * (1.0 - smoothstep(0.004, 0.004 + aa, m0)) * 0.22);
                alpha = max(alpha, onWall * (1.0 - smoothstep(0.0, 0.08, m0)) * 0.1);

                // hairline cracks: in some of 17 sectors around, one from the edge outward, wandering, thinning out
                float2 c = float2(_Rect.x + _Rect.y, _Rect.z + _Rect.w) * 0.5;
                float2 h = float2(_Rect.y - _Rect.x, _Rect.w - _Rect.z) * 0.5;
                float2 n = (p0 - c) / h;
                float u = atan2(n.y, n.x) / 6.2831853 + 0.5;
                float k = floor(u * 17.0);
                float has = step(0.6, ZumiHash(k + 41.0));
                float uc = (k + 0.25 + 0.5 * ZumiHash(k + 7.0)) / 17.0;
                float reach = 0.15 + 0.3 * ZumiHash(k + 19.0);
                float along = saturate(m0 / reach);
                float wander = (ZumiJag1(m0 * 9.0, k * 3.7) - 0.5) * 0.08 + (ZumiJag1(m0 * 30.0, k * 5.1) - 0.5) * 0.02;
                float across = abs((u - uc) * 6.2831853 * length(n * h) - wander);
                float width = 0.003 * (1.0 - along) + 0.001;
                float crack = has * step(0.0, m0) * step(m0, reach) * (1.0 - smoothstep(width, width + 1.5 * fwidth(across), across));
                alpha = max(alpha, 0.25 * crack * (1.0 - along));

                // full strength on the key wall; past the corner, eased to the side walls' share
                float key = lerp(_Edge.z, 1.0, 1.0 - smoothstep(0.0, _Edge.w, ZumiPast(w0)));
                return half4(0, 0, 0, alpha * key * saturate(_Opacity * 3.0));
            }
            ENDHLSL
        }
    }
}
