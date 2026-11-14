local data = {}

local ae_compDurations = {0, 1}
data.ae_compDurations = ae_compDurations

local ae_effectType = 'transition'
data.ae_effectType = ae_effectType

local ae_transitionInputIndex = {
    {'LumiLayer_27-trs-blend', 'baseTex', 1},
}
data.ae_transitionInputIndex = ae_transitionInputIndex

local ae_durations = {
    ['LumiLayer_27-trs-blend'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1}, },
            ['baseTex'] = {{0, 1}, },
        },
    },
    ['LumiBokehBlur_200-effect0'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1}, },
        },
    },
    ['LumiLayer_200-blend'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1}, },
            ['baseTex'] = {{0, 1}, },
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
        ['opacity'] = 0,
        ['active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(1280, 720),
        ['layerSize'] = Amaz.Vector2f(1280, 720),
        ['mirrorEdge'] = false,
        ['blendMode'] = 'Normal',
    },
    ['LumiBokehBlur_200-effect0'] = {
        ['bokehMode'] = 2,
        ['sample'] = 35,
        ['scaleX'] = 1,
        ['scaleY'] = 1,
        ['regionIns'] = 0,
        ['lightIns'] = 2,
        ['quality'] = 0.5,
        ['angle'] = 0,
        ['lineNum'] = 6,
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
    ['LumiBokehBlur_200-effect0#sample#number'] =
{
	{
		{0.33333333, 0, 0.66666667, 1, }, 
		{0, 0.5, }, 
		{{0, }, {35, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.33333333, 0, 0.66666667, 1, }, 
		{0.5, 0.833333, }, 
		{{35, }, {0, }, }, 
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
