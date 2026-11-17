// A place's mesh (front or back): its painted view, unlit, seen only through the room's window (stencil bit 7,
// Zumi/Portal). Each vertex carries, in its second texture coordinates, how much of it shows by its direction from
// the seat (the vignette over the view's measured span). Each pixel is masked by the window (ZumiOpening.hlsl), found
// where the line of sight leaves the room through the window's planes: a rounded rectangle following the wall, laid
// along the walls so it runs on unbroken where it folds onto a side wall:
//   plain   whole inside, fading smoothly to nothing over _Round.y metres up to its outline;
//   broken  (_Broken) the broken wall's notched edge, grown from the middle by _Open while the place fades in, cut where
//           the line of sight meets the reveal, the hole's sides _Edge.y metres into the wall (Zumi/Reveal draws them):
//           whole where it clears the reveal's far end, darkening toward that end's edge into the reveal's own tone,
//           so the wall around the hole is never faded or darkened. Past the key wall's corner the notches ease,
//           within _Edge.w metres along the side wall, to _Edge.z of themselves.
// The focus scrim (_SeatFwd.w): behind and around the panel, an ellipse about the seat's forward (_Scrim: half spans
// in radians, then where it starts to ease off and where it ends, as shares of them), the place is blurred, and
// darkened and desaturated as far as _ScrimLook says (ZumiPlaces: blur only), so the frames stand out against a calm
// version of it; beyond, untouched.
// What comes nearer than the panel is not drawn: it would hide the panel in the depth buffer. Front before back, both
// writing depth, so each pixel takes the nearest surface once.
Shader "Zumi/Place"
{
    Properties
    {
        _MainTex ("Texture", 2D) = "white" {}
        _Opacity ("Opacity", Range(0, 1)) = 1
        _Open ("Open", Range(0, 1)) = 1
        [Toggle] _Broken ("Broken wall", Float) = 0
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
        _SeatFwd ("Seat forward (w: scrim on)", Vector) = (0, 0, 1, 1)
        _Scrim ("Scrim half spans (radians), ease from, end", Vector) = (0.63, 0.5, 0.45, 1.3)
        _ScrimLook ("Scrim brightness, saturation, blur (texels)", Vector) = (0.42, 0.35, 5, 0)
    }
    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "Queue" = "Transparent-98" "RenderType" = "Transparent" }
        Pass
        {
            Tags { "LightMode" = "SRPDefaultUnlit" }
            Blend SrcAlpha OneMinusSrcAlpha, One OneMinusSrcAlpha
            ZWrite On
            Cull Off
            Stencil { Ref 128 ReadMask 128 Comp Equal }
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            TEXTURE2D(_MainTex);
            SAMPLER(sampler_MainTex);
            CBUFFER_START(UnityPerMaterial)
                float4 _MainTex_ST;
                float4 _MainTex_TexelSize;
                half _Opacity;
                float _Open;
                float _Broken;
                float4 _Seat, _Key, _KeyN, _KeyR, _SideL, _SideLN, _SideR, _SideRN, _CornerL, _CornerR, _SideLA, _SideRA, _Rect, _Round, _Edge;
                float4 _SeatFwd, _Scrim, _ScrimLook;
            CBUFFER_END
            #include "ZumiOpening.hlsl"
            struct A { float4 pos : POSITION; float2 uv : TEXCOORD0; float2 fit : TEXCOORD1; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; float2 fit : TEXCOORD1; float3 world : TEXCOORD2; UNITY_VERTEX_OUTPUT_STEREO };
            V vert(A i)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.world = TransformObjectToWorld(i.pos.xyz);
                o.pos = TransformWorldToHClip(o.world);
                o.uv = TRANSFORM_TEX(i.uv, _MainTex);
                o.fit = i.fit;
                return o;
            }

            // how much of the scrim a point of the place gets: 1 behind the panel, easing to 0 well beyond it
            float Scrim(float3 world)
            {
                if (_SeatFwd.w < 0.5) return 0.0;
                float3 d = normalize(world - _Seat.xyz);
                float3 f = _SeatFwd.xyz;
                float3 r = normalize(cross(float3(0, 1, 0), f));
                float2 q = float2(atan2(dot(d, r), dot(d, f)), asin(clamp(d.y, -1.0, 1.0))) / _Scrim.xy;
                return 1.0 - smoothstep(_Scrim.z, _Scrim.w, length(q));
            }

            half4 frag(V i) : SV_Target
            {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                float3 eye = GetCameraPositionWS();
                float3 ray = i.world - eye;
                clip(dot(ray, ray) - 1.15 * 1.15);

                float3 w0 = ZumiExit(eye, ray, 0.0);
                float2 p0 = ZumiFlat(w0);
                float u;
                float mask = _Opacity * (1.0 - smoothstep(-_Round.y, 0.0, ZumiOutline(p0, u)));
                float toBack = 0.0;
                UNITY_BRANCH
                if (_Broken > 0.5)
                {
                    // through the hole only where the line of sight also clears the reveal's far end
                    float m1 = ZumiBroken(ZumiFlat(ZumiExit(eye, ray, _Edge.y)), _Open, 1.0);
                    float s = max(ZumiBroken(p0, _Open, 1.0), m1);
                    mask = 1.0 - smoothstep(-1.5 * fwidth(s), 0.0, s);
                    toBack = smoothstep(-ZUMI_REVEAL_BLEND, 0.0, m1);
                }

                half3 colour = SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, i.uv).rgb;
                float calm = Scrim(i.world);
                UNITY_BRANCH
                if (calm > 0.01)
                {
                    // the blur from the texture's own mips, one read: a lower mip by log2 of the blur's width in texels,
                    // wider toward the panel's middle (eight extra reads a pixel over most of the window, on the front
                    // and the back alike, kept the GPU saturated on the headset, 2026-11-17)
                    half3 soft = SAMPLE_TEXTURE2D_BIAS(_MainTex, sampler_MainTex, i.uv, log2(1.0 + _ScrimLook.z * calm)).rgb;
                    half grey = dot(soft, half3(0.299, 0.587, 0.114));
                    half3 quiet = lerp(grey.xxx, soft, _ScrimLook.y) * _ScrimLook.x;
                    colour = lerp(colour, quiet, calm);
                }
                colour = lerp(colour, ZumiLinear(ZUMI_REVEAL_BACK), toBack * 0.85);
                // nothing where nothing shows: no depth either, so a part of the place inside the room never hides the
                // reveal or the cracks behind it
                clip(i.fit.x * mask - 0.002);
                return half4(colour, i.fit.x * mask);
            }
            ENDHLSL
        }
    }
}
