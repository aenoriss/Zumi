// A crisp line in the Zumi hues: the colour turns round the uv square's middle (a conic gradient, turning by
// _Turn), full strength; for the carousel's rim round its middle book and the position dots' current pill.
// _Color's alpha fades it.
Shader "Zumi/Rim"
{
    Properties
    {
        _Color ("Tint", Color) = (1, 1, 1, 1)
        _Turn ("Turn (radians)", Float) = 0
    }
    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "Queue" = "Transparent" "RenderType" = "Transparent" }
        Pass
        {
            Tags { "LightMode" = "SRPDefaultUnlit" }
            Blend SrcAlpha OneMinusSrcAlpha
            ZWrite Off
            Cull Off
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            CBUFFER_START(UnityPerMaterial)
                half4 _Color;
                float _Turn;
            CBUFFER_END
            struct A { float4 pos : POSITION; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; UNITY_VERTEX_OUTPUT_STEREO };
            V vert(A i)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = TransformObjectToHClip(i.pos.xyz);
                o.uv = i.uv;
                return o;
            }
            half3 Hue(float k)
            {
                static const half3 c[7] = {
                    half3(0.780, 0.659, 1.000), half3(0.612, 0.796, 1.000), half3(1.000, 0.659, 0.812),
                    half3(0.620, 0.898, 0.784), half3(1.000, 0.910, 0.604), half3(1.000, 0.765, 0.627),
                    half3(0.780, 0.659, 1.000) };
                int i = (int)floor(k);
                return lerp(c[i], c[i + 1], smoothstep(0.0, 1.0, frac(k)));
            }
            half4 frag(V i) : SV_Target
            {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                float2 p = i.uv * 2.0 - 1.0;
                float a = atan2(p.y, p.x) + _Turn;
                return half4(Hue(frac(a / 6.2831853) * 6.0), 1.0) * _Color;
            }
            ENDHLSL
        }
    }
}
