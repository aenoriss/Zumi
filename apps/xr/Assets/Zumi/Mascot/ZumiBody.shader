// Zumi's body, unlit: either the rainbow vertex colours (all readers) or one player hue as a vertical gradient,
// light at the tip, base in the middle, deep at the bottom. A second pass draws the plum outline as an inverted hull.
Shader "Zumi/Body"
{
    Properties
    {
        [Toggle] _Rainbow ("Rainbow (vertex colours)", Float) = 1
        _Light ("Light (tip)", Color) = (1, 1, 1, 1)
        _Base ("Base", Color) = (1, 1, 1, 1)
        _Deep ("Deep (bottom)", Color) = (1, 1, 1, 1)
        _YMin ("Height min (object space)", Float) = -1.47
        _YMax ("Height max (object space)", Float) = 1.45
        _OutlineColor ("Outline", Color) = (0.357, 0.09, 0.282, 1)
        _OutlineWidth ("Outline width (object space)", Float) = 0.022
    }
    SubShader
    {
        Tags { "RenderType" = "Opaque" "RenderPipeline" = "UniversalPipeline" "Queue" = "Geometry" }

        HLSLINCLUDE
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
        CBUFFER_START(UnityPerMaterial)
            float _Rainbow;
            half4 _Light, _Base, _Deep, _OutlineColor;
            float _YMin, _YMax, _OutlineWidth;
        CBUFFER_END
        ENDHLSL

        Pass
        {
            Name "Body"
            Tags { "LightMode" = "UniversalForward" }
            Cull Back
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            struct A { float4 pos : POSITION; half4 col : COLOR; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 pos : SV_POSITION; half4 col : COLOR; UNITY_VERTEX_OUTPUT_STEREO };
            V vert(A i)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = TransformObjectToHClip(i.pos.xyz);
                float t = saturate((i.pos.y - _YMin) / (_YMax - _YMin));
                half4 hue = t > 0.5 ? lerp(_Base, _Light, (t - 0.5) * 2) : lerp(_Deep, _Base, t * 2);
                o.col = _Rainbow > 0.5 ? i.col : hue;
                return o;
            }
            half4 frag(V i) : SV_Target { return half4(i.col.rgb, 1); }
            ENDHLSL
        }

        Pass
        {
            Name "Outline"
            Tags { "LightMode" = "SRPDefaultUnlit" }
            Cull Front
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            struct A { float4 pos : POSITION; float3 n : NORMAL; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 pos : SV_POSITION; UNITY_VERTEX_OUTPUT_STEREO };
            V vert(A i)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = TransformObjectToHClip(i.pos.xyz + normalize(i.n) * _OutlineWidth);
                return o;
            }
            half4 frag(V i) : SV_Target { return _OutlineColor; }
            ENDHLSL
        }
    }
}
