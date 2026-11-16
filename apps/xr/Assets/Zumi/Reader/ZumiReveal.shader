// The reveal: the wall's thickness inside a place's window in a real wall, as geometry. A short tunnel from the
// window's outline on the wall's surface (ZumiOpening.hlsl: notched like a broken wall, grown from the middle by
// _Open, eased to a plain rounded edge past a corner) straight back into the wall _Edge.y metres, each side along its
// own wall's normal, so on a fold it bends on the corner line with the outline. The mesh (ZumiPlaces) only carries,
// per vertex, u around the outline and 0 at the wall's face or 1 at the far end; the vertex shader puts it on the
// walls, so its mouth is the outline the place and the cracks are cut to. Seen only through the hole: a pixel whose
// line of sight crosses the wall's face outside the outline is not drawn, so from off to one side more of the far
// side shows and the near side hides behind the real wall, as a real hole's would. Unlit, a fixed shading: plaster,
// darker toward the far end, the sill lighter than the lintel, a faint grain and brick showing through deep in.
Shader "Zumi/Reveal"
{
    Properties
    {
        _Opacity ("Opacity", Range(0, 1)) = 1
        _Open ("Open", Range(0, 1)) = 1
        _Notched ("Notched (broken wall)", Range(0, 1)) = 1
        _Key ("Key wall point", Vector) = (0, 0, 2, 0)
        _KeyN ("Key wall normal (into the room)", Vector) = (0, 0, -1, 0)
        _KeyR ("Key wall right", Vector) = (1, 0, 0, 0)
        _SideL ("Left side wall point (w: folds)", Vector) = (0, 0, 0, 0)
        _SideLN ("Left side wall normal", Vector) = (1, 0, 0, 0)
        _SideR ("Right side wall point (w: folds)", Vector) = (0, 0, 0, 0)
        _SideRN ("Right side wall normal", Vector) = (-1, 0, 0, 0)
        _CornerL ("Left corner point (w: metres along the walls)", Vector) = (0, 0, 0, 0)
        _CornerR ("Right corner point (w: metres along the walls)", Vector) = (0, 0, 0, 0)
        _SideLA ("Along the left side wall into the room", Vector) = (0, 0, -1, 0)
        _SideRA ("Along the right side wall into the room", Vector) = (0, 0, -1, 0)
        _Rect ("Window along the walls (from, to) and up (bottom, top), metres", Vector) = (-2, 2, 0.2, 2.4)
        _Round ("Corner radius, soft edge width (metres)", Vector) = (0.45, 0.4, 0, 0)
        _Edge ("-, reveal depth, side-wall break, corner fade", Vector) = (0, 0.15, 0, 0.15)
    }
    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "Queue" = "Transparent-96" "RenderType" = "Transparent" }
        Pass
        {
            Tags { "LightMode" = "SRPDefaultUnlit" }
            Blend SrcAlpha OneMinusSrcAlpha, One OneMinusSrcAlpha
            ZWrite On
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
                float _Notched;
                float4 _Key, _KeyN, _KeyR, _SideL, _SideLN, _SideR, _SideRN, _CornerL, _CornerR, _SideLA, _SideRA, _Rect, _Round, _Edge;
            CBUFFER_END
            #include "ZumiOpening.hlsl"
            struct A { float4 pos : POSITION; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 pos : SV_POSITION; float3 world : TEXCOORD0; float2 shade : TEXCOORD1; UNITY_VERTEX_OUTPUT_STEREO };

            V vert(A i)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                float open = max(_Open, 1e-3);
                float2 p = ZumiEdgeAt(i.uv.x, open, _Notched);
                float3 n;
                float3 w = ZumiWall(p, n) - n * (_Edge.y * i.uv.y);
                o.world = w;
                o.pos = TransformWorldToHClip(w);
                // which way the side faces: up on the sill (the outline's bottom), down under the lintel
                float2 c = float2(_Rect.x + _Rect.y, _Rect.z + _Rect.w) * 0.5;
                float2 h = float2(_Rect.y - _Rect.x, _Rect.w - _Rect.z) * 0.5;
                float2 out2 = normalize((p - c) / (h * h));
                o.shade = float2(i.uv.y, -out2.y);
                return o;
            }

            float Hash3(float3 p) { return frac(sin(dot(p, float3(127.1, 311.7, 74.7))) * 43758.5453); }

            float Noise3(float3 p)
            {
                float3 i = floor(p), f = frac(p);
                f = f * f * (3.0 - 2.0 * f);
                return lerp(lerp(lerp(Hash3(i), Hash3(i + float3(1, 0, 0)), f.x), lerp(Hash3(i + float3(0, 1, 0)), Hash3(i + float3(1, 1, 0)), f.x), f.y),
                            lerp(lerp(Hash3(i + float3(0, 0, 1)), Hash3(i + float3(1, 0, 1)), f.x), lerp(Hash3(i + float3(0, 1, 1)), Hash3(i + float3(1, 1, 1)), f.x), f.y), f.z);
            }

            half4 frag(V i) : SV_Target
            {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                float3 eye = GetCameraPositionWS();
                float3 ray = i.world - eye;
                // seen only through the hole: where the line of sight crosses the wall's face inside the outline
                float m0 = ZumiBroken(ZumiFlat(ZumiExit(eye, ray, 0.0)), max(_Open, 1e-3), _Notched);
                float aa = max(fwidth(m0), 1e-4);
                float through = 1.0 - smoothstep(-aa, 0.5 * aa, m0);
                clip(through - 0.002);

                float deep = saturate(i.shade.x);
                float3 tone = lerp(ZUMI_REVEAL_FRONT, ZUMI_REVEAL_BACK, pow(deep, 0.7));
                tone *= 0.78 + 0.22 * i.shade.y;
                // grain, and here and there brick through the plaster deeper in
                float3 q = i.world;
                float grain = Noise3(q * 40.0) * 0.6 + Noise3(q * 120.0) * 0.4;
                tone *= 0.88 + 0.24 * grain;
                float patch = smoothstep(0.55, 0.75, Noise3(q * 7.0 + 3.1)) * smoothstep(0.1, 0.4, deep);
                float mortar = smoothstep(0.40, 0.47, abs(frac(q.y / 0.075) - 0.5));
                float3 brick = lerp(float3(0.42, 0.26, 0.2), float3(0.5, 0.48, 0.44), mortar) * lerp(1.0, 0.35, deep);
                tone = lerp(tone, brick, 0.35 * patch);
                return half4(ZumiLinear(tone), through * saturate(_Opacity * 3.0));
            }
            ENDHLSL
        }
    }
}
