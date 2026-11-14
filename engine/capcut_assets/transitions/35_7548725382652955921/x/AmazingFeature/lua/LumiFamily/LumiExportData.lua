local data = {}

local ae_compDurations = {0, 1.03333333333333}
data.ae_compDurations = ae_compDurations

local ae_effectType = 'transition'
data.ae_effectType = ae_effectType

local ae_transitionInputIndex = {
    {'LumiMotionBlur3D_42-effect0', 'InputTex', 0},
    {'LumiMotionBlur3D_59-effect0', 'InputTex', 1},
}
data.ae_transitionInputIndex = ae_transitionInputIndex

local ae_durations = {
    ['LumiMotionBlur3D_42-effect0'] = {
        ['nodeDuration'] = {{0, 0.63333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.63333333333333}, },
        },
    },
    ['LumiMotionBlur3D_59-effect0'] = {
        ['nodeDuration'] = {{0.5, 1.1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.5, 1.1}, },
        },
    },
    ['LumiLayer_59-blend'] = {
        ['nodeDuration'] = {{0, 1.1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.5, 1.1}, },
            ['baseTex'] = {{0, 0.63333333333333}, },
        },
    },
}
data.ae_durations = ae_durations

local ae_attribute = {
    ['LumiMotionBlur3D_42-effect0'] = {
        ['active_cam_fovx'] = 39.5999984741211,
        ['pivot'] = Amaz.Vector3f(0.5, 0.5, 0),
        ['ae_pre_pivot'] = Amaz.Vector3f(0.5, 0.5, 0),
        ['position'] = Amaz.Vector3f(0.5, 0.5, 0),
        ['ae_pre_position'] = Amaz.Vector3f(0.5, 0.5, 0),
        ['unifiedScale'] = true,
        ['scale_x'] = 1,
        ['ae_pre_scale_x'] = 1,
        ['scale_y'] = 1,
        ['ae_pre_scale_y'] = 1,
        ['scale_z'] = 1,
        ['ae_pre_scale_z'] = 1,
        ['direction_x'] = 0,
        ['ae_pre_direction_x'] = 0,
        ['direction_y'] = 0,
        ['ae_pre_direction_y'] = 0,
        ['direction_z'] = 0,
        ['ae_pre_direction_z'] = 0,
        ['rotation_x'] = 0,
        ['ae_pre_rotation_x'] = 0,
        ['rotation_y'] = 0,
        ['ae_pre_rotation_y'] = 0,
        ['rotation_z'] = 0,
        ['ae_pre_rotation_z'] = 0,
        ['vIntensity'] = 0.5,
        ['vCenter'] = -0.25,
        ['samples'] = 24,
        ['alpha'] = 1,
        ['mirrorEdge'] = false,
        ['dither'] = 1,
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1080),
    },
    ['LumiMotionBlur3D_59-effect0'] = {
        ['active_cam_fovx'] = 39.5999984741211,
        ['pivot'] = Amaz.Vector3f(0.5, 0.5, 0),
        ['ae_pre_pivot'] = Amaz.Vector3f(0.5, 0.5, 0),
        ['position'] = Amaz.Vector3f(1.45648148148148, 0.79907407407407, 0),
        ['ae_pre_position'] = Amaz.Vector3f(1.45648148148148, 0.79907407407407, 0),
        ['unifiedScale'] = true,
        ['scale_x'] = 0.65,
        ['ae_pre_scale_x'] = 0.65,
        ['scale_y'] = 1,
        ['ae_pre_scale_y'] = 1,
        ['scale_z'] = 1,
        ['ae_pre_scale_z'] = 1,
        ['direction_x'] = 0,
        ['ae_pre_direction_x'] = 0,
        ['direction_y'] = 0,
        ['ae_pre_direction_y'] = 0,
        ['direction_z'] = 0,
        ['ae_pre_direction_z'] = 0,
        ['rotation_x'] = 0,
        ['ae_pre_rotation_x'] = 0,
        ['rotation_y'] = 33,
        ['ae_pre_rotation_y'] = 33,
        ['rotation_z'] = 0,
        ['ae_pre_rotation_z'] = 0,
        ['vIntensity'] = 0.5,
        ['vCenter'] = -0.25,
        ['samples'] = 24,
        ['alpha'] = 1,
        ['mirrorEdge'] = false,
        ['dither'] = 1,
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1080),
    },
    ['LumiLayer_59-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Precomp',
        ['blendMode'] = 0,
    },
}
data.ae_attribute = ae_attribute

