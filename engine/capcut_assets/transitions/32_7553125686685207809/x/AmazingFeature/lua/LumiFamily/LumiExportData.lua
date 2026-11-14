local data = {}

local ae_compDurations = {0, 1.96666666666667}
data.ae_compDurations = ae_compDurations

local ae_effectType = 'transition'
data.ae_effectType = ae_effectType

local ae_transitionInputIndex = {
    {'LumiLayer_1105-matte', 'InputTex', 0},
    {'LumiLayer_1104-blend', 'InputTex', 0},
    {'LumiLayer_2180-matte-blend', 'InputTex', 1},
    {'LumiLayer_2185-blend', 'InputTex', 1},
}
data.ae_transitionInputIndex = ae_transitionInputIndex

local ae_durations = {
    ['LumiAnimSeqLoadAndCrop_1053-effect0'] = {
        ['nodeDuration'] = {{0.4, 1.66666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.4, 1.66666666666667}, },
            ['seqTex_1_1'] = {{0.4, 1.66666666666667}, },
        },
    },
    ['LumiLayer_1105-matte'] = {
        ['nodeDuration'] = {{0.4, 0.83333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.4, 0.83333333333333}, },
            ['maskTex'] = {{0.4, 1.66666666666667}, },
        },
    },
    ['LumiLayer_1104-blend'] = {
        ['nodeDuration'] = {{0, 0.83333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.4}, },
            ['baseTex'] = {{0.4, 0.83333333333333}, },
        },
    },
    ['LumiLayer_2180-matte-blend'] = {
        ['nodeDuration'] = {{0, 1.66666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.83333333333333, 1.66666666666667}, },
            ['baseTex'] = {{0, 0.83333333333333}, },
            ['maskTex'] = {{0.4, 1.66666666666667}, },
        },
    },
    ['LumiLayer_2185-blend'] = {
        ['nodeDuration'] = {{0, 2}, },
        ['texDuration'] = {
            ['InputTex'] = {{1.66666666666667, 2}, },
            ['baseTex'] = {{0, 1.66666666666667}, },
        },
    },
    ['LumiOpticsCompensation_1103-effect0'] = {
        ['nodeDuration'] = {{0.13333333333333, 1.83333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 2}, },
        },
    },
    ['LumiLayer_1103-blend'] = {
        ['nodeDuration'] = {{0, 2}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.13333333333333, 1.83333333333333}, },
            ['baseTex'] = {{0, 2}, },
        },
    },
    ['LumiTritone_1102-effect0'] = {
        ['nodeDuration'] = {{0.13333333333333, 1.83333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 2}, },
        },
    },
    ['LumiLayer_1102-blend'] = {
        ['nodeDuration'] = {{0, 2}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.13333333333333, 1.83333333333333}, },
            ['baseTex'] = {{0, 2}, },
        },
    },
    ['LumiSShake_1101-effect0'] = {
        ['nodeDuration'] = {{0.13333333333333, 1.83333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 2}, },
        },
    },
    ['LumiLayer_1101-blend'] = {
        ['nodeDuration'] = {{0, 2}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.13333333333333, 1.83333333333333}, },
            ['baseTex'] = {{0, 2}, },
        },
    },
    ['LumiChromaticAberration_1083-effect0'] = {
        ['nodeDuration'] = {{0.13333333333333, 1.83333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 2}, },
        },
    },
    ['LumiLayer_1083-blend'] = {
        ['nodeDuration'] = {{0, 2}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.13333333333333, 1.83333333333333}, },
            ['baseTex'] = {{0, 2}, },
        },
    },
    ['LumiGaussianBlur_1056-effect0'] = {
        ['nodeDuration'] = {{0.13333333333333, 1.83333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 2}, },
        },
    },
    ['LumiLayer_1056-blend'] = {
        ['nodeDuration'] = {{0, 2}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.13333333333333, 1.83333333333333}, },
            ['baseTex'] = {{0, 2}, },
        },
    },
}
data.ae_durations = ae_durations

