local data = {}

local ae_compDurations = {0, 0.5}
data.ae_compDurations = ae_compDurations

local ae_effectType = 'transition'
data.ae_effectType = ae_effectType

local ae_transitionInputIndex = {
    {'LumiLayer_27-trs-blend', 'baseTex', 1},
}
data.ae_transitionInputIndex = ae_transitionInputIndex

local ae_durations = {
    ['LumiLayer_27-trs-blend'] = {
        ['nodeDuration'] = {{0, 0.5}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.5}, },
            ['baseTex'] = {{0, 0.5}, },
        },
    },
    ['LumiDirectionalBlurs_200-effect0'] = {
        ['nodeDuration'] = {{0, 0.5}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.5}, },
        },
    },
    ['LumiExposure_200-effect1'] = {
        ['nodeDuration'] = {{0, 0.5}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.5}, },
        },
    },
    ['LumiLayer_200-blend'] = {
        ['nodeDuration'] = {{0, 0.5}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.5}, },
            ['baseTex'] = {{0, 0.5}, },
        },
    },
}
data.ae_durations = ae_durations

local ae_attribute = {
    ['LumiLayer_27-trs-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = true,
        ['layerType'] = 'Precomp',
        ['anchorPoint'] = Amaz.Vector3f(640, 360, 0),
        ['position'] = Amaz.Vector3f(640, 360, 0),
        ['scale'] = Amaz.Vector3f(100, 100, 100),
        ['orientation'] = Amaz.Vector3f(0, 0, 0),
        ['xRotation'] = 0,
        ['yRotation'] = 0,
        ['rotation'] = 0,
        ['opacity'] = 100,
        ['active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(1280, 720),
        ['layerSize'] = Amaz.Vector2f(1280, 720),
        ['mirrorEdge'] = false,
        ['blendMode'] = 'Normal',
    },
    ['LumiDirectionalBlurs_200-effect0'] = {
        ['blurIntensity'] = 0,
        ['angle'] = 90,
        ['directionNum'] = 1,
        ['exposure'] = 1,
        ['quality'] = 0.5,
        ['spaceDither'] = 0,
        ['borderType'] = 0,
        ['blendMode'] = 2,
    },
    ['LumiExposure_200-effect1'] = {
        ['channelType'] = 0,
        ['exposure'] = 0,
        ['offset'] = 0,
        ['grayscaleCorrection'] = 1,
        ['redExposure'] = 0,
        ['redOffset'] = 0,
        ['redGrayscaleCorrection'] = 1,
        ['greenExposure'] = 0,
        ['greenOffset'] = 0,
        ['greenGrayscaleCorrection'] = 1,
        ['blueExposure'] = 0,
        ['blueOffset'] = 0,
        ['blueGrayscaleCorrection'] = 1,
        ['noUseLinearLight'] = false,
    },
    ['LumiLayer_200-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 'Normal',
    },
}
data.ae_attribute = ae_attribute

local ae_keyframes = {
    ['LumiLayer_27-trs-blend#opacity#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0, 0.4, }, 
		{{100, }, {0, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiDirectionalBlurs_200-effect0#blurIntensity#number'] =
{
	{
		{0.33333333, 0, 0, 1.000000013, }, 
		{0, 0.233333, }, 
		{{0, }, {120, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.33333333, 0, 0, 0.99999969, }, 
		{0.233333, 0.5, }, 
		{{120, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiExposure_200-effect1#exposure#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0, 0.233333, }, 
		{{0, }, {2, }, }, 
		{6417, }, 
		{1, }, 
	}, 
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.233333, 0.5, }, 
		{{2, }, {0, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiExposure_200-effect1#grayscaleCorrection#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0, 0.233333, }, 
		{{1, }, {4, }, }, 
		{6417, }, 
		{1, }, 
	}, 
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.233333, 0.5, }, 
		{{4, }, {1, }, }, 
		{6417, }, 
		{1, }, 
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
