local data = {}

local ae_compDurations = {0, 1}
data.ae_compDurations = ae_compDurations

local ae_effectType = 'transition'
data.ae_effectType = ae_effectType

local ae_transitionInputIndex = {
    {'LumiTurbulenceDisplacement_48-effect0', 'InputTex', 1},
    {'LumiLayer_48-blend', 'baseTex', 0},
}
data.ae_transitionInputIndex = ae_transitionInputIndex

local ae_durations = {
    ['LumiTurbulenceDisplacement_48-effect0'] = {
        ['nodeDuration'] = {{0.33333333333333, 3}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.33333333333333, 3}, },
        },
    },
    ['LumiLayer_48-blend'] = {
        ['nodeDuration'] = {{0, 3}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.33333333333333, 3}, },
            ['baseTex'] = {{0, 0.33333333333333}, },
        },
    },
    ['LumiPixelSort_51-effect0'] = {
        ['nodeDuration'] = {{0.23333333333333, 0.43333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 3}, },
        },
    },
    ['LumiLayer_51-blend'] = {
        ['nodeDuration'] = {{0, 3}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.23333333333333, 0.43333333333333}, },
            ['baseTex'] = {{0, 3}, },
        },
    },
}
data.ae_durations = ae_durations

local ae_attribute = {
    ['LumiTurbulenceDisplacement_48-effect0'] = {
        ['size'] = 0.04,
        ['quantity'] = 10,
        ['complexity'] = 5,
        ['evolution'] = 0,
        ['cycle'] = 100,
        ['offset_x'] = 0,
        ['offset_y'] = 0,
        ['type'] = 0,
        ['fix_type'] = 0,
        ['picture_scale'] = 1,
        ['motion_tile_type'] = 2,
        ['qualityType'] = 3,
        ['AEDesignSize'] = Amaz.Vector2f(672, 504),
    },
    ['LumiLayer_48-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Precomp',
        ['blendMode'] = 0,
    },
    ['LumiPixelSort_51-effect0'] = {
        ['threshold'] = 0,
        ['rotate'] = 90,
        ['randomly'] = 1,
        ['reverseSort'] = false,
        ['affectType'] = 0,
        ['triggerType'] = 0,
        ['sortType'] = 0,
        ['featherStart'] = 0,
        ['featherEnd'] = 0,
        ['length'] = 0,
        ['offset'] = 0,
        ['offsetRandom'] = 0,
        ['randomSeed'] = 0,
        ['cycle'] = 0,
        ['blockSize'] = 0.01,
        ['blurSize'] = 0,
        ['outputType'] = 0,
        ['AEDesignSize'] = Amaz.Vector2f(672, 504),
    },
    ['LumiLayer_51-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 0,
    },
}
data.ae_attribute = ae_attribute

local ae_keyframes = {
    ['LumiTurbulenceDisplacement_48-effect0#size#number'] =
{
	{
		{0.33333333, 0, 0.66666667, 1, }, 
		{0.333333, 0.666667, }, 
		{{0.04, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiTurbulenceDisplacement_48-effect0#evolution#number'] =
{
	{
		{0.33333333, 0, 0.66666667, 1, }, 
		{0.333333, 0.666667, }, 
		{{0, }, {720, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiPixelSort_51-effect0#length#number'] =
{
	{
		{0.0001, 0, 0.339192692, 1.000000045, }, 
		{0.233333, 0.333333, }, 
		{{0, }, {1, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{1, 0, 0.339192692, 3e-8, }, 
		{0.333333, 0.4, }, 
		{{1, }, {1, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{1, 0, 0.9999, 1, }, 
		{0.4, 0.433333, }, 
		{{1, }, {0, }, }, 
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