local ae_attribute = {
    ['LumiAnimSeqLoadAndCrop_1053-effect0'] = {
        ['specify_1_1'] = true,
        ['animSeqType_1_1'] = 0,
        ['cropType_1_1'] = 1,
        ['edgeType_1_1'] = 3,
        ['enableVideoAlphaBlend_1_1'] = false,
        ['pivot_1_1'] = Amaz.Vector2f(0.5, 0.5),
        ['ae_pre_pivot_1_1'] = Amaz.Vector2f(0.5, 0.5),
        ['position_1_1'] = Amaz.Vector2f(0.5, 0.5),
        ['ae_pre_position_1_1'] = Amaz.Vector2f(0.5, 0.5),
        ['rotation_1_1'] = 0,
        ['scale_1_1'] = 1,
        ['opacity_1_1'] = 1,
        ['speed_1_1'] = 1,
        ['playMode_1_1'] = 0,
        ['specify_9_16'] = false,
        ['animSeqType_9_16'] = 2,
        ['cropType_9_16'] = 1,
        ['edgeType_9_16'] = 0,
        ['enableVideoAlphaBlend_9_16'] = false,
        ['pivot_9_16'] = Amaz.Vector2f(0.5, 0.5),
        ['ae_pre_pivot_9_16'] = Amaz.Vector2f(0.5, 0.5),
        ['position_9_16'] = Amaz.Vector2f(0.5, 0.5),
        ['ae_pre_position_9_16'] = Amaz.Vector2f(0.5, 0.5),
        ['rotation_9_16'] = 0,
        ['scale_9_16'] = 1,
        ['opacity_9_16'] = 1,
        ['speed_9_16'] = 1,
        ['playMode_9_16'] = 1,
        ['specify_16_9'] = false,
        ['animSeqType_16_9'] = 2,
        ['cropType_16_9'] = 1,
        ['edgeType_16_9'] = 0,
        ['enableVideoAlphaBlend_16_9'] = false,
        ['pivot_16_9'] = Amaz.Vector2f(0.5, 0.5),
        ['ae_pre_pivot_16_9'] = Amaz.Vector2f(0.5, 0.5),
        ['position_16_9'] = Amaz.Vector2f(0.5, 0.5),
        ['ae_pre_position_16_9'] = Amaz.Vector2f(0.5, 0.5),
        ['rotation_16_9'] = 0,
        ['scale_16_9'] = 1,
        ['opacity_16_9'] = 1,
        ['speed_16_9'] = 1,
        ['playMode_16_9'] = 1,
        ['specify_5.8'] = false,
        ['animSeqType_5.8'] = 2,
        ['cropType_5.8'] = 1,
        ['edgeType_5.8'] = 0,
        ['enableVideoAlphaBlend_5.8'] = false,
        ['pivot_5.8'] = Amaz.Vector2f(0.5, 0.5),
        ['ae_pre_pivot_5.8'] = Amaz.Vector2f(0.5, 0.5),
        ['position_5.8'] = Amaz.Vector2f(0.5, 0.5),
        ['ae_pre_position_5.8'] = Amaz.Vector2f(0.5, 0.5),
        ['rotation_5.8'] = 0,
        ['scale_5.8'] = 1,
        ['opacity_5.8'] = 1,
        ['speed_5.8'] = 1,
        ['playMode_5.8'] = 1,
        ['specify_2_1'] = false,
        ['animSeqType_2_1'] = 2,
        ['cropType_2_1'] = 1,
        ['edgeType_2_1'] = 0,
        ['enableVideoAlphaBlend_2_1'] = false,
        ['pivot_2_1'] = Amaz.Vector2f(0.5, 0.5),
        ['ae_pre_pivot_2_1'] = Amaz.Vector2f(0.5, 0.5),
        ['position_2_1'] = Amaz.Vector2f(0.5, 0.5),
        ['ae_pre_position_2_1'] = Amaz.Vector2f(0.5, 0.5),
        ['rotation_2_1'] = 0,
        ['scale_2_1'] = 1,
        ['opacity_2_1'] = 1,
        ['speed_2_1'] = 1,
        ['playMode_2_1'] = 1,
        ['specify_3_4'] = false,
        ['animSeqType_3_4'] = 2,
        ['cropType_3_4'] = 1,
        ['edgeType_3_4'] = 0,
        ['enableVideoAlphaBlend_3_4'] = false,
        ['pivot_3_4'] = Amaz.Vector2f(0.5, 0.5),
        ['ae_pre_pivot_3_4'] = Amaz.Vector2f(0.5, 0.5),
        ['position_3_4'] = Amaz.Vector2f(0.5, 0.5),
        ['ae_pre_position_3_4'] = Amaz.Vector2f(0.5, 0.5),
        ['rotation_3_4'] = 0,
        ['scale_3_4'] = 1,
        ['opacity_3_4'] = 1,
        ['speed_3_4'] = 1,
        ['playMode_3_4'] = 1,
        ['specify_4_3'] = false,
        ['animSeqType_4_3'] = 2,
        ['cropType_4_3'] = 1,
        ['edgeType_4_3'] = 0,
        ['enableVideoAlphaBlend_4_3'] = false,
        ['pivot_4_3'] = Amaz.Vector2f(0.5, 0.5),
        ['ae_pre_pivot_4_3'] = Amaz.Vector2f(0.5, 0.5),
        ['position_4_3'] = Amaz.Vector2f(0.5, 0.5),
        ['ae_pre_position_4_3'] = Amaz.Vector2f(0.5, 0.5),
        ['rotation_4_3'] = 0,
        ['scale_4_3'] = 1,
        ['opacity_4_3'] = 1,
        ['speed_4_3'] = 1,
        ['playMode_4_3'] = 1,
        ['specify_1.85_1'] = false,
        ['animSeqType_1.85_1'] = 2,
        ['cropType_1.85_1'] = 1,
        ['edgeType_1.85_1'] = 0,
        ['enableVideoAlphaBlend_1.85_1'] = false,
        ['pivot_1.85_1'] = Amaz.Vector2f(0.5, 0.5),
        ['ae_pre_pivot_1.85_1'] = Amaz.Vector2f(0.5, 0.5),
        ['position_1.85_1'] = Amaz.Vector2f(0.5, 0.5),
        ['ae_pre_position_1.85_1'] = Amaz.Vector2f(0.5, 0.5),
        ['rotation_1.85_1'] = 0,
        ['scale_1.85_1'] = 1,
        ['opacity_1.85_1'] = 1,
        ['speed_1.85_1'] = 1,
        ['playMode_1.85_1'] = 1,
        ['specify_2.35_1'] = false,
        ['animSeqType_2.35_1'] = 2,
        ['cropType_2.35_1'] = 1,
        ['edgeType_2.35_1'] = 0,
        ['enableVideoAlphaBlend_2.35_1'] = false,
        ['pivot_2.35_1'] = Amaz.Vector2f(0.5, 0.5),
        ['ae_pre_pivot_2.35_1'] = Amaz.Vector2f(0.5, 0.5),
        ['position_2.35_1'] = Amaz.Vector2f(0.5, 0.5),
        ['ae_pre_position_2.35_1'] = Amaz.Vector2f(0.5, 0.5),
        ['rotation_2.35_1'] = 0,
        ['scale_2.35_1'] = 1,
        ['opacity_2.35_1'] = 1,
        ['speed_2.35_1'] = 1,
        ['playMode_2.35_1'] = 1,
        ['globalRotation'] = 0,
        ['globalScale'] = 1,
        ['globalOpacity'] = 1,
        ['globalSpeed'] = 1,
        ['lite_mode'] = true,
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1080),
    },
    ['LumiLayer_1105-matte'] = {
        ['hasBlend'] = false,
        ['hasMatte'] = true,
        ['hasTransform'] = false,
        ['layerType'] = 'Precomp',
        ['matteMode'] = 1,
    },
    ['LumiLayer_1104-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Precomp',
        ['blendMode'] = 0,
    },
    ['LumiLayer_2180-matte-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = true,
        ['hasTransform'] = false,
        ['layerType'] = 'Precomp',
        ['matteMode'] = 1,
        ['blendMode'] = 0,
    },
    ['LumiLayer_2185-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Precomp',
        ['blendMode'] = 0,
    },
    ['LumiOpticsCompensation_1103-effect0'] = {
        ['fov'] = 34.4317086638912,
        ['inverseLensDistortion'] = true,
        ['fovOrientation'] = 0,
        ['center'] = Amaz.Vector2f(0.5, 0.5),
        ['antiAliasing'] = false,
        ['fillBorders'] = false,
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1080),
    },
    ['LumiLayer_1103-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 0,
    },
    ['LumiTritone_1102-effect0'] = {
        ['highlightColor'] = Amaz.Color(1, 1, 1, 1),
        ['middleColor'] = Amaz.Color(0.54666662216187, 0.54666662216187, 0.54666662216187, 1),
        ['shadowColor'] = Amaz.Color(0, 0, 0, 1),
        ['oriAlpha'] = 0.31663954665864,
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1080),
    },
    ['LumiLayer_1102-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 0,
    },
    ['LumiSShake_1101-effect0'] = {
        ['ampRatio'] = 0.30383009663543,
        ['frqRatio'] = 3.6,
        ['phase0'] = 0,
        ['scale0'] = 1,
        ['blurEnabled'] = false,
        ['blurIntensity'] = 1,
        ['blurQuality'] = 0,
        ['seed'] = 0,
        ['xFill'] = 2,
        ['yFill'] = 2,
        ['xAmpR'] = 192,
        ['xFrqR'] = 1,
        ['xAmp'] = 0,
        ['xFrq'] = 0.5,
        ['xPhase'] = 0,
        ['yAmpR'] = 192,
        ['yFrqR'] = 1,
        ['yAmp'] = 0,
        ['yFrq'] = 0.5,
        ['yPhase'] = 0,
        ['zAmpR'] = 0,
        ['zFrqR'] = 1,
        ['zAmp'] = 0,
        ['zFrq'] = 0.5,
        ['zPhase'] = 0,
        ['wAmpR'] = 0,
        ['wFrqR'] = 1,
        ['wAmp'] = 0,
        ['wFrq'] = 0.5,
        ['wPhase'] = 0,
        ['rAmpRatio'] = 1,
        ['gAmpRatio'] = 1,
        ['bAmpRatio'] = 1,
        ['rPhase'] = 0,
        ['gPhase'] = 0,
        ['bPhase'] = 0,
        ['rgbRnd'] = 0,
        ['rgbFrq'] = 2,
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1080),
    },
    ['LumiLayer_1101-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 0,
    },
    ['LumiChromaticAberration_1083-effect0'] = {
        ['offsetX'] = 0.23641092452494,
        ['offsetY'] = 0.23641092452494,
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1080),
    },
    ['LumiLayer_1083-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 0,
    },
    ['LumiGaussianBlur_1056-effect0'] = {
        ['blurIntensity'] = 62.9203194530517,
        ['quality'] = 0.3,
        ['spaceDither'] = 0.2,
        ['horizontalStrength'] = 1,
        ['verticalStrength'] = 1,
        ['blurDirection'] = 0,
        ['borderType'] = 3,
        ['blurAlpha'] = true,
        ['inverseGammaCorrection'] = true,
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1080),
    },
    ['LumiLayer_1056-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 0,
    },
}
data.ae_attribute = ae_attribute

