local data = {}

local ae_compDurations = {0, 1.53333330154419}
data.ae_compDurations = ae_compDurations

local ae_effectType = 'transition'
data.ae_effectType = ae_effectType

local ae_transitionInputIndex = {
    {'LumiLayer_105-matte-blend', 'InputTex', 1},
    {'LumiLayer_105-matte-blend', 'baseTex', 0},
}
data.ae_transitionInputIndex = ae_transitionInputIndex

local ae_durations = {
    ['LumiAnimSeqLoadAndCrop_6601-effect0'] = {
        ['nodeDuration'] = {{0, 1.53333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.53333333333333}, },
            ['seqTex_1_1'] = {{0, 1.53333333333333}, },
        },
    },
    ['LumiExtract_104-effect0'] = {
        ['nodeDuration'] = {{0, 1.53333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.53333333333333}, },
        },
    },
    ['LumiGaussianBlur_104-effect1'] = {
        ['nodeDuration'] = {{0, 1.53333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.53333333333333}, },
        },
    },
    ['LumiLayer_105-matte-blend'] = {
        ['nodeDuration'] = {{0, 1.53333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.26666666666667, 1.53333333333333}, },
            ['baseTex'] = {{0, 1.36666666666667}, },
            ['maskTex'] = {{0, 1.53333333333333}, },
        },
    },
    ['LumiDisplacementMap_103-effect0'] = {
        ['nodeDuration'] = {{0, 1.53333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.53333333333333}, },
            ['horizontalImage'] = {{0, 1.53333333333333}, },
            ['verticalImage'] = {{0, 1.53333333333333}, },
        },
    },
    ['LumiLayer_103-blend'] = {
        ['nodeDuration'] = {{0, 1.53333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.53333333333333}, },
            ['baseTex'] = {{0, 1.53333333333333}, },
        },
    },
    ['LumiLayer_102-trs-blend'] = {
        ['nodeDuration'] = {{0, 1.53333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.53333333333333}, },
            ['baseTex'] = {{0, 1.53333333333333}, },
        },
    },
    ['LumiDeepGlow_101-effect0'] = {
        ['nodeDuration'] = {{0, 1.53333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.53333333333333}, },
        },
    },
    ['LumiBrightness_101-effect1'] = {
        ['nodeDuration'] = {{0, 1.53333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.53333333333333}, },
        },
    },
    ['LumiLayer_101-blend'] = {
        ['nodeDuration'] = {{0, 1.53333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.53333333333333}, },
            ['baseTex'] = {{0, 1.53333333333333}, },
        },
    },
}
data.ae_durations = ae_durations

