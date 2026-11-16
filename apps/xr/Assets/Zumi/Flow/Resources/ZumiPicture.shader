// A picture on a card, unlit: a scanned or coloured page, a mask overlay, the book. _MainTex blends toward _SecondTex
// by _Mix (the pencil page turning into its coloured page), times _Color; alpha blended, both sides drawn.
Shader "Zumi/Picture"
{
    Properties
    {
        _MainTex ("Picture", 2D) = "white" {}
        _SecondTex ("Second picture", 2D) = "white" {}
        _Mix ("Mix", Range(0, 1)) = 0
        _Color ("Tint", Color) = (1, 1, 1, 1)
        [Toggle] _ZWrite ("Depth write", Float) = 0
        _Dissolve ("Dissolve", Range(0, 1)) = 0
        _Graphite ("Graphite (pencil on cream) where not yet swept", Range(0, 1)) = 0
        _SweepPlane ("Sweep: world axis xyz, the line's place along it w; graphite beyond it", Vector) = (1, 0, 0, -1000)
    }
    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "Queue" = "Transparent" "RenderType" = "Transparent" }
        Pass
        {
            Tags { "LightMode" = "SRPDefaultUnlit" }
            Blend SrcAlpha OneMinusSrcAlpha
            ZWrite [_ZWrite]
            Cull Off
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            TEXTURE2D(_MainTex);
            SAMPLER(sampler_MainTex);
            TEXTURE2D(_SecondTex);
            SAMPLER(sampler_SecondTex);
            CBUFFER_START(UnityPerMaterial)
                float4 _MainTex_ST;
                half _Mix;
                half4 _Color;
                half _Dissolve;
                half _Graphite;
                float4 _SweepPlane;
            CBUFFER_END
            struct A { float4 pos : POSITION; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; float3 world : TEXCOORD1; UNITY_VERTEX_OUTPUT_STEREO };
            V vert(A i)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = TransformObjectToHClip(i.pos.xyz);
                o.uv = TRANSFORM_TEX(i.uv, _MainTex);
                o.world = TransformObjectToWorld(i.pos.xyz);
                return o;
            }
            // value noise over world space (so the whole book dissolves as one, across its parts)
            float Hash(float3 p) { return frac(sin(dot(p, float3(127.1, 311.7, 74.7))) * 43758.5453); }
            float Noise(float3 p)
            {
                float3 i = floor(p), f = frac(p);
                f = f * f * (3.0 - 2.0 * f);
                return lerp(lerp(lerp(Hash(i), Hash(i + float3(1, 0, 0)), f.x), lerp(Hash(i + float3(0, 1, 0)), Hash(i + float3(1, 1, 0)), f.x), f.y),
                            lerp(lerp(Hash(i + float3(0, 0, 1)), Hash(i + float3(1, 0, 1)), f.x), lerp(Hash(i + float3(0, 1, 1)), Hash(i + float3(1, 1, 1)), f.x), f.y), f.z);
            }
            half3 Zumi(float k)
            {
                static const half3 c[7] = {
                    half3(0.780, 0.659, 1.000), half3(0.612, 0.796, 1.000), half3(1.000, 0.659, 0.812),
                    half3(0.620, 0.898, 0.784), half3(1.000, 0.910, 0.604), half3(1.000, 0.765, 0.627),
                    half3(0.780, 0.659, 1.000) };
                int n = (int)floor(k);
                return lerp(c[n], c[n + 1], smoothstep(0.0, 1.0, frac(k)));
            }
            half4 frag(V i) : SV_Target
            {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                half4 a = SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, i.uv);
                half4 b = SAMPLE_TEXTURE2D(_SecondTex, sampler_SecondTex, i.uv);
                half4 c = lerp(a, b, _Mix) * _Color;
                if (_Graphite > 0.0)
                {
                    // pencil: the picture's lightness, a little more contrast, from ink to cream paper; the part the
                    // sweep has passed is in colour, with a thin line of the Zumi hues at the sweep
                    float d = dot(i.world, _SweepPlane.xyz) - _SweepPlane.w;
                    half l = saturate((dot(c.rgb, half3(0.299, 0.587, 0.114)) - 0.5) * 1.3 + 0.5);
                    half3 pencil = lerp(half3(0.165, 0.129, 0.106), half3(0.961, 0.929, 0.863), l);
                    c.rgb = lerp(c.rgb, pencil, _Graphite * step(0.0, d));
                    half edge = (1.0 - smoothstep(0.0, 0.006, abs(d))) * _Graphite;
                    c.rgb = lerp(c.rgb, Zumi(frac(i.world.y * 4.0 + _Time.y * 0.3) * 6.0) * 1.1, edge);
                }
                if (_Dissolve > 0.0)
                {
                    float n = Noise(i.world * 70.0) * 0.65 + Noise(i.world * 160.0) * 0.35;
                    float cut = _Dissolve * 1.2 - 0.05;
                    clip(n - cut);
                    // a wide band ahead of the edge takes the Zumi hues, strongest right at the edge
                    float edge = 1.0 - smoothstep(0.0, 0.16, n - cut);
                    c.rgb = lerp(c.rgb, Zumi(frac(n * 2.0 + i.world.y * 6.0 + i.world.x * 3.0) * 6.0) * 1.05, saturate(edge * 1.3));
                }
                return c;
            }
            ENDHLSL
        }
    }
}
