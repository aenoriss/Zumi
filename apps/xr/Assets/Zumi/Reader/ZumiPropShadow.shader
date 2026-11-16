// The soft contact shadow under a prop: a dark round patch on the surface it stands on, densest under its middle
// (the set preview's blob: full to 8 % of the radius, under half at 60 %, nothing at the rim). Over passthrough it
// darkens the real surface; it is drawn after the place and before the panel.
Shader "Zumi/PropShadow"
{
    Properties
    {
        _Strength ("Strength", Range(0, 1)) = 0.5
    }
    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "Queue" = "Transparent-50" "RenderType" = "Transparent" }
        Pass
        {
            Tags { "LightMode" = "SRPDefaultUnlit" }
            Blend SrcAlpha OneMinusSrcAlpha, One OneMinusSrcAlpha
            ZWrite Off
            Cull Off
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            CBUFFER_START(UnityPerMaterial)
                half _Strength;
            CBUFFER_END
            struct A { float4 pos : POSITION; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; UNITY_VERTEX_OUTPUT_STEREO };
            V vert(A i)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = TransformObjectToHClip(i.pos.xyz);
                o.uv = i.uv * 2.0 - 1.0;
                return o;
            }
            half4 frag(V i) : SV_Target
            {
                half r = length(i.uv);
                half dark = r < 0.6 ? lerp(1.0, 0.45, saturate((r - 0.08) / 0.52)) : lerp(0.45, 0.0, saturate((r - 0.6) / 0.4));
                return half4(0, 0, 0, _Strength * dark);
            }
            ENDHLSL
        }
    }
}