local ae_attribute = {
    ['LumiAnimSeqLoadAndCrop_6601-effect0'] = {
        ['specify_1_1'] = true,
        ['animSeqType_1_1'] = 0,
        ['cropType_1_1'] = 1,
        ['edgeType_1_1'] = 1,
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
        ['playMode_9_16'] = 0,
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
        ['playMode_16_9'] = 0,
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
        ['playMode_5.8'] = 0,
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
        ['playMode_2_1'] = 0,
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
        ['playMode_3_4'] = 0,
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
        ['playMode_4_3'] = 0,
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
        ['playMode_1.85_1'] = 0,
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
        ['playMode_2.35_1'] = 0,
        ['globalRotation'] = 0,
        ['globalScale'] = 1,
        ['globalOpacity'] = 1,
        ['globalSpeed'] = 1,
        ['lite_mode'] = true,
        ['AEDesignSize'] = Amaz.Vector2f(960, 960),
    },
    ['LumiExtract_104-effect0'] = {
        ['blackField'] = 30.9090909090909,
        ['blackSoft'] = 0,
        ['whiteField'] = 255,
        ['whiteSoft'] = 0,
        ['reverse'] = false,
        ['AEDesignSize'] = Amaz.Vector2f(960, 960),
    },
    ['LumiGaussianBlur_104-effect1'] = {
        ['blurIntensity'] = 60,
        ['quality'] = 0.28951592824836,
        ['spaceDither'] = 0,
        ['horizontalStrength'] = 1,
        ['verticalStrength'] = 1,
        ['blurDirection'] = 0,
        ['borderType'] = 3,
        ['blurAlpha'] = true,
        ['inverseGammaCorrection'] = false,
        ['AEDesignSize'] = Amaz.Vector2f(960, 960),
    },
    ['LumiLayer_105-matte-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = true,
        ['hasTransform'] = false,
        ['layerType'] = 'Precomp',
        ['matteMode'] = 0,
        ['blendMode'] = 0,
    },
    ['LumiDisplacementMap_103-effect0'] = {
        ['horizontalType'] = 0,
        ['horizontalIntensity'] = 0,
        ['verticalType'] = 1,
        ['verticalIntensity'] = 0.03157977795113,
        ['edgeType'] = 1,
        ['AEDesignSize'] = Amaz.Vector2f(960, 960),
    },
    ['LumiLayer_103-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 0,
    },
    ['LumiLayer_102-trs-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = true,
        ['layerType'] = 'Precomp',
        ['anchorPoint'] = Amaz.Vector3f(480, 480, 0),
        ['position'] = Amaz.Vector3f(480, 480, 0),
        ['scale'] = Amaz.Vector3f(100, 100, 100),
        ['orientation'] = Amaz.Vector3f(0, 0, 0),
        ['xRotation'] = 0,
        ['yRotation'] = 0,
        ['rotation'] = 0,
        ['opacity'] = 47.4673312777267,
        ['active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(960, 960),
        ['layerSize'] = Amaz.Vector2f(960, 960),
        ['mirrorEdge'] = false,
        ['blendMode'] = 2,
    },
    ['LumiDeepGlow_101-effect0'] = {
        ['radius'] = 288,
        ['exposure'] = 0.54393809440079,
        ['threshold'] = 0.64,
        ['thresholdSmooth'] = 0.5,
        ['greyScale'] = 0,
        ['blendMode'] = 1,
        ['view'] = 1,
        ['ratio'] = 1,
        ['rotate'] = 0,
        ['ca'] = false,
        ['redOffset'] = 0.0025,
        ['greenOffset'] = 0,
        ['blueOffset'] = -0.0025,
        ['tint'] = false,
        ['tintMode'] = 1,
        ['tintColor'] = Amaz.Color(1, 0, 0, 1),
        ['tintMix'] = 1,
        ['sourceOpacity'] = 1,
        ['unmult'] = true,
        ['gammaCorrect'] = true,
        ['gammaValue'] = 2,
        ['glowIter'] = 8,
        ['stepsMult'] = 1.5,
        ['downSample'] = 0.80000001192093,
        ['quality'] = 0.80421091180099,
        ['AEDesignSize'] = Amaz.Vector2f(960, 960),
    },
    ['LumiBrightness_101-effect1'] = {
        ['brightnessIntensity'] = 0.29534771330532,
        ['AEDesignSize'] = Amaz.Vector2f(960, 960),
    },
    ['LumiLayer_101-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 0,
    },
}
data.ae_attribute = ae_attribute

local ae_keyframes = {
    ['LumiAnimSeqLoadAndCrop_6601-effect0#seqTime#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0, 1.53333333333333, }, 
		{{0, }, {1.53333333333333, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiExtract_104-effect0#blackField#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.266667, 1.366667, }, 
		{{255, }, {0, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiDisplacementMap_103-effect0#verticalIntensity#number'] =
{
	{
		{0.529687511, 0, 0.751579089, 0.770315704, }, 
		{0, 0.5, }, 
		{{0, }, {0.13, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.300571435, 0.028247165, 0.760599748, 0.028090484, }, 
		{0.5, 0.933333, }, 
		{{0.13, }, {0.13, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.188399183, 0.219342863, 0.502563431, 1, }, 
		{0.933333, 1.5, }, 
		{{0.13, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiLayer_102-trs-blend#opacity#number'] =
{
	{
		{0.328486345, 0, 0.531611651, 1, }, 
		{0, 0.5, }, 
		{{0, }, {100, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.166666667, 0, 0.833333333, 0, }, 
		{0.5, 0.933333, }, 
		{{100, }, {100, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.446446046, 0, 0.593281351, 1, }, 
		{0.933333, 1.5, }, 
		{{100, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiDeepGlow_101-effect0#exposure#number'] =
{
	{
		{0.001, 0, 0.32735532, 1, }, 
		{0, 0.666667, }, 
		{{0, }, {0.8, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.33333333, 0, 0.66666667, 0, }, 
		{0.666667, 0.8, }, 
		{{0.8, }, {0.8, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.681904933, 0, 0.999, 1, }, 
		{0.8, 1.5, }, 
		{{0.8, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiBrightness_101-effect1#brightnessIntensity#number'] =
{
	{
		{0.19, 0, 0.45, 1, }, 
		{0, 0.5, }, 
		{{0, }, {0.55, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.5, 0.933333, }, 
		{{0.55, }, {0.55, }, }, 
		{6417, }, 
		{1, }, 
	}, 
	{
		{0.45, 0, 0.69, 1, }, 
		{0.933333, 1.5, }, 
		{{0.55, }, {0, }, }, 
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
