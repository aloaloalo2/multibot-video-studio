local data = {}

local ae_compDurations = {0, 1}
data.ae_compDurations = ae_compDurations

local ae_effectType = 'transition'
data.ae_effectType = ae_effectType

local ae_transitionInputIndex = {
    {'LumiLayer_43-blend', 'InputTex', 0},
    {'LumiLayer_43-blend', 'baseTex', 1},
}
data.ae_transitionInputIndex = ae_transitionInputIndex

local ae_durations = {
    ['LumiLayer_43-blend'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.5}, },
            ['baseTex'] = {{0.5, 1}, },
        },
    },
    ['LumiChromaticAberration_136-effect1'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1}, },
        },
    },
    ['LumiGlitchSignal_136-effect2'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1}, },
        },
    },
    ['LumiTurbulenceDisplacement_136-effect3'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1}, },
        },
    },
    ['LumiSaturation_136-effect4'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1}, },
        },
    },
    ['LumiDirectionalBlurs_136-effect5'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1}, },
        },
    },
    ['LumiLayer_136-blend'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1}, },
            ['baseTex'] = {{0, 1}, },
        },
    },
}
data.ae_durations = ae_durations

local ae_attribute = {
    ['LumiLayer_43-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Precomp',
        ['blendMode'] = 0,
    },
    ['LumiChromaticAberration_136-effect1'] = {
        ['offsetX'] = 0,
        ['offsetY'] = 0,
    },
    ['LumiGlitchSignal_136-effect2'] = {
        ['lowQuality'] = 0,
        ['filterIntensity'] = 0,
        ['sharpen'] = 0,
        ['sharpenSize'] = 5,
        ['chromaNoise'] = 0,
        ['hueNoise'] = 0,
        ['chromaloss'] = 0,
        ['moireNoise'] = 0,
        ['moireSize'] = 0.5,
        ['moireSpeed'] = 0,
        ['randomSeed'] = 0,
        ['destruction'] = false,
        ['signalStrength'] = 1,
        ['d2dIntensity'] = 0,
    },
    ['LumiTurbulenceDisplacement_136-effect3'] = {
        ['size'] = 0,
        ['quantity'] = 5,
        ['complexity'] = 1,
        ['evolution'] = 720,
        ['cycle'] = 100,
        ['offset_x'] = 0,
        ['offset_y'] = 0,
        ['type'] = 0,
        ['fix_type'] = 0,
        ['picture_scale'] = 1,
        ['motion_tile_type'] = 2,
        ['qualityType'] = 3,
    },
    ['LumiSaturation_136-effect4'] = {
        ['saturationIntensity'] = 0,
    },
    ['LumiDirectionalBlurs_136-effect5'] = {
        ['blurIntensity'] = 0,
        ['angle'] = -67,
        ['directionNum'] = 1,
        ['exposure'] = 1,
        ['quality'] = 0.5,
        ['spaceDither'] = 0,
        ['borderType'] = 0,
        ['blendMode'] = 2,
    },
    ['LumiLayer_136-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 0,
    },
}
data.ae_attribute = ae_attribute

local ae_keyframes = {
    ['LumiChromaticAberration_136-effect1#offsetX#number'] =
{
	{
		{0.5, 0, 0.29, 1, }, 
		{0.3, 0.466667, }, 
		{{0, }, {1, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.539028525, 0, 0.379597553, 1, }, 
		{0.466667, 0.833333, }, 
		{{1, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiChromaticAberration_136-effect1#offsetY#number'] =
{
	{
		{0.5, 0, 0.29, 1, }, 
		{0.3, 0.533333, }, 
		{{0, }, {1, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.539028525, 0, 0.379597553, 1, }, 
		{0.533333, 0.833333, }, 
		{{1, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiGlitchSignal_136-effect2#lowQuality#number'] =
{
	{
		{0.166666667, 0.166666667, 0.29, 1, }, 
		{0.033333, 0.5, }, 
		{{0, }, {0.8, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.71, 0, 0.833333333, 0.833333333, }, 
		{0.5, 0.966667, }, 
		{{0.8, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiGlitchSignal_136-effect2#filterIntensity#number'] =
{
	{
		{0.166666667, 0.166666667, 0.29, 1, }, 
		{0.033333, 0.5, }, 
		{{0, }, {1.2, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.71, 0, 0.833333333, 0.833333333, }, 
		{0.5, 0.966667, }, 
		{{1.2, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiGlitchSignal_136-effect2#sharpen#number'] =
{
	{
		{0.166666667, 0.166666667, 0.29, 1, }, 
		{0.033333, 0.5, }, 
		{{0, }, {0.05, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.71, 0, 0.833333333, 0.833333333, }, 
		{0.5, 0.966667, }, 
		{{0.05, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiTurbulenceDisplacement_136-effect3#size#number'] =
{
	{
		{0.62, 0, 0.833333333, 0.833333333, }, 
		{0.433333, 0.5, }, 
		{{0, }, {0.1, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.166666667, 0.166666667, 0.38, 1, }, 
		{0.5, 0.866667, }, 
		{{0.1, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiTurbulenceDisplacement_136-effect3#evolution#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.2, 0.9, }, 
		{{0, }, {720, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiSaturation_136-effect4#saturationIntensity#number'] =
{
	{
		{0.52, 0, 0.48, 1, }, 
		{0.3, 0.5, }, 
		{{0, }, {0.6, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.52, 0, 0.48, 1, }, 
		{0.5, 0.7, }, 
		{{0.6, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiDirectionalBlurs_136-effect5#blurIntensity#number'] =
{
	{
		{0.78, 0, 0.833333333, 0.833333333, }, 
		{0.333333, 0.466667, }, 
		{{0, }, {50, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.166666667, 0.166666667, 0.22, 1, }, 
		{0.466667, 0.733333, }, 
		{{50, }, {0, }, }, 
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
