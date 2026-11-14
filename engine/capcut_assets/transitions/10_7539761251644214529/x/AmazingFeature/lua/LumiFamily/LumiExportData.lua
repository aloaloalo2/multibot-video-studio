local data = {}

local ae_compDurations = {0, 1}
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
        ['nodeDuration'] = {{0.13333333333333, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.13333333333333, 1}, },
        },
    },
    ['LumiDisplacementMap_202-effect0'] = {
        ['nodeDuration'] = {{0.13333333333333, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.13333333333333, 1}, },
            ['horizontalImage'] = {{0.13333333333333, 1}, },
            ['verticalImage'] = {{0.13333333333333, 1}, },
        },
    },
    ['LumiLayer_202-blend'] = {
        ['nodeDuration'] = {{0.13333333333333, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.13333333333333, 1}, },
            ['baseTex'] = {{0.13333333333333, 1}, },
        },
    },
    ['LumiLayer_1803-trs'] = {
        ['nodeDuration'] = {{0, 0.23333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.23333333333333}, },
        },
    },
    ['LumiLayer_1802-trs-blend'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.13333333333333, 1}, },
            ['baseTex'] = {{0, 0.23333333333333}, },
        },
    },
    ['LumiChromaticAberration_1801-effect0'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1}, },
        },
    },
    ['LumiGaussianBlur_1801-effect1'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1}, },
        },
    },
    ['LumiExposure_1801-effect2'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1}, },
        },
    },
    ['LumiLayer_1801-blend'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1}, },
            ['baseTex'] = {{0, 1}, },
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
        ['blurRadius'] = 3,
        ['segment'] = false,
        ['invert'] = false,
        ['quality'] = 0.13631586175216,
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1080),
    },
    ['LumiDisplacementMap_202-effect0'] = {
        ['horizontalType'] = 0,
        ['horizontalIntensity'] = -0.1,
        ['verticalType'] = 0,
        ['verticalIntensity'] = 0,
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
        ['position'] = Amaz.Vector3f(0, 540, 0),
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
        ['rotation'] = 0,
        ['opacity'] = 100,
        ['active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(1080, 1080),
        ['layerSize'] = Amaz.Vector2f(1080, 1080),
        ['mirrorEdge'] = false,
        ['blendMode'] = 0,
    },
    ['LumiChromaticAberration_1801-effect0'] = {
        ['offsetX'] = -0.34210913778539,
        ['offsetY'] = 0,
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1080),
    },
    ['LumiGaussianBlur_1801-effect1'] = {
        ['blurIntensity'] = 83.430101487121,
        ['quality'] = 0.21810537880345,
        ['spaceDither'] = 0,
        ['horizontalStrength'] = 1,
        ['verticalStrength'] = 1,
        ['blurDirection'] = 1,
        ['borderType'] = 0,
        ['blurAlpha'] = true,
        ['inverseGammaCorrection'] = true,
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1080),
    },
    ['LumiExposure_1801-effect2'] = {
        ['channelType'] = 0,
        ['exposure'] = 0.54703374945849,
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
		{0.237929464, 0, 0.701046672, 1, }, 
		{0, 0.233333, }, 
		{{-0.05, }, {-0.1, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.19, 0, 0.37, 1, }, 
		{0.233333, 0.3, }, 
		{{-0.1, }, {0.3, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.329226394, 0, 0.546234434, 1, }, 
		{0.3, 0.466667, }, 
		{{0.3, }, {-0.1, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.36807542, 0, 0.525105064, 1, }, 
		{0.466667, 0.6, }, 
		{{-0.1, }, {0.035, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.27, 0, 0.587123101, 1, }, 
		{0.6, 0.733333, }, 
		{{0.035, }, {-0.015, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.287463416, 0, 0.63, 1, }, 
		{0.733333, 0.866667, }, 
		{{-0.015, }, {0.005, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.266748418, 0, 0.644836639, 1, }, 
		{0.866667, 1, }, 
		{{0.005, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiDisplacementMap_202-effect0#verticalIntensity#number'] =
{
	{
		{0.366017388, 0, 0.565253241, 1, }, 
		{0.3, 0.366667, }, 
		{{0, }, {0.055, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.22732188, 0, 0.620590074, 1, }, 
		{0.366667, 0.533333, }, 
		{{0.055, }, {-0.03, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.218184905, 0, 0.594923539, 1, }, 
		{0.533333, 0.733333, }, 
		{{-0.03, }, {0.007, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.223560946, 0, 0.544783814, 1, }, 
		{0.733333, 0.933333, }, 
		{{0.007, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiLayer_1803-trs#position#vector'] =
{
	{
		{0.42, 0, 0.999, 1, }, 
		{0, 0.033333, }, 
		{{540, 540, 0, }, {534, 540, 0, }, {540, 540, 0, }, {534, 540, 0, }, }, 
		{6413, }, 
		{0, }, 
	}, 
	{
		{0.61, 0.17, 0.69, 1, }, 
		{0.033333, 0.233333, }, 
		{{534, 540, 0, }, {0, 540, 0, }, {534, 540, 0, }, {0, 540, 0, }, }, 
		{6413, }, 
		{0, }, 
	}, 
},
    ['LumiLayer_1802-trs-blend#position#vector'] =
{
	{
		{0.59, 0.33, 0.76, 1, }, 
		{0.133333, 0.233333, }, 
		{{1666, 540, 0, }, {540, 540, 0, }, {1666, 540, 0, }, {540, 540, 0, }, }, 
		{6413, }, 
		{0, }, 
	}, 
},
    ['LumiChromaticAberration_1801-effect0#offsetX#number'] =
{
	{
		{0.26, 0, 0.464278503, 1, }, 
		{0.1, 0.3, }, 
		{{0, }, {-0.4, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.297005612, 0, 0.676552347, 1, }, 
		{0.3, 0.866667, }, 
		{{-0.4, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiGaussianBlur_1801-effect1#blurIntensity#number'] =
{
	{
		{0.527964118, 0, 0.582269971, 0.893781599, }, 
		{0.033333, 0.166667, }, 
		{{0, }, {78, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.224324661, 0.58167829, 0.615532099, 1, }, 
		{0.166667, 0.3, }, 
		{{78, }, {85, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.236729176, 0, 0.531473464, 1, }, 
		{0.3, 0.8, }, 
		{{85, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiExposure_1801-effect2#exposure#number'] =
{
	{
		{0.214976024, 0, 0.592705066, 0.819558949, }, 
		{0.033333, 0.266667, }, 
		{{0, }, {0.6, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.556198202, 0.072746694, 0.7, 0.510677106, }, 
		{0.266667, 0.3, }, 
		{{0.6, }, {0.9, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.080032535, 0.834781274, 0.687903332, 1, }, 
		{0.3, 0.933333, }, 
		{{0.9, }, {0, }, }, 
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
