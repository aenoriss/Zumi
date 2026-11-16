// The Zumi glow: a soft round gradient of the mascot's six hues (lilac, sky, pink, mint, butter, peach) arranged
// around the centre and turning by _Turn, whitening a little toward the middle, falling off to nothing at the edge.
// Drawn on a unit quad (uv 0..1); _Color's alpha fades it.
Shader "Zumi/Glow"
{
    Properties
    {
        _Color ("Tint", Color) = (1, 1, 1, 1)
        _Turn ("Turn (radians)", Float) = 0
        _Solid ("Vertex colour instead of the wheel", Range(0, 1)) = 0
        _Core ("White at the middle", Range(0, 1)) = 0.35
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
                half _Solid;
                half _Core;
            CBUFFER_END
            // vertex colour: a particle's own fade (a mesh without colours reads white)
            struct A { float4 pos : POSITION; float2 uv : TEXCOORD0; half4 colour : COLOR; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; half4 colour : COLOR; UNITY_VERTEX_OUTPUT_STEREO };
            V vert(A i)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = TransformObjectToHClip(i.pos.xyz);
                o.uv = i.uv;
                o.colour = i.colour;
                return o;
            }
            half3 Hue(float k)
            {
                // the six hues around the circle, k in 0..6, blended smoothly between neighbours
                static const half3 c[7] = {
                    half3(0.780, 0.659, 1.000), half3(0.612, 0.796, 1.000), half3(1.000, 0.659, 0.812),
                    half3(0.620, 0.898, 0.784), half3(1.000, 0.910, 0.604), half3(1.000, 0.765, 0.627),
                    half3(0.780, 0.659, 1.000) };
                int i = (int)floor(k);
                float f = smoothstep(0.0, 1.0, frac(k));
                return lerp(c[i], c[i + 1], f);
            }
            half4 frag(V i) : SV_Target
            {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                float2 p = i.uv * 2.0 - 1.0;
                float r = length(p);
                float a = atan2(p.y, p.x) + _Turn;
                float k = frac(a / 6.2831853) * 6.0;
                half3 col = lerp(Hue(k), half3(1.0, 0.98, 0.95), (1.0 - smoothstep(0.0, 0.4, r)) * _Core);
                half alpha = 1.0 - smoothstep(0.25, 1.0, r);
                alpha *= alpha;
                // _Solid: one hue per particle, its vertex colour, instead of the wheel
                col = lerp(col, i.colour.rgb, _Solid);
                return half4(col, alpha) * _Color * half4(1, 1, 1, i.colour.a);
            }
            ENDHLSL
        }
    }
}
