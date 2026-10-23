// Projector shader for the rainbow streaks the crystals throw on the room: adds a spectrum texture (red to violet)
// wherever a Projector points, nothing behind it or outside its frame.
Shader "TheRainbowMaker/RainbowStreak"
{
    Properties
    {
        _ShadowTex ("Rainbow streak", 2D) = "black" {}
        _Strength ("Strength", Range(0, 4)) = 1.4
    }
    SubShader
    {
        Tags { "Queue" = "Transparent" }
        Pass
        {
            ZWrite Off
            ColorMask RGB
            Blend One One
            Offset -1, -1

            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"

            sampler2D _ShadowTex;
            float _Strength;
            float4x4 unity_Projector;

            struct v2f
            {
                float4 pos : SV_POSITION;
                float4 uv : TEXCOORD0;
            };

            v2f vert (appdata_base v)
            {
                v2f o;
                o.pos = UnityObjectToClipPos(v.vertex);
                o.uv = mul(unity_Projector, v.vertex);
                return o;
            }

            fixed4 frag (v2f i) : SV_Target
            {
                if (i.uv.w <= 0) discard;                  // behind the projector
                float2 t = i.uv.xy / i.uv.w;
                if (any(t < 0) || any(t > 1)) discard;     // outside the streak's frame
                return fixed4(tex2D(_ShadowTex, t).rgb * _Strength, 1);
            }
            ENDCG
        }
    }
}
