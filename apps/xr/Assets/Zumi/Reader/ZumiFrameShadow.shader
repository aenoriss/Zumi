// A frame's soft shadow: a feathered dark halo a few centimetres round the frame's shape, so the frames read as a
// layer floating in front of what is behind them. Drawn on the frame window's quad grown by _Grow (its uv mapped back
// to the frame's texture), after the windows and before the layers (queue 2995), never writing depth, black at an
// alpha: the shape's alpha (the window texture) blurred over _Radius of its uv, never inside the frame itself.
Shader "Zumi/FrameShadow"
{
    Properties
    {
        _MainTex ("Frame shape (alpha)", 2D) = "white" {}
        _Grow ("Quad over the frame's size (x, y)", Vector) = (1.1, 1.1, 0, 0)
        _Radius ("Feather, in the frame's uv (x, y)", Vector) = (0.04, 0.04, 0, 0)
        _Strength ("Darkness", Range(0, 1)) = 0.5
    }
    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "Queue" = "Transparent-5" "RenderType" = "Transparent" }
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
            TEXTURE2D(_MainTex);
            SAMPLER(sampler_MainTex);
            CBUFFER_START(UnityPerMaterial)
                float4 _MainTex_ST;
                float4 _Grow;
                float4 _Radius;
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
                o.uv = (i.uv - 0.5) * _Grow.xy + 0.5;
                return o;
            }
            // the shape's alpha, nothing outside the frame's texture
            half Shape(float2 uv)
            {
                float2 inside = step(0.0, uv) * step(uv, 1.0);
                return SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, saturate(uv)).a * inside.x * inside.y;
            }
            half4 frag(V i) : SV_Target
            {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                half own = Shape(i.uv);
                UNITY_BRANCH
                if (own > 0.99) return 0;
                float2 r = _Radius.xy;
                half near = 0, far = 0;
                // two rings of eight taps: half the feather and all of it
                [unroll] for (int k = 0; k < 8; k++)
                {
                    float a = k * 0.785398;
                    float2 d = float2(cos(a), sin(a)) * r;
                    near += Shape(i.uv + d * 0.5);
                    far += Shape(i.uv + d);
                }
                half shadow = (own + near / 8.0 * 2.0 + far / 8.0) / 4.0;
                return half4(0, 0, 0, _Strength * shadow * (1.0 - own));
            }
            ENDHLSL
        }
    }
}
