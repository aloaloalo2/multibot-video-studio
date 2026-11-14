local data = {}

local ae_compDurations = {0, 1.53333333333333}
data.ae_compDurations = ae_compDurations

local ae_effectType = 'transition'
data.ae_effectType = ae_effectType

local ae_transitionInputIndex = {
    {'LumiDepth_201-effect0', 'InputTex', 1},
    {'LumiDisplacementMap_202-effect0', 'InputTex', 1},
    {'LumiLayer_202-blend', 'baseTex', 1},
    {'LumiLayer_1803-trs', 'InputTex', 0},
}
data.ae_transitionInputIndex = ae_transitionInputIndex

local ae_durations = {
    ['LumiDepth_201-effect0'] = {
        ['nodeDuration'] = {{0.26666666666667, 1.53333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.26666666666667, 1.53333333333333}, },
        },
    },
    ['LumiDisplacementMap_202-effect0'] = {
        ['nodeDuration'] = {{0.26666666666667, 1.53333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.26666666666667, 1.53333333333333}, },
            ['horizontalImage'] = {{0.26666666666667, 1.53333333333333}, },
            ['verticalImage'] = {{0.26666666666667, 1.53333333333333}, },
        },
    },
    ['LumiLayer_202-blend'] = {
        ['nodeDuration'] = {{0.26666666666667, 1.53333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.26666666666667, 1.53333333333333}, },
            ['baseTex'] = {{0.26666666666667, 1.53333333333333}, },
        },
    },
    ['LumiLayer_1803-trs'] = {
        ['nodeDuration'] = {{0, 0.26666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.26666666666667}, },
        },
    },
    ['LumiLayer_1802-trs-blend'] = {
        ['nodeDuration'] = {{0, 1.53333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.26666666666667, 1.53333333333333}, },
            ['baseTex'] = {{0, 0.26666666666667}, },
        },
    },
    ['LumiBCC_Prism_1801-effect0'] = {
        ['nodeDuration'] = {{0, 1.53333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.53333333333333}, },
        },
    },
    ['LumiExposure_1801-effect1'] = {
        ['nodeDuration'] = {{0, 1.53333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.53333333333333}, },
        },
    },
    ['LumiLayer_1801-blend'] = {
        ['nodeDuration'] = {{0, 1.53333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.53333333333333}, },
            ['baseTex'] = {{0, 1.53333333333333}, },
        },
    },
}
data.ae_durations = ae_durations

local ae_attribute = {
    ['LumiDepth_201-effect0'] = {
        ['opticalFlowWeight'] = 0.69999998807907,
        ['mapMode'] = 0,
        ['mapValueX'] = 1.23000001907349,
        ['mapValueY'] = 1.67999994754791,
        ['threshold'] = false,
        ['minThreshold'] = 0,
        ['maxThreshold'] = 1,
        ['blurRadius'] = 25,
        ['segment'] = false,
        ['invert'] = false,
        ['quality'] = 0.11105280022872,
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1080),
    },
    ['LumiDisplacementMap_202-effect0'] = {
        ['horizontalType'] = 0,
        ['horizontalIntensity'] = -0.03119423330912,
        ['verticalType'] = 0,
        ['verticalIntensity'] = 0.12,
        ['edgeType'] = 1,
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1080),
    },
    ['LumiLayer_202-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 0,
    },
    ['LumiLayer_1803-trs'] = {
        ['hasBlend'] = false,
        ['hasMatte'] = false,
        ['hasTransform'] = true,
        ['layerType'] = 'Precomp',
        ['anchorPoint'] = Amaz.Vector3f(540, 540, 0),
        ['position'] = Amaz.Vector3f(540, 540, 0),
        ['scale'] = Amaz.Vector3f(100, 100, 100),
        ['orientation'] = Amaz.Vector3f(0, 0, 0),
        ['xRotation'] = 0,
        ['yRotation'] = 0,
        ['rotation'] = 0,
        ['opacity'] = 100,
        ['active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(1080, 1080),
        ['layerSize'] = Amaz.Vector2f(1080, 1080),
        ['mirrorEdge'] = true,
    },
    ['LumiLayer_1802-trs-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = true,
        ['layerType'] = 'Precomp',
        ['anchorPoint'] = Amaz.Vector3f(540, 540, 0),
        ['position'] = Amaz.Vector3f(540, 540, 0),
        ['scale'] = Amaz.Vector3f(100, 100, 100),
        ['orientation'] = Amaz.Vector3f(0, 0, 0),
        ['xRotation'] = 0,
        ['yRotation'] = 0,
        ['rotation'] = -75,
        ['opacity'] = 100,
        ['active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(1080, 1080),
        ['layerSize'] = Amaz.Vector2f(1080, 1080),
        ['mirrorEdge'] = true,
        ['blendMode'] = 0,
    },
    ['LumiBCC_Prism_1801-effect0'] = {
        ['globalTransform'] = 0,
        ['smoothness'] = 0.25,
        ['center'] = Amaz.Vector2f(0.5, 0.5),
        ['weight'] = 1,
        ['scaleStart'] = 110,
        ['scaleEnd'] = 90,
        ['angleStart'] = 90,
        ['angleEnd'] = -90,
        ['falloff'] = 0,
        ['offsetStart'] = Amaz.Vector2f(0.5, 0.5),
        ['offsetEnd'] = Amaz.Vector2f(0.5, 0.5),
        ['colorStart'] = Amaz.Color(1, 0.05620932579041, 0.45593258738518, 1),
        ['colorMid'] = Amaz.Color(0.75294250249863, 1, 0, 1),
        ['colorEnd'] = Amaz.Color(0, 0.47843092679977, 1, 1),
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1080),
    },
    ['LumiExposure_1801-effect1'] = {
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
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1080),
    },
    ['LumiLayer_1801-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 0,
    },
}
data.ae_attribute = ae_attribute

