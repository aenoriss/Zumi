// The place's edge on the walls as a comic frame's ink line (ZumiPlaceOutline): drawn on a band of mesh round the
// boundary whose first texture coordinates are the place on the walls laid flat (s along the room's outline, y up), so
// the line runs on unbroken round a corner. Square corners, as a comic frame has; its width and its sideways wobble
// change slowly along each side, as a hand-drawn line does, and calm down to nothing at the corners. Nothing else: no
// halo, no shadow. Drawn after the depth over the openings is cleared, so the place's depth never hides it.
//   _Rect  the line's middle: s from, s to, bottom, top (metres)   _Line  width, wobble (metres)
//   _Ink   the colour as shown                                     _Opacity  the place's fade
Shader "Zumi/Ink"
{
    Properties
    {
        _Opacity ("Opacity", Range(0, 1)) = 1
        _Ink ("Ink", Color) = (0.08, 0.075, 0.07, 1)
        _Rect ("Line on the walls laid flat (s from, s to, bottom, top)", Vector) = (0, 4, 0, 2.5)
        _Line ("Width, wobble (metres)", Vector) = (0.014, 0.0035, 0, 0)
    }
    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "Queue" = "Transparent-93" "RenderType" = "Transparent" }
        Pass
        {
            Tags { "LightMode" = "SRPDefaultUnlit" }
            Blend SrcAlpha OneMinusSrcAlpha, One OneMinusSrcAlpha
            ZWrite Off
            ZTest LEqual
            Cull Off
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            CBUFFER_START(UnityPerMaterial)
                float _Opacity;
                float4 _Ink, _Rect, _Line;
            CBUFFER_END
            struct A { float4 pos : POSITION; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 pos : SV_POSITION; float2 flat : TEXCOORD0; UNITY_VERTEX_OUTPUT_STEREO };
            V vert(A i)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = TransformObjectToHClip(i.pos.xyz);
                o.flat = i.uv;
                return o;
            }

            float Hash(float n) { return frac(sin(n * 91.3458) * 47453.5453); }

            // smooth noise along a line, 0 to 1
            float Noise(float x)
            {
                float i = floor(x), f = frac(x);
                f = f * f * (3.0 - 2.0 * f);
                return lerp(Hash(i), Hash(i + 1.0), f);
            }

            half4 frag(V i) : SV_Target
            {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                float2 c = float2(_Rect.x + _Rect.y, _Rect.z + _Rect.w) * 0.5;
                float2 h = float2(_Rect.y - _Rect.x, _Rect.w - _Rect.z) * 0.5;
                float2 q = abs(i.flat - c) - h;
                // which side is nearest: an upright side runs along y, a level one along s; each its own seed
                bool upright = q.x > q.y;
                float along = upright ? i.flat.y : i.flat.x;
                float seed = upright ? (i.flat.x > c.x ? 17.0 : 5.0) : (i.flat.y > c.y ? 29.0 : 11.0);
                // metres from the nearer corner along that side: the wobble calms down within three widths of it
                float fromCorner = upright ? h.y - abs(i.flat.y - c.y) : h.x - abs(i.flat.x - c.x);
                float calm = smoothstep(0.0, 3.0 * _Line.x, fromCorner);
                float wobble = _Line.y * calm * ((Noise(along * 2.1 + seed) - 0.5) * 1.4 + (Noise(along * 7.3 + seed * 3.0) - 0.5) * 0.6);
                float width = _Line.x * (0.85 + 0.3 * Noise(along * 1.3 + seed * 7.0));
                // square corners: the box distance, 0 on the line's middle
                float d = abs(max(q.x, q.y) - wobble) - width * 0.5;
                float aa = max(fwidth(d), 1e-5);
                float ink = 1.0 - smoothstep(-aa, aa, d);
                clip(ink - 0.002);
                return half4(_Ink.rgb, ink * 0.96 * saturate(_Opacity * 1.5));
            }
            ENDHLSL
        }
    }
}
