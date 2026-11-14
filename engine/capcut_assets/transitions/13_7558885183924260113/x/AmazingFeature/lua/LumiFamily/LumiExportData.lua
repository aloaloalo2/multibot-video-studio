local data = {}

local ae_compDurations = {0, 1}
data.ae_compDurations = ae_compDurations

local ae_effectType = 'transition'
data.ae_effectType = ae_effectType

local ae_transitionInputIndex = {
    {'LumiMotionBlur2D_3397-effect0', 'InputTex', 1},
    {'LumiLayer_3397-blend', 'baseTex', 1},
    {'LumiMotionBlur2D_3419-effect0', 'InputTex', 0},
    {'LumiLayer_3419-blend', 'baseTex', 0},
}
data.ae_transitionInputIndex = ae_transitionInputIndex

local ae_durations = {
    ['LumiMotionBlur2D_3397-effect0'] = {
        ['nodeDuration'] = {{0.33333333333333, 1.41666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.33333333333333, 1.41666666666667}, },
        },
    },
    ['LumiOpticsCompensation_3397-effect1'] = {
        ['nodeDuration'] = {{0.33333333333333, 1.41666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.33333333333333, 1.41666666666667}, },
        },
    },
    ['LumiLayer_3397-blend'] = {
        ['nodeDuration'] = {{0.33333333333333, 1.41666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.33333333333333, 1.41666666666667}, },
            ['baseTex'] = {{0.33333333333333, 1.41666666666667}, },
        },
    },
    ['LumiMotionBlur2D_3419-effect0'] = {
        ['nodeDuration'] = {{0, 0.33333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.33333333333333}, },
        },
    },
    ['LumiOpticsCompensation_3419-effect1'] = {
        ['nodeDuration'] = {{0, 0.33333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.33333333333333}, },
        },
    },
    ['LumiLayer_3419-blend'] = {
        ['nodeDuration'] = {{0, 0.33333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.33333333333333}, },
            ['baseTex'] = {{0, 0.33333333333333}, },
        },
    },
    ['LumiLayer_3433-trs'] = {
        ['nodeDuration'] = {{0, 0.33333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.33333333333333}, },
        },
    },
    ['LumiLayer_3411-trs-blend'] = {
        ['nodeDuration'] = {{0, 1.41666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.33333333333333, 1.41666666666667}, },
            ['baseTex'] = {{0, 0.33333333333333}, },
        },
    },
}
data.ae_durations = ae_durations

