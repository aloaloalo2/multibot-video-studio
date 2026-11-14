local data = {}

local ae_compDurations = {0, 1.96666666666667}
data.ae_compDurations = ae_compDurations

local ae_effectType = 'transition'
data.ae_effectType = ae_effectType

local ae_transitionInputIndex = {
    {'LumiDust_84-effect0', 'InputTex', 1},
    {'LumiLayer_84-blend', 'baseTex', 1},
    {'LumiDust_66-effect0', 'InputTex', 0},
    {'LumiLayer_66-blend', 'baseTex', 0},
}
data.ae_transitionInputIndex = ae_transitionInputIndex

local ae_durations = {
    ['LumiDust_84-effect0'] = {
        ['nodeDuration'] = {{0, 5}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 5}, },
        },
    },
    ['LumiLayer_84-blend'] = {
        ['nodeDuration'] = {{0, 5}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 5}, },
            ['baseTex'] = {{0, 5}, },
        },
    },
    ['LumiDust_66-effect0'] = {
        ['nodeDuration'] = {{0, 5}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 5}, },
        },
    },
    ['LumiOpticsCompensation_66-effect1'] = {
        ['nodeDuration'] = {{0, 5}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 5}, },
        },
    },
    ['LumiLayer_66-blend'] = {
        ['nodeDuration'] = {{0, 5}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 5}, },
            ['baseTex'] = {{0, 5}, },
        },
    },
    ['LumiLayer_77-blend'] = {
        ['nodeDuration'] = {{0, 5}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 5}, },
            ['baseTex'] = {{0, 5}, },
        },
    },
    ['LumiDeepGlow_98-effect0'] = {
        ['nodeDuration'] = {{0, 5}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 5}, },
        },
    },
    ['LumiLayer_98-blend'] = {
        ['nodeDuration'] = {{0, 5}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 5}, },
            ['baseTex'] = {{0, 5}, },
        },
    },
}
data.ae_durations = ae_durations

local ae_attribute = {
    ['LumiDust_84-effect0'] = {
        ['progress'] = 0,
        ['distorIns'] = 32,
        ['dustNum'] = 0.69999998807907,
        ['dustSize'] = 1.4,
        ['brightness'] = 0,
        ['contrast'] = -0.91,
        ['quantity'] = 1,
        ['complexity'] = 8,
        ['evolution'] = 0,
        ['cycle'] = 100,
        ['offset_x'] = 0,
        ['offset_y'] = 0,
        ['maskType'] = 0,
        ['mask_noise_brightness'] = 0.01,
        ['mask_noise_contrast'] = -0.07,
        ['mask_noise_quantity'] = 1,
        ['mask_noise_complexity'] = 8,
        ['mask_noise_evolution'] = 342,
        ['mask_noise_cycle'] = 100,
        ['mask_noise_offset_x'] = 0,
        ['mask_noise_offset_y'] = 0,
        ['mask_line_rot'] = 0,
        ['maskFeather'] = 0.30000001192093,
        ['startRotX'] = 0,
        ['startRotY'] = 360,
        ['startRotZ'] = 0,
        ['startMoveX'] = 0,
        ['startMoveY'] = 0,
        ['startMoveZ'] = 0,
        ['startSize'] = 1,
        ['endRotX'] = 0,
        ['endRotY'] = 0,
        ['endRotZ'] = 0,
        ['endMoveX'] = 0,
        ['endMoveY'] = 0,
        ['endMoveZ'] = 0,
        ['endSize'] = 1,
        ['AEDesignSize'] = Amaz.Vector2f(1920, 1920),
    },
    ['LumiLayer_84-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 0,
    },
    ['LumiDust_66-effect0'] = {
        ['progress'] = 74.4999956701947,
        ['distorIns'] = 40,
        ['dustNum'] = 0.69999998807907,
        ['dustSize'] = 0.7,
        ['brightness'] = 0,
        ['contrast'] = -0.91,
        ['quantity'] = 1,
        ['complexity'] = 8,
        ['evolution'] = 0,
        ['cycle'] = 100,
        ['offset_x'] = 0,
        ['offset_y'] = 0,
        ['maskType'] = 0,
        ['mask_noise_brightness'] = 0.01,
        ['mask_noise_contrast'] = -0.07,
        ['mask_noise_quantity'] = 1,
        ['mask_noise_complexity'] = 8,
        ['mask_noise_evolution'] = 342,
        ['mask_noise_cycle'] = 100,
        ['mask_noise_offset_x'] = 0,
        ['mask_noise_offset_y'] = 0,
        ['mask_line_rot'] = 0,
        ['maskFeather'] = 0.30000001192093,
        ['startRotX'] = 0,
        ['startRotY'] = 360,
        ['startRotZ'] = 0,
        ['startMoveX'] = 0,
        ['startMoveY'] = 0,
        ['startMoveZ'] = 0,
        ['startSize'] = 0.9,
        ['endRotX'] = 0,
        ['endRotY'] = 0,
        ['endRotZ'] = 0,
        ['endMoveX'] = 0,
        ['endMoveY'] = 0,
        ['endMoveZ'] = 0,
        ['endSize'] = 1,
        ['AEDesignSize'] = Amaz.Vector2f(1920, 1920),
    },
    ['LumiOpticsCompensation_66-effect1'] = {
        ['fov'] = 93,
        ['inverseLensDistortion'] = true,
        ['fovOrientation'] = 0,
        ['center'] = Amaz.Vector2f(0.5, 0.5),
        ['antiAliasing'] = true,
        ['fillBorders'] = false,
        ['AEDesignSize'] = Amaz.Vector2f(1920, 1920),
    },
    ['LumiLayer_66-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 0,
    },
    ['LumiLayer_77-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Precomp',
        ['blendMode'] = 0,
    },
    ['LumiDeepGlow_98-effect0'] = {
        ['radius'] = 100,
        ['exposure'] = 0.29298987040771,
        ['threshold'] = 0,
        ['thresholdSmooth'] = 0,
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
        ['quality'] = 0.1,
        ['AEDesignSize'] = Amaz.Vector2f(1920, 1920),
    },
    ['LumiLayer_98-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 0,
    },
}
data.ae_attribute = ae_attribute

