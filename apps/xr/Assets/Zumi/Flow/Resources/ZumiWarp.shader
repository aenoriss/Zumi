// Straightens a page: drawn into a render texture of the page's shape (Graphics.Blit), each pixel of the page
// (u, v) looks up the camera image at H (u, v, 1), the homography from the unit square to the four corners of the
// page as the camera saw them. No compute: one fragment shader, so it runs anywhere.
Shader "Hidden/Zumi/Warp"
{
    Properties
    {
        _MainTex ("Camera image", 2D) = "white" {}
    }
    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" }
        Pass
        {
            ZTest Always ZWrite Off Cull Off
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            TEXTURE2D(_MainTex);
            SAMPLER(sampler_MainTex);
            float4 _H0, _H1, _H2;
            struct A { float4 pos : POSITION; float2 uv : TEXCOORD0; };
            struct V { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; };
            V vert(A i)
            {
                V o;
                o.pos = TransformObjectToHClip(i.pos.xyz);
                o.uv = i.uv;
                return o;
            }
            half4 frag(V i) : SV_Target
            {
                float3 p = float3(i.uv, 1);
                float3 q = float3(dot(_H0.xyz, p), dot(_H1.xyz, p), dot(_H2.xyz, p));
                float2 uv = q.xy / q.z;
                half4 c = SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, uv);
                // outside the camera image: paper white
                if (any(uv < 0) || any(uv > 1)) c = half4(1, 1, 1, 1);
                c.a = 1;
                return c;
            }
            ENDHLSL
        }
    }
}
