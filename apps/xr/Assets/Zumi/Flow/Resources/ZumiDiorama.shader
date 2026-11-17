// The making-of's 3D world: a place's mesh or a prop, unlit (a prop shaded a little by _Shade from its normals), opaque,
// writing depth. With _Masked on, a pixel shows only where the line from the eye to it crosses the window's plane
// inside its rounded rectangle (_Window: world to the window's frame, its +z into the scene; _Half: half width, half
// height, corner radius, metres), so the place is seen through that opening from any eye. It fades by a 4x4 dither
// (_Opacity), which keeps it sorted.
Shader "Zumi/Diorama"
{
    Properties
    {
        _MainTex ("Texture", 2D) = "white" {}
        _Opacity ("Opacity", Range(0, 1)) = 1
        [Toggle] _Masked ("Masked by the window", Float) = 1
        _Half ("Window half width, half height, corner radius", Vector) = (0.25, 0.175, 0.05, 0)
        _Shade ("Shade from normals", Range(0, 1)) = 0
    }
    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "Queue" = "Transparent+20" "RenderType" = "TransparentCutout" }
        Pass
        {
            Tags { "LightMode" = "SRPDefaultUnlit" }
            ZWrite On
            Cull Off
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
                float _Masked;
                float4 _Half;
                half _Shade;
                float4x4 _Window;
            CBUFFER_END
            struct A { float4 pos : POSITION; float3 normal : NORMAL; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; float3 world : TEXCOORD1; half3 normal : TEXCOORD2; UNITY_VERTEX_OUTPUT_STEREO };
            V vert(A i)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.world = TransformObjectToWorld(i.pos.xyz);
                o.pos = TransformWorldToHClip(o.world);
                o.uv = TRANSFORM_TEX(i.uv, _MainTex);
                o.normal = TransformObjectToWorldNormal(i.normal);
                return o;
            }
            half4 frag(V i, half facing : VFACE) : SV_Target
            {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                static const half bayer[16] = { 0.5, 8.5, 2.5, 10.5, 12.5, 4.5, 14.5, 6.5, 3.5, 11.5, 1.5, 9.5, 15.5, 7.5, 13.5, 5.5 };
                uint2 pixel = uint2(i.pos.xy) & 3;
                clip(_Opacity - bayer[pixel.y * 4 + pixel.x] / 16.0);
                UNITY_BRANCH
                if (_Masked > 0.5)
                {
                    float3 e = mul(_Window, float4(GetCameraPositionWS(), 1.0)).xyz;
                    float3 p = mul(_Window, float4(i.world, 1.0)).xyz;
                    float dz = p.z - e.z;
                    float t = abs(dz) > 1e-5 ? -e.z / dz : 0.0;
                    float2 hit = e.xy + (p.xy - e.xy) * t;
                    float2 q = abs(hit) - (_Half.xy - _Half.z);
                    float d = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - _Half.z;
                    clip(-d);
                    // nothing between the eye and the window's plane: the opening is the nearest thing
                    clip(p.z + 0.002);
                }
                half3 colour = SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, i.uv).rgb;
                half3 n = normalize(i.normal + 1e-5) * (facing < 0 ? -1.0 : 1.0);
                half light = lerp(1.0, 0.62 + 0.5 * saturate(dot(n, normalize(half3(0.35, 0.8, -0.45)))), _Shade);
                return half4(colour * light, 1);
            }
            ENDHLSL
        }
    }
}