local ae_keyframes = {
    ['LumiDust_84-effect0#progress#number'] =
{
	{
		{0.166666667, 0, 0.833333333, 0.999999987, }, 
		{0, 0.280697, }, 
		{{100, }, {70, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.989898942, -8e-9, 0.833333333, 1, }, 
		{0.280697, 1.333333, }, 
		{{70, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiDust_84-effect0#startRotY#number'] =
{
	{
		{0.33333333, 0, 0.250000013, 1.000000127, }, 
		{0.252637, 1.07041, }, 
		{{0, }, {360, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiDust_84-effect0#startSize#number'] =
{
	{
		{0.840943713, 5e-8, 0.66666667, 1, }, 
		{0.505273, 0.912305, }, 
		{{0, }, {1, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiDust_66-effect0#progress#number'] =
{
	{
		{0.290404046, -3.5e-8, 0, 1.000000145, }, 
		{0, 0.4, }, 
		{{0, }, {49, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{1, -2.26e-7, 0.833333333, 1, }, 
		{0.4, 2, }, 
		{{49, }, {100, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiDust_66-effect0#distorIns#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.844434, 1.555566, }, 
		{{32, }, {40, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiDust_66-effect0#dustSize#number'] =
{
	{
		{0.33333333, 0, 0.66666667, 1, }, 
		{0.844434, 1.555566, }, 
		{{1.4, }, {0.7, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiDust_66-effect0#mask_noise_evolution#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.033333, 1.1, }, 
		{{0, }, {342, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiDust_66-effect0#startRotY#number'] =
{
	{
		{1, 4.2e-8, 0.66666667, 1, }, 
		{0.033333, 1.266667, }, 
		{{0, }, {360, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiDust_66-effect0#startSize#number'] =
{
	{
		{0.960038964, 1.7e-8, 0.66666667, 1, }, 
		{0, 1.266667, }, 
		{{1, }, {0.9, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiOpticsCompensation_66-effect1#fov#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.666667, 1.2, }, 
		{{0, }, {93, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiDeepGlow_98-effect0#exposure#number'] =
{
	{
		{0.33333333, 0, 0.66666667, 1, }, 
		{0, 0.7, }, 
		{{0, }, {0.66, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.232456141, 2.3e-8, 0.796783646, 1.000000072, }, 
		{0.66, 1.966667, }, 
		{{0.79, }, {0.2, }, }, 
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
