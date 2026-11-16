// What lies behind a place's meshes in the window: a low dome round the seat's eye (ZumiPlaces builds it, ±100 degrees
// across and ±70 up about the place's forward), so where the hole reaches past the view's edge (the head moved off
// the eye the place was fitted from) the scene goes soft instead of empty. Its colour by direction: inside the view's
// span (_Span: hDeg, vDeg) a heavily blurred copy of the front picture (_MainTex, a few texels wide, its UV clamped so
// the edge colours run on outward); past the edge, over _Fade degrees, toward the place's ambient light by elevation
// (_Sky, _Horizon, _Ground at the picture's mean brightness, _MeanTex). Unlit, no depth, drawn first in the window
// (stencil bit 7, the same window mask as Zumi/Place, ZumiOpening.hlsl); the meshes and their vignette fade over it.
// The mesh's first texture coordinates are each vertex's azimuth and elevation in degrees.
Shader "Zumi/PlaceBackdrop"
{
    Properties
    {
        _MainTex ("Blurred front", 2D) = "grey" {}
        _MeanTex ("Mean colour", 2D) = "grey" {}
        _Opacity ("Opacity", Range(0, 1)) = 1
        _Open ("Open", Range(0, 1)) = 1
        [Toggle] _Broken ("Broken wall", Float) = 0
        _Span ("View span (hDeg, vDeg)", Vector) = (130, 70, 0, 0)
        _Fade ("Degrees past the view's edge to the ambient light", Float) = 15
        _Sky ("Ambient sky", Color) = (0.5, 0.5, 0.5, 0)
        _Horizon ("Ambient horizon", Color) = (0.5, 0.5, 0.5, 0)
        _Ground ("Ambient ground", Color) = (0.5, 0.5, 0.5, 0)
        _Seat ("Seat eye", Vector) = (0, 0, 0, 0)
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
        Tags { "RenderPipeline" = "UniversalPipeline" "Queue" = "Transparent-99" "RenderType" = "Transparent" }
        Pass
        {
            Tags { "LightMode" = "SRPDefaultUnlit" }
            Blend SrcAlpha OneMinusSrcAlpha, One OneMinusSrcAlpha
            ZWrite Off
            ZTest Always
            Cull Off
            Stencil { Ref 128 ReadMask 128 Comp Equal }
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            TEXTURE2D(_MainTex);
            SAMPLER(sampler_MainTex);
            TEXTURE2D(_MeanTex);
            SAMPLER(sampler_MeanTex);
            CBUFFER_START(UnityPerMaterial)
                half _Opacity;
                float _Open;
                float _Broken;
                float4 _Span;
                float _Fade;
                half4 _Sky, _Horizon, _Ground;
                float4 _Seat, _Key, _KeyN, _KeyR, _SideL, _SideLN, _SideR, _SideRN, _CornerL, _CornerR, _SideLA, _SideRA, _Rect, _Round, _Edge;
            CBUFFER_END
            #include "ZumiOpening.hlsl"
            struct A { float4 pos : POSITION; float2 dir : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 pos : SV_POSITION; float2 dir : TEXCOORD0; float3 world : TEXCOORD1; UNITY_VERTEX_OUTPUT_STEREO };
            V vert(A i)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.world = TransformObjectToWorld(i.pos.xyz);
                o.pos = TransformWorldToHClip(o.world);
                o.dir = i.dir;
                return o;
            }

            half4 frag(V i) : SV_Target
            {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                float3 eye = GetCameraPositionWS();
                float3 ray = i.world - eye;
                float3 w0 = ZumiExit(eye, ray, 0.0);
                float2 p0 = ZumiFlat(w0);
                float u;
                float mask = _Opacity * (1.0 - smoothstep(-_Round.y, 0.0, ZumiOutline(p0, u)));
                float toBack = 0.0;
                UNITY_BRANCH
                if (_Broken > 0.5)
                {
                    float m1 = ZumiBroken(ZumiFlat(ZumiExit(eye, ray, _Edge.y)), _Open, 1.0);
                    float s = max(ZumiBroken(p0, _Open, 1.0), m1);
                    mask = _Opacity * (1.0 - smoothstep(-1.5 * fwidth(s), 0.0, s));
                    toBack = smoothstep(-ZUMI_REVEAL_BLEND, 0.0, m1);
                }
                clip(mask - 0.002);

                // the blurred picture by direction, its edge running on outward
                float2 half_span = _Span.xy * 0.5;
                float2 uv = clamp(0.5 + i.dir / _Span.xy, 0.02, 0.98);
                half3 picture = SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, uv).rgb;
                // past the view's edge, toward the ambient light at the picture's brightness
                half3 mean = SAMPLE_TEXTURE2D(_MeanTex, sampler_MeanTex, float2(0.5, 0.5)).rgb;
                half level = dot(mean, half3(0.2126, 0.7152, 0.0722));
                half3 light = i.dir.y >= 0.0 ? lerp(_Horizon.rgb, _Sky.rgb, saturate(i.dir.y / 45.0)) : lerp(_Horizon.rgb, _Ground.rgb, saturate(-i.dir.y / 45.0));
                light *= level / max(dot(light, half3(0.2126, 0.7152, 0.0722)), 1e-3);
                float past = max(abs(i.dir.x) - half_span.x, abs(i.dir.y) - half_span.y);
                half3 colour = lerp(picture, light, smoothstep(0.0, _Fade, past));
                colour = lerp(colour, ZumiLinear(ZUMI_REVEAL_BACK), toBack * 0.85);
                return half4(colour, mask);
            }
            ENDHLSL
        }
    }
}
