// Draws no colour: marks the stencil or the depth buffer where a place may show. One shader, three uses, set by the
// reader (ZumiPlaces) on three materials:
//   opening   the window's quads (on the key wall, and its folds onto side walls), bit 7, where nothing nearer was
//             drawn (queue 2899)
//   far       the same rectangle again, inside bit 7: depth back to the far plane, so the place's meshes sort among
//             themselves and nothing drawn behind the wall hides them (2900); the place's backdrop follows (2901)
//   clear     the same once the place and its rim are drawn (2906): the place's depth never hides the panel's layers
// The stencil's eight bits: 0 to 3 a panel's frames (Zumi/PanelWindow, Zumi/Card), 7 the place's opening; 4 to 6
// are free. Each use reads and writes only its own bits.
Shader "Zumi/Portal"
{
    Properties
    {
        _StencilRef ("Stencil ref", Range(0, 255)) = 128
        _StencilRead ("Stencil read mask", Range(0, 255)) = 64
        _StencilWrite ("Stencil write mask", Range(0, 255)) = 128
        [Enum(UnityEngine.Rendering.CompareFunction)] _StencilComp ("Stencil comparison", Float) = 3
        [Enum(UnityEngine.Rendering.StencilOp)] _StencilPass ("Stencil pass", Float) = 2
        [Enum(UnityEngine.Rendering.CompareFunction)] _ZTest ("Depth test", Float) = 4
        [Toggle] _ZWrite ("Depth write", Float) = 0
        [Enum(UnityEngine.Rendering.CullMode)] _Cull ("Cull", Float) = 0
        [Toggle] _Far ("At the far plane", Float) = 0
    }
    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "Queue" = "Transparent-100" "RenderType" = "Transparent" }
        Pass
        {
            Tags { "LightMode" = "SRPDefaultUnlit" }
            ColorMask 0
            ZWrite [_ZWrite]
            ZTest [_ZTest]
            Cull [_Cull]
            Stencil { Ref [_StencilRef] ReadMask [_StencilRead] WriteMask [_StencilWrite] Comp [_StencilComp] Pass [_StencilPass] }
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            CBUFFER_START(UnityPerMaterial)
                float _Far;
            CBUFFER_END
            struct A { float4 pos : POSITION; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 pos : SV_POSITION; UNITY_VERTEX_OUTPUT_STEREO };
            V vert(A i)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = TransformObjectToHClip(i.pos.xyz);
                #if UNITY_REVERSED_Z
                    o.pos.z = lerp(o.pos.z, o.pos.w * 1e-6, _Far);
                #else
                    o.pos.z = lerp(o.pos.z, o.pos.w * (1.0 - 1e-6), _Far);
                #endif
                return o;
            }
            half4 frag(V i) : SV_Target { return 0; }
            ENDHLSL
        }
    }
}
