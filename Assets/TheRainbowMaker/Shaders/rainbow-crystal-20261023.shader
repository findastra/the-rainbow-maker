// Cut-crystal look for the Rainbow Maker's crystals (built-in pipeline, VRChat-safe, no grab pass).
// The view ray goes in through a facet and out through a mirrored back facet three times (red, green and blue at
// slightly different IORs), and each colour reads the reflection probe in its own direction, so facets split into
// colour like real lead crystal. Facets that bend the sun toward the eye show its fire.
Shader "TheRainbowMaker/Crystal"
{
    Properties
    {
        _Tint ("Tint", Color) = (0.96, 0.98, 1, 1)
        _IOR ("Index of refraction", Range(1.0, 2.0)) = 1.55
        _Dispersion ("Dispersion (IOR spread R to B)", Range(0.0, 0.3)) = 0.12
        _BodyAlpha ("Body opacity", Range(0.0, 1.0)) = 0.4
        _Cut ("Facet steepness", Range(1.0, 5.0)) = 2.5
        _Sparkle ("Sun sparkle", Range(0.0, 30.0)) = 10
        _SparkleSharpness ("Sparkle sharpness", Range(4.0, 400.0)) = 40
    }
    SubShader
    {
        Tags { "Queue" = "Transparent" "RenderType" = "Transparent" "IgnoreProjector" = "True" }
        Pass
        {
            Tags { "LightMode" = "ForwardBase" }
            Blend SrcAlpha OneMinusSrcAlpha
            ZWrite Off
            Cull Back

            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"
            #include "Lighting.cginc"

            fixed4 _Tint;
            float _IOR, _Dispersion, _BodyAlpha, _Cut, _Sparkle, _SparkleSharpness;

            struct v2f
            {
                float4 pos : SV_POSITION;
                float3 worldPos : TEXCOORD0;
                float3 worldNormal : TEXCOORD1;
            };

            v2f vert (appdata_base v)
            {
                v2f o;
                o.pos = UnityObjectToClipPos(v.vertex);
                o.worldPos = mul(unity_ObjectToWorld, v.vertex).xyz;
                o.worldNormal = UnityObjectToWorldNormal(v.normal);
                return o;
            }

            float3 Probe (float3 dir)
            {
                return DecodeHDR(UNITY_SAMPLE_TEXCUBE(unity_SpecCube0, dir), unity_SpecCube0_HDR);
            }

            float3 Hue (float h)
            {
                return saturate(abs(frac(h + float3(0, 2.0 / 3.0, 1.0 / 3.0)) * 6 - 3) - 1);
            }

            // In through the facet, out through a back facet tilted the other way (the facet normal mirrored about the
            // view ray, as on a cut stone); too steep to leave means total internal reflection.
            float3 Through (float3 ray, float3 n, float3 nBack, float ior)
            {
                float3 inside = refract(ray, n, 1.0 / ior);
                float3 outside = refract(inside, -nBack, ior);
                return dot(outside, outside) > 0.001 ? outside : reflect(inside, nBack);
            }

            fixed4 frag (v2f i) : SV_Target
            {
                float3 n = normalize(i.worldNormal);
                float3 v = normalize(_WorldSpaceCameraPos - i.worldPos);
                float3 ray = -v;
                // The mesh's star facets are shallow; light inside a real cut crystal bounces between much steeper
                // ones. Steepen each facet's tilt away from the view (_Cut) so neighbouring facets catch very
                // different parts of the room and sky, which is what makes cut glass look like a patchwork.
                float3 tilt = n - v * dot(n, v);
                n = normalize(v * dot(n, v) + tilt * _Cut);
                float3 nBack = normalize(reflect(-n, v));

                // one path per colour: red bends least, blue most, so facet edges split into colour
                float3 rR = Through(ray, n, nBack, _IOR - _Dispersion);
                float3 rG = Through(ray, n, nBack, _IOR);
                float3 rB = Through(ray, n, nBack, _IOR + _Dispersion);
                float3 through = float3(Probe(rR).r, Probe(rG).g, Probe(rB).b) * _Tint.rgb;

                // off the surface
                float3 mirror = Probe(reflect(ray, n));
                float fresnel = 0.05 + 0.95 * pow(1 - saturate(dot(n, v)), 5);

                // a facet that mirrors the sun to the eye glints white; one that bends the sun to the eye shows
                // its fire, each colour where its own path lines up with the sun
                float3 l = normalize(_WorldSpaceLightPos0.xyz);
                float glint = pow(saturate(dot(reflect(-l, n), v)), _SparkleSharpness);
                float3 fire = float3(pow(saturate(dot(rR, l)), _SparkleSharpness),
                                     pow(saturate(dot(rG, l)), _SparkleSharpness),
                                     pow(saturate(dot(rB, l)), _SparkleSharpness));
                float3 sparkle = (glint + fire + fire.g * 0.5 * Hue(dot(n, float3(1.7, 2.3, 3.1)))) * _LightColor0.rgb * _Sparkle;

                float3 col = lerp(through, mirror, fresnel) + sparkle;
                float alpha = saturate(_BodyAlpha + fresnel + dot(sparkle, 0.33));
                return fixed4(col, alpha);
            }
            ENDCG
        }
    }
    Fallback "Transparent/Diffuse"
}
