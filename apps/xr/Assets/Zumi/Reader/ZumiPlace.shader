// A place's mesh (front or back): its painted view, unlit, seen only through the room's openings (stencil bit 7,
// Zumi/Portal). Each vertex carries, in its second texture coordinates, how much of it shows by its direction from
// the seat (the vignette over the view's measured span) and how far beyond the room's edge it lies in metres: what
// is still inside the room is not drawn. Its third: the degrees from the seat's eye level up to the wall's top and
// down to the floor line where it lands; each pixel is cut there (the mesh's origin is the seat's eye), so a large
// triangle crossing the wall's top leaves a clean edge, not a smear. Without a scanned room the opening is one window, and the place also fades
// toward the window's edges. Where the mesh has a gap nothing is drawn, so the wall shows, not black. Front before
// back, both writing depth, so each pixel takes the nearest surface once.
// The focus scrim (_SeatFwd.w): behind and around the panel, an ellipse about the seat's forward (_Scrim: half spans
// in radians, then where it starts to ease off and where it ends, as shares of them), the place is blurred over
// _ScrimLook.z texels (and darkened and desaturated as far as _ScrimLook.xy say: ZumiPlaces leaves both at 1), so
// the frames stand out against a calm version of it; beyond, untouched.
Shader "Zumi/Place"
{
    Properties
    {
        _MainTex ("Texture", 2D) = "white" {}
        _Opacity ("Opacity", Range(0, 1)) = 1
        _Window ("Fade toward the window's edges", Float) = 0
        _EdgeDegrees ("Soft edge at the wall's top and the floor line, degrees", Float) = 1.5
        _Seat ("Seat eye", Vector) = (0, 0, 0, 0)
        _SeatFwd ("Seat forward (w: scrim on)", Vector) = (0, 0, 1, 1)
        _Scrim ("Scrim half spans (radians), ease from, end", Vector) = (0.63, 0.5, 0.6, 1.5)
        _ScrimLook ("Scrim brightness, saturation, blur (texels)", Vector) = (1, 1, 2.5, 0)
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
                float4 _Seat, _SeatFwd, _Scrim, _ScrimLook;
                half _Opacity;
                half _Window;
                float _EdgeDegrees;
                float4 _WindowCentre;
                float4 _WindowRight;
                float4 _WindowUp;
                // half width, half height, the width of the soft edge, all in metres
                float4 _WindowSize;
            CBUFFER_END
            struct A { float4 pos : POSITION; float2 uv : TEXCOORD0; float2 fit : TEXCOORD1; float2 edges : TEXCOORD2; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; float2 fit : TEXCOORD1; float3 world : TEXCOORD2; float3 local : TEXCOORD3; float2 edges : TEXCOORD4; UNITY_VERTEX_OUTPUT_STEREO };
            V vert(A i)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.world = TransformObjectToWorld(i.pos.xyz);
                o.pos = TransformWorldToHClip(o.world);
                o.uv = TRANSFORM_TEX(i.uv, _MainTex);
                o.fit = i.fit;
                o.local = i.pos.xyz;
                o.edges = i.edges;
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
                clip(i.fit.y);
                // up and down, per pixel: from the floor line to the top of the wall, as seen from the seat (the
                // mesh's origin), with a short soft edge
                float elevation = degrees(asin(clamp(normalize(i.local).y, -1.0, 1.0)));
                float2 inside = float2(i.edges.x - elevation, i.edges.y + elevation) / _EdgeDegrees;
                half alpha = _Opacity * i.fit.x * smoothstep(0.0, 1.0, saturate(min(inside.x, inside.y)));
                if (_Window > 0.5)
                {
                    // where the line of sight to this point crosses the window
                    float3 eye = GetCameraPositionWS();
                    float3 ray = i.world - eye;
                    float3 normal = cross(_WindowRight.xyz, _WindowUp.xyz);
                    float3 at = eye + ray * (dot(_WindowCentre.xyz - eye, normal) / dot(ray, normal)) - _WindowCentre.xyz;
                    float2 inside = (_WindowSize.xy - abs(float2(dot(at, _WindowRight.xyz), dot(at, _WindowUp.xyz)))) / _WindowSize.z;
                    alpha *= smoothstep(0.0, 1.0, saturate(min(inside.x, inside.y)));
                }
                half3 colour = SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, i.uv).rgb;
                float calm = Scrim(i.world);
                UNITY_BRANCH
                if (calm > 0.01)
                {
                    // a ring of eight taps about the pixel, wider toward the panel's middle
                    float2 d = _MainTex_TexelSize.xy * _ScrimLook.z * calm;
                    half3 ring = SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, i.uv + float2(d.x, 0)).rgb + SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, i.uv - float2(d.x, 0)).rgb
                               + SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, i.uv + float2(0, d.y)).rgb + SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, i.uv - float2(0, d.y)).rgb
                               + SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, i.uv + d * 0.7).rgb + SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, i.uv - d * 0.7).rgb
                               + SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, i.uv + float2(d.x, -d.y) * 0.7).rgb + SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, i.uv + float2(-d.x, d.y) * 0.7).rgb;
                    half3 soft = (colour + ring) / 9.0;
                    half grey = dot(soft, half3(0.299, 0.587, 0.114));
                    half3 quiet = lerp(grey.xxx, soft, _ScrimLook.y) * _ScrimLook.x;
                    colour = lerp(colour, quiet, calm);
                }
                return half4(colour, alpha);
            }
            ENDHLSL
        }
    }
}
