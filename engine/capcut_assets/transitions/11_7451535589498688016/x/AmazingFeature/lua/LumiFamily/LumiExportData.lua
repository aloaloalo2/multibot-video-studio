local data = {}

local ae_compDurations = {0, 1.5}
data.ae_compDurations = ae_compDurations

local ae_effectType = 'transition'
data.ae_effectType = ae_effectType

local ae_transitionInputIndex = {
    {'LumiLayer_27-trs-blend', 'baseTex', 1},
}
data.ae_transitionInputIndex = ae_transitionInputIndex

local ae_durations = {
    ['LumiRadialBlur_27-effect0'] = {
        ['nodeDuration'] = {{0, 1.5}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.5}, },
        },
    },
    ['LumiWaveWarp_27-effect1'] = {
        ['nodeDuration'] = {{0, 1.5}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.5}, },
        },
    },
    ['LumiLayer_27-trs-blend'] = {
        ['nodeDuration'] = {{0, 1.5}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.5}, },
            ['baseTex'] = {{0, 1.5}, },
        },
    },
    ['LumiExposure_195-effect0'] = {
        ['nodeDuration'] = {{0.03333333333333, 0.66666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.5}, },
        },
    },
    ['LumiLayer_195-blend'] = {
        ['nodeDuration'] = {{0, 1.5}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.03333333333333, 0.66666666666667}, },
            ['baseTex'] = {{0, 1.5}, },
        },
    },
}
data.ae_durations = ae_durations

local ae_attribute = {
    ['LumiRadialBlur_27-effect0'] = {
        ['blurType'] = 0,
        ['amount'] = 0,
        ['quality'] = 0.20000000298023,
        ['center'] = Amaz.Vector2f(0.5, 0),
        ['weightDecay'] = 0.965,
        ['dither'] = 1,
        ['blurAlpha'] = true,
        ['inverseGammaCorrection'] = false,
        ['borderType'] = 0,
    },
    ['LumiWaveWarp_27-effect1'] = {
        ['type'] = 0,
        ['amplitude'] = 0,
        ['wavelength'] = 450,
        ['direction'] = 90,
        ['speed'] = 2,
        ['fixedType'] = 1,
        ['phase'] = 0,
        ['antiAliasing'] = 0,
    },
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
    ['LumiExposure_195-effect0'] = {
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
    ['LumiLayer_195-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 'Normal',
    },
}
data.ae_attribute = ae_attribute

local ae_keyframes = {
    ['LumiRadialBlur_27-effect0#amount#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0, 1.5, }, 
		{{0, }, {90, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiWaveWarp_27-effect1#amplitude#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0, 1.5, }, 
		{{0, }, {20, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiLayer_27-trs-blend#position#vector'] =
{
	{
		{0.333333, 0, 0, 1, }, 
		{0, 1.5, }, 
		{{640, 360, 0, }, {640, 0, 0, }, {640, 300, 0, }, {640, 60, 0, }, }, 
		{6413, }, 
		{0, }, 
	}, 
},
    ['LumiLayer_27-trs-blend#scale#vector'] =
{
	{
		{0.33333333,0.33333333,0.33333333, 0,0,0.33333333, 0,0,0.66666667, 1.000000069,1.000000069,0.66666667, }, 
		{0, 1.5, }, 
		{{100, 100, 100, }, {200, 200, 100, }, }, 
		{6414, }, 
		{0, }, 
	}, 
},
    ['LumiLayer_27-trs-blend#opacity#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0, 1.5, }, 
		{{100, }, {0, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiExposure_195-effect0#exposure#number'] =
{
	{
		{0.33333333, 0, 0.66666667, 1, }, 
		{0.033333, 0.2, }, 
		{{0, }, {3, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.33333333, 0, 0.66666667, 1, }, 
		{0.2, 0.366667, }, 
		{{3, }, {0, }, }, 
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