local ae_keyframes = {
    ['LumiAnimSeqLoadAndCrop_1053-effect0#seqTime#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.4, 1.66666666666667, }, 
		{{0, }, {1.26666666666667, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiOpticsCompensation_1103-effect0#fov#number'] =
{
	{
		{0.465, 0.204089095, 0.745, 0.437751012, }, 
		{0.133333, 0.833333, }, 
		{{0, }, {88, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.132, 0.523305335, 0.192, 0.920490376, }, 
		{0.833333, 1.8, }, 
		{{88, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiTritone_1102-effect0#oriAlpha#number'] =
{
	{
		{0.166666667, 0, 0.833333333, 1, }, 
		{0.133333, 0.833333, }, 
		{{1, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.185, 0.040433749, 0.196, 0.724425714, }, 
		{0.833333, 1.766667, }, 
		{{0, }, {1, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiSShake_1101-effect0#ampRatio#number'] =
{
	{
		{0.15797532, 0, 0.630398781, 0.677960589, }, 
		{0.133333, 0.833333, }, 
		{{0, }, {0.46, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.219, 0.403342632, 0.645, 0.937939781, }, 
		{0.833333, 1.766667, }, 
		{{0.46, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiChromaticAberration_1083-effect0#offsetX#number'] =
{
	{
		{0.166666667, 0, 0.833333333, 1, }, 
		{0.133333, 0.833333, }, 
		{{0, }, {0.6, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.108, 0.477420066, 0.21, 0.950245098, }, 
		{0.833333, 1.8, }, 
		{{0.6, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiChromaticAberration_1083-effect0#offsetY#number'] =
{
	{
		{0.166666667, 0, 0.833333333, 1, }, 
		{0.133333, 0.833333, }, 
		{{0, }, {0.6, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.108, 0.477420066, 0.21, 0.950245098, }, 
		{0.833333, 1.8, }, 
		{{0.6, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiGaussianBlur_1056-effect0#blurIntensity#number'] =
{
	{
		{0.639, 0.087258137, 0.805, 0.690884756, }, 
		{0.133333, 0.833333, }, 
		{{0, }, {200, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.08, 0.513524785, 0.152, 1, }, 
		{0.833333, 1.8, }, 
		{{200, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
}
data.ae_keyframes = ae_keyframes

local ae_reverseKeyframes = false
data.ae_reverseKeyframes = ae_reverseKeyframes

local ae_sliderInfos = {
}
data.ae_sliderInfos = ae_sliderInfos

local ae_fadeinInfos = {
    time = 0,
    infos = {
    }
}
data.ae_fadeinInfos = ae_fadeinInfos

local ae_fadeoutInfos = {
    time = 0,
    infos = {
    }
}
data.ae_fadeoutInfos = ae_fadeoutInfos

local ae_animationInfos = {
    animationMode = 0,
    loopStart = 0,
    speedInfo = {1, 0, 1, },
}
data.ae_animationInfos = ae_animationInfos

return data
