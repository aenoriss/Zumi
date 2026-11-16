// A place's mesh (front or back): its painted view, unlit, seen only through the room's openings (stencil bit 7,
// Zumi/Portal). Each vertex carries, in its second texture coordinates, how much of it shows by its direction from
// the seat (the vignette over the view's measured span) and how far beyond the room's edge it lies in metres: what
// is still inside the room is not drawn. Its third: the degrees from the seat's eye level up to the wall's top and
// down to the floor line where it lands; each pixel is cut there (the mesh's origin is the seat's eye), so a large
// triangle crossing the wall's top leaves a clean edge, not a smear. Without a scanned room the opening is one window, and the place also fades
// toward the window's edges. Where the mesh has a gap nothing is drawn, so the wall shows, not black. Front before
// back, both writing depth, so each pixel takes the nearest surface once.
Shader "Zumi/Place"
{
    Properties
    {
        _MainTex ("Texture", 2D) = "white" {}
        _Opacity ("Opacity", Range(0, 1)) = 1
        _Window ("Fade toward the window's edges", Float) = 0
        _EdgeDegrees ("Soft edge at the wall's top and the floor line, degrees", Float) = 1.5
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
                return half4(SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, i.uv).rgb, alpha);
            }
            ENDHLSL
        }
    }
}