local ae_keyframes = {
    ['LumiMotionBlur3D_42-effect0#ae_pre_position#vector'] =
{
	{
		{0.56, 0, 0.44, 1, }, 
		{0.23333333333333, 0.70000033333333, }, 
		{{0.5, 0.5, 0, }, {-0.2037037037037, 0.29259259259259, 0, }, {0.5, 0.5, 0, }, {-0.2037037037037, 0.29259259259259, 0, }, }, 
		{6413, }, 
		{0, }, 
	}, 
},
    ['LumiMotionBlur3D_42-effect0#position#vector'] =
{
	{
		{0.56, 0, 0.44, 1, }, 
		{0.2, 0.666667, }, 
		{{0.5, 0.5, 0, }, {-0.2037037037037, 0.29259259259259, 0, }, {0.5, 0.5, 0, }, {-0.2037037037037, 0.29259259259259, 0, }, }, 
		{6413, }, 
		{0, }, 
	}, 
},
    ['LumiMotionBlur3D_42-effect0#ae_pre_scale_x#number'] =
{
	{
		{0.13, 0, 0.44, 1, }, 
		{0.03333333333333, 0.23333333333333, }, 
		{{1, }, {0.78, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.56, 0, 0.44, 1, }, 
		{0.23333333333333, 0.70000033333333, }, 
		{{0.78, }, {0.35, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiMotionBlur3D_42-effect0#scale_x#number'] =
{
	{
		{0.13, 0, 0.44, 1, }, 
		{0, 0.2, }, 
		{{1, }, {0.78, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.56, 0, 0.44, 1, }, 
		{0.2, 0.666667, }, 
		{{0.78, }, {0.35, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiMotionBlur3D_42-effect0#ae_pre_rotation_y#number'] =
{
	{
		{0.13, 0, 0.44, 1, }, 
		{0.03333333333333, 0.23333333333333, }, 
		{{0, }, {-8, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.578604933, 0, 0.644654263, 1, }, 
		{0.23333333333333, 0.70000033333333, }, 
		{{-8, }, {-16, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiMotionBlur3D_42-effect0#rotation_y#number'] =
{
	{
		{0.13, 0, 0.44, 1, }, 
		{0, 0.2, }, 
		{{0, }, {-8, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.578604933, 0, 0.644654263, 1, }, 
		{0.2, 0.666667, }, 
		{{-8, }, {-16, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiMotionBlur3D_59-effect0#ae_pre_position#vector'] =
{
	{
		{0.21, 0, 0.25, 1, }, 
		{0.56666633333333, 0.60000033333333, }, 
		{{1.45648148148148, 0.79907407407407, 0, }, {1.06574074074074, 0.60277777777778, 0, }, {1.45648148148148, 0.79907407407407, 0, }, {1.06574074074074, 0.60277777777778, 0, }, }, 
		{6413, }, 
		{0, }, 
	}, 
	{
		{0.05, 0, 0.25, 1, }, 
		{0.60000033333333, 0.93333333333333, }, 
		{{1.06574074074074, 0.60277777777778, 0, }, {0.5, 0.5, 0, }, {1.06574074074074, 0.60277777777778, 0, }, {0.5, 0.5, 0, }, }, 
		{6413, }, 
		{0, }, 
	}, 
},
    ['LumiMotionBlur3D_59-effect0#position#vector'] =
{
	{
		{0.21, 0, 0.25, 1, }, 
		{0.533333, 0.566667, }, 
		{{1.45648148148148, 0.79907407407407, 0, }, {1.06574074074074, 0.60277777777778, 0, }, {1.45648148148148, 0.79907407407407, 0, }, {1.06574074074074, 0.60277777777778, 0, }, }, 
		{6413, }, 
		{0, }, 
	}, 
	{
		{0.05, 0, 0.25, 1, }, 
		{0.566667, 0.9, }, 
		{{1.06574074074074, 0.60277777777778, 0, }, {0.5, 0.5, 0, }, {1.06574074074074, 0.60277777777778, 0, }, {0.5, 0.5, 0, }, }, 
		{6413, }, 
		{0, }, 
	}, 
},
    ['LumiMotionBlur3D_59-effect0#ae_pre_scale_x#number'] =
{
	{
		{0.05, 0, 0.25, 1, }, 
		{0.60000033333333, 0.93333333333333, }, 
		{{0.65, }, {0.8, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.05, 0, 0.25, 1, }, 
		{0.93333333333333, 1.06666633333333, }, 
		{{0.8, }, {1, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiMotionBlur3D_59-effect0#scale_x#number'] =
{
	{
		{0.05, 0, 0.25, 1, }, 
		{0.566667, 0.9, }, 
		{{0.65, }, {0.8, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.05, 0, 0.25, 1, }, 
		{0.9, 1.033333, }, 
		{{0.8, }, {1, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiMotionBlur3D_59-effect0#ae_pre_rotation_y#number'] =
{
	{
		{0.062399728, 0, 0.280548496, 0.616226069, }, 
		{0.60000033333333, 0.93333333333333, }, 
		{{33, }, {8, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.290555272, 0.193737066, 0.621991829, 1, }, 
		{0.93333333333333, 1.06666633333333, }, 
		{{8, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiMotionBlur3D_59-effect0#rotation_y#number'] =
{
	{
		{0.062399728, 0, 0.280548496, 0.616226069, }, 
		{0.566667, 0.9, }, 
		{{33, }, {8, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.290555272, 0.193737066, 0.621991829, 1, }, 
		{0.9, 1.033333, }, 
		{{8, }, {0, }, }, 
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