local ae_attribute = {
    ['LumiMotionBlur2D_3397-effect0'] = {
        ['rotate'] = 0,
        ['ae_pre_rotate'] = 0,
        ['anchor'] = Amaz.Vector2f(0.5, 0.5),
        ['ae_pre_anchor'] = Amaz.Vector2f(0.5, 0.5),
        ['position'] = Amaz.Vector2f(0.5, 0.5),
        ['ae_pre_position'] = Amaz.Vector2f(0.5, 0.5),
        ['unifiedScale'] = true,
        ['scale_x'] = 0.99690693953185,
        ['ae_pre_scale_x'] = 0.99690693953185,
        ['scale_y'] = 0.99690693953185,
        ['ae_pre_scale_y'] = 0.99690693953185,
        ['vIntensity'] = 0.5,
        ['vCenter'] = -0.25,
        ['minSamples'] = 0.12,
        ['maxSamples'] = 0.24,
        ['mirrorEdge'] = false,
        ['dither'] = 1,
        ['AEDesignSize'] = Amaz.Vector2f(1280, 1280),
    },
    ['LumiOpticsCompensation_3397-effect1'] = {
        ['fov'] = 8.83362364817322,
        ['inverseLensDistortion'] = true,
        ['fovOrientation'] = 0,
        ['center'] = Amaz.Vector2f(0.5, 0.5),
        ['antiAliasing'] = true,
        ['fillBorders'] = false,
        ['AEDesignSize'] = Amaz.Vector2f(1280, 1280),
    },
    ['LumiLayer_3397-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 0,
    },
    ['LumiMotionBlur2D_3419-effect0'] = {
        ['rotate'] = 0,
        ['ae_pre_rotate'] = 0,
        ['anchor'] = Amaz.Vector2f(0.5, 0.5),
        ['ae_pre_anchor'] = Amaz.Vector2f(0.5, 0.5),
        ['position'] = Amaz.Vector2f(0.5, 0.5),
        ['ae_pre_position'] = Amaz.Vector2f(0.5, 0.5),
        ['unifiedScale'] = true,
        ['scale_x'] = 3,
        ['ae_pre_scale_x'] = 3,
        ['scale_y'] = 3,
        ['ae_pre_scale_y'] = 3,
        ['vIntensity'] = 0.5,
        ['vCenter'] = -0.25,
        ['minSamples'] = 0.12,
        ['maxSamples'] = 0.24,
        ['mirrorEdge'] = false,
        ['dither'] = 1,
        ['AEDesignSize'] = Amaz.Vector2f(1280, 1280),
    },
    ['LumiOpticsCompensation_3419-effect1'] = {
        ['fov'] = 125,
        ['inverseLensDistortion'] = true,
        ['fovOrientation'] = 0,
        ['center'] = Amaz.Vector2f(0.5, 0.5),
        ['antiAliasing'] = true,
        ['fillBorders'] = false,
        ['AEDesignSize'] = Amaz.Vector2f(1280, 1280),
    },
    ['LumiLayer_3419-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 0,
    },
    ['LumiLayer_3433-trs'] = {
        ['hasBlend'] = false,
        ['hasMatte'] = false,
        ['hasTransform'] = true,
        ['layerType'] = 'Precomp',
        ['anchorPoint'] = Amaz.Vector3f(640, 640, 0),
        ['position'] = Amaz.Vector3f(640, 640, 0),
        ['scale'] = Amaz.Vector3f(100, 100, 100),
        ['orientation'] = Amaz.Vector3f(0, 0, 0),
        ['xRotation'] = 0,
        ['yRotation'] = 0,
        ['rotation'] = 51,
        ['opacity'] = 100,
        ['active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(1280, 1280),
        ['layerSize'] = Amaz.Vector2f(1280, 1280),
        ['mirrorEdge'] = true,
    },
    ['LumiLayer_3411-trs-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = true,
        ['layerType'] = 'Precomp',
        ['anchorPoint'] = Amaz.Vector3f(640, 640, 0),
        ['position'] = Amaz.Vector3f(640, 640, 0),
        ['scale'] = Amaz.Vector3f(100, 100, 100),
        ['orientation'] = Amaz.Vector3f(0, 0, 0),
        ['xRotation'] = 0,
        ['yRotation'] = 0,
        ['rotation'] = 0,
        ['opacity'] = 100,
        ['active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(1280, 1280),
        ['layerSize'] = Amaz.Vector2f(1280, 1280),
        ['mirrorEdge'] = true,
        ['blendMode'] = 0,
    },
}
data.ae_attribute = ae_attribute

local ae_keyframes = {
    ['LumiMotionBlur2D_3397-effect0#ae_pre_scale_x#number'] =
{
	{
		{0.33333333, 0, 0, 1, }, 
		{0.37499966666667, 1.20833366666667, }, 
		{{0.8, }, {1, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiMotionBlur2D_3397-effect0#scale_x#number'] =
{
	{
		{0.33333333, 0, 0, 1, }, 
		{0.333333, 1.166667, }, 
		{{0.8, }, {1, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiMotionBlur2D_3397-effect0#ae_pre_scale_y#number'] =
{
	{
		{0.33333333, 0, 0, 1, }, 
		{0.37499966666667, 1.20833366666667, }, 
		{{0.8, }, {1, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiMotionBlur2D_3397-effect0#scale_y#number'] =
{
	{
		{0.33333333, 0, 0, 1, }, 
		{0.333333, 1.166667, }, 
		{{0.8, }, {1, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiOpticsCompensation_3397-effect1#fov#number'] =
{
	{
		{0.166666667, 0.017861939, 0.263041693, 0.999999971, }, 
		{0.333333, 1.25, }, 
		{{170, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiMotionBlur2D_3419-effect0#ae_pre_scale_x#number'] =
{
	{
		{1, 0, 0.66666667, 1, }, 
		{0.04166666666667, 0.37499966666667, }, 
		{{1, }, {3, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiMotionBlur2D_3419-effect0#scale_x#number'] =
{
	{
		{1, 0, 0.66666667, 1, }, 
		{0, 0.333333, }, 
		{{1, }, {3, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiMotionBlur2D_3419-effect0#ae_pre_scale_y#number'] =
{
	{
		{1, 0, 0.66666667, 1, }, 
		{0.04166666666667, 0.37499966666667, }, 
		{{1, }, {3, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiMotionBlur2D_3419-effect0#scale_y#number'] =
{
	{
		{1, 0, 0.66666667, 1, }, 
		{0, 0.333333, }, 
		{{1, }, {3, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiOpticsCompensation_3419-effect1#fov#number'] =
{
	{
		{1, 0, 0.66666667, 1, }, 
		{0, 0.333333, }, 
		{{0, }, {125, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiLayer_3433-trs#rotation#number'] =
{
	{
		{1, 0, 0.66666667, 1, }, 
		{0, 0.333333, }, 
		{{0, }, {51, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiLayer_3411-trs-blend#rotation#number'] =
{
	{
		{0.0001, 0, 0, 1, }, 
		{0.333333, 1, }, 
		{{51, }, {0, }, }, 
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