local ae_keyframes = {
    ['LumiDisplacementMap_202-effect0#horizontalIntensity#number'] =
{
	{
		{0.381325985, 0.038958717, 0.788544521, 1, }, 
		{0.233333, 0.5, }, 
		{{-0.03119423, }, {0.12, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.329226394, 0, 0.546234434, 1, }, 
		{0.5, 0.733333, }, 
		{{0.12, }, {-0.1, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.289341633, 0, 0.636899983, 1, }, 
		{0.733333, 0.966667, }, 
		{{-0.1, }, {0.05, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.319683452, 0, 0.631181066, 1, }, 
		{0.966667, 1.233333, }, 
		{{0.05, }, {-0.006, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.176963493, 0, 0.244575122, 1, }, 
		{1.233333, 1.533333, }, 
		{{-0.006, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiDisplacementMap_202-effect0#verticalIntensity#number'] =
{
	{
		{0.593771706, 0, 0.591803057, 1, }, 
		{0.3, 0.633333, }, 
		{{0.12, }, {-0.11, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.22732188, 0, 0.620590074, 1, }, 
		{0.633333, 0.866667, }, 
		{{-0.11, }, {0.05887622, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.218184905, 0, 0.628111916, 1, }, 
		{0.866667, 1.1, }, 
		{{0.05887622, }, {-0.014, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.209043298, 0, 0.351361803, 1, }, 
		{1.1, 1.366667, }, 
		{{-0.014, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiLayer_1803-trs#rotation#number'] =
{
	{
		{0.8, 0, 0.999, 1, }, 
		{0, 0.266667, }, 
		{{0, }, {105, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiLayer_1802-trs-blend#rotation#number'] =
{
	{
		{0.001, 0, 0.280994624, 1, }, 
		{0.266667, 0.5, }, 
		{{-75, }, {17, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.416549562, 0, 0.590382608, 1, }, 
		{0.5, 0.733333, }, 
		{{17, }, {-13, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.305650501, 0, 0.576549785, 1, }, 
		{0.733333, 1, }, 
		{{-13, }, {5, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.221579454, 0, 0.528501981, 1, }, 
		{1, 1.3, }, 
		{{5, }, {-0.66, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.22, 0, 0.53, 1, }, 
		{1.3, 1.533333, }, 
		{{-0.66, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiBCC_Prism_1801-effect0#globalTransform#number'] =
{
	{
		{0.599039659, 0, 0.947471189, 0.752636284, }, 
		{0, 0.266667, }, 
		{{0, }, {15, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.216540907, 0.499146953, 0.718793231, 1, }, 
		{0.266667, 0.5, }, 
		{{15, }, {7.5, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.261972861, 0, 0.48423533, 1, }, 
		{0.5, 0.6, }, 
		{{7.5, }, {8, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.348600017, 0, 0.673610462, 1, }, 
		{0.6, 0.733333, }, 
		{{8, }, {4.632455, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.222550945, 0, 0.510975762, 1, }, 
		{0.733333, 0.833333, }, 
		{{4.632455, }, {5.393391, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.370300608, 0, 0.683029218, 1, }, 
		{0.833333, 1, }, 
		{{5.393391, }, {1.88769, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.297846811, 0, 0.527223988, 1, }, 
		{1, 1.133333, }, 
		{{1.88769, }, {2.58779, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.282633142, 0, 0.699607773, 1, }, 
		{1.133333, 1.3, }, 
		{{2.58779, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiExposure_1801-effect1#exposure#number'] =
{
	{
		{0.599458866, 0, 0.924453477, 0.484385317, }, 
		{0, 0.266667, }, 
		{{0, }, {1, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.19950356, 0.778036775, 0.739292569, 1, }, 
		{0.266667, 1.466667, }, 
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
