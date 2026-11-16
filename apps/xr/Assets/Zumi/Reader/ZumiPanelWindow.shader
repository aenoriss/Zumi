// A frame's window (export_zumi.box_cards "window: frame <n>"): draws nothing, marks the frame's shape (the
// texture's alpha) in the stencil's low four bits so that frame's layers (Zumi/Card) show only through it and the
// gutters stay empty. Before the layers (queue 2990), never writes depth. The other bits are the place's (Zumi/Portal).
Shader "Zumi/PanelWindow"
{
    Properties
    {
        _MainTex ("Frame shape (alpha)", 2D) = "white" {}
        _Stencil ("Stencil ref", Range(1, 15)) = 1
    }
    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "Queue" = "Transparent-10" "RenderType" = "Transparent" }
        Pass
        {
            Tags { "LightMode" = "SRPDefaultUnlit" }
            ColorMask 0
            ZWrite Off
            Cull Off
            Stencil { Ref [_Stencil] ReadMask 15 WriteMask 15 Comp Always Pass Replace }
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            TEXTURE2D(_MainTex);
            SAMPLER(sampler_MainTex);
            CBUFFER_START(UnityPerMaterial)
                float4 _MainTex_ST;
            CBUFFER_END
            struct A { float4 pos : POSITION; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; UNITY_VERTEX_OUTPUT_STEREO };
            V vert(A i)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = TransformObjectToHClip(i.pos.xyz);
                o.uv = TRANSFORM_TEX(i.uv, _MainTex);
                return o;
            }
            half4 frag(V i) : SV_Target
            {
                clip(SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, i.uv).a - 0.5);
                return 0;
            }
            ENDHLSL
        }
    }
}
