// A place's prop standing in the room: the only lit thing the reader draws. Its light is the open place's
// (ZumiRoomLight sets it for all props at once): the ambient's three colours by how far the surface faces up or
// down, the key light by how far it faces the light, and a share of its own painted texture as its own light, so a
// prop never goes black. Both sides are drawn (the models are not reliably closed). Opaque; while it fades with its
// place it is thinned by a 4x4 dither, which keeps it sorted and keeps the passthrough behind it whole.
Shader "Zumi/Prop"
{
    Properties
    {
        _MainTex ("Texture", 2D) = "white" {}
        _Opacity ("Opacity", Range(0, 1)) = 1
    }
    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "Queue" = "AlphaTest" "RenderType" = "TransparentCutout" }
        Pass
        {
            Tags { "LightMode" = "SRPDefaultUnlit" }
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
            CBUFFER_END
            // the open place's light, the same for every prop
            half4 _ZumiSky, _ZumiHorizon, _ZumiGround;
            // toward the light (world), and its colour times its strength
            float4 _ZumiKeyDir;
            half4 _ZumiKey;
            // x: the share of the texture shown as the prop's own light; y: the ambient's gain
            half4 _ZumiPropLight;
            struct A { float4 pos : POSITION; float3 normal : NORMAL; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; half3 normal : TEXCOORD1; UNITY_VERTEX_OUTPUT_STEREO };
            V vert(A i)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = TransformObjectToHClip(i.pos.xyz);
                o.uv = TRANSFORM_TEX(i.uv, _MainTex);
                o.normal = TransformObjectToWorldNormal(i.normal);
                return o;
            }
            half4 frag(V i, half facing : VFACE) : SV_Target
            {
                static const half bayer[16] = { 0.5, 8.5, 2.5, 10.5, 12.5, 4.5, 14.5, 6.5, 3.5, 11.5, 1.5, 9.5, 15.5, 7.5, 13.5, 5.5 };
                uint2 pixel = uint2(i.pos.xy) & 3;
                clip(_Opacity - bayer[pixel.y * 4 + pixel.x] / 16.0);
                half3 n = normalize(i.normal) * (facing < 0 ? -1.0 : 1.0);
                half3 ambient = n.y > 0 ? lerp(_ZumiHorizon.rgb, _ZumiSky.rgb, n.y) : lerp(_ZumiHorizon.rgb, _ZumiGround.rgb, -n.y);
                half3 light = _ZumiPropLight.x + _ZumiPropLight.y * ambient + _ZumiKey.rgb * saturate(dot(n, _ZumiKeyDir.xyz));
                return half4(SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, i.uv).rgb * light, 1);
            }
            ENDHLSL
        }
    }
}
