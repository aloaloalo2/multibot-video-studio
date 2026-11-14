local data = {}

local ae_compDurations = {0, 1.63333333333333}
data.ae_compDurations = ae_compDurations

local ae_effectType = 'transition'
data.ae_effectType = ae_effectType

local ae_transitionInputIndex = {
    {'LumiLayer_205-blend', 'baseTex', 1},
}
data.ae_transitionInputIndex = ae_transitionInputIndex

local ae_durations = {
    ['LumiLayer_205-blend'] = {
        ['nodeDuration'] = {{0, 1.66666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.83333333333333}, },
            ['baseTex'] = {{0.83333333333333, 1.66666666666667}, },
        },
    },
    ['LumiSShake_503-effect0'] = {
        ['nodeDuration'] = {{0.83333333333333, 1.03333333333333}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.66666666666667}, },
        },
    },
    ['LumiLayer_503-blend'] = {
        ['nodeDuration'] = {{0, 1.66666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.83333333333333, 1.03333333333333}, },
            ['baseTex'] = {{0, 1.66666666666667}, },
        },
    },
    ['LumiFlicker_509-effect0'] = {
        ['nodeDuration'] = {{0.66666666666667, 1.1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.66666666666667}, },
        },
    },
    ['LumiWarp_509-effect1'] = {
        ['nodeDuration'] = {{0.66666666666667, 1.1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.66666666666667, 1.1}, },
        },
    },
    ['LumiDeepGlow_509-effect2'] = {
        ['nodeDuration'] = {{0.66666666666667, 1.1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.66666666666667, 1.1}, },
        },
    },
    ['LumiGaussianBlur_509-effect3'] = {
        ['nodeDuration'] = {{0.66666666666667, 1.1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.66666666666667, 1.1}, },
        },
    },
    ['LumiLinearWipe_555-effect0'] = {
        ['nodeDuration'] = {{0, 1.66666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.66666666666667}, },
        },
    },
    ['LumiLayer_555-trs'] = {
        ['nodeDuration'] = {{0, 1.66666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.66666666666667}, },
        },
    },
    ['LumiLinearWipe_556-effect0'] = {
        ['nodeDuration'] = {{0, 1.66666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.66666666666667}, },
        },
    },
    ['LumiLayer_556-trs-blend'] = {
        ['nodeDuration'] = {{0, 1.66666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.66666666666667}, },
            ['baseTex'] = {{0, 1.66666666666667}, },
        },
    },
    ['LumiLayer_509-blend'] = {
        ['nodeDuration'] = {{0, 1.66666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.66666666666667, 1.1}, },
            ['baseTex'] = {{0, 1.66666666666667}, },
        },
    },
    ['LumiLinearWipe_573-effect0'] = {
        ['nodeDuration'] = {{0, 1.66666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.66666666666667}, },
        },
    },
    ['LumiLinearWipe_561-effect0'] = {
        ['nodeDuration'] = {{0, 1.66666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.66666666666667}, },
        },
    },
    ['LumiLayer_561-trs'] = {
        ['nodeDuration'] = {{0, 1.66666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.66666666666667}, },
        },
    },
    ['LumiLayer_573-trs-blend'] = {
        ['nodeDuration'] = {{0, 1.66666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.66666666666667}, },
            ['baseTex'] = {{0, 1.66666666666667}, },
        },
    },
    ['LumiLayer_575-blend'] = {
        ['nodeDuration'] = {{0, 1.66666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.66666666666667}, },
            ['baseTex'] = {{0, 1.66666666666667}, },
        },
    },
    ['LumiLayer_576-blend'] = {
        ['nodeDuration'] = {{0, 1.66666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1.66666666666667}, },
            ['baseTex'] = {{0, 1.66666666666667}, },
        },
    },
}
data.ae_durations = ae_durations

local ae_attribute = {
    ['LumiLayer_205-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Precomp',
        ['blendMode'] = 0,
    },
    ['LumiSShake_503-effect0'] = {
        ['ampRatio'] = 0.5,
        ['frqRatio'] = 30,
        ['phase0'] = 0,
        ['scale0'] = 1,
        ['blurEnabled'] = false,
        ['blurIntensity'] = 1,
        ['blurQuality'] = 0,
        ['seed'] = 0,
        ['xFill'] = 2,
        ['yFill'] = 2,
        ['xAmpR'] = 192,
        ['xFrqR'] = 1,
        ['xAmp'] = 0,
        ['xFrq'] = 0.5,
        ['xPhase'] = 0,
        ['yAmpR'] = 192,
        ['yFrqR'] = 1,
        ['yAmp'] = 0,
        ['yFrq'] = 0.5,
        ['yPhase'] = 0,
        ['zAmpR'] = 0,
        ['zFrqR'] = 1,
        ['zAmp'] = 0,
        ['zFrq'] = 0.5,
        ['zPhase'] = 0,
        ['wAmpR'] = 0,
        ['wFrqR'] = 1,
        ['wAmp'] = 0,
        ['wFrq'] = 0.5,
        ['wPhase'] = 0,
        ['rAmpRatio'] = 1,
        ['gAmpRatio'] = 1,
        ['bAmpRatio'] = 1,
        ['rPhase'] = 0,
        ['gPhase'] = 0,
        ['bPhase'] = 0,
        ['rgbRnd'] = 0,
        ['rgbFrq'] = 2,
        ['AEDesignSize'] = Amaz.Vector2f(720, 1280),
    },
    ['LumiLayer_503-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 0,
    },
    ['LumiFlicker_509-effect0'] = {
        ['amp0'] = 0.2,
        ['ampRL'] = 1,
        ['ampRC'] = 0,
        ['frqR'] = 10,
        ['ampW'] = 0,
        ['frqW'] = 5,
        ['phaseWR'] = 0,
        ['phaseWG'] = 0,
        ['phaseWB'] = 0,
        ['ampR'] = 1,
        ['ampG'] = 1,
        ['ampB'] = 1,
        ['brightness'] = 1,
        ['seed'] = 0.12300000339746,
        ['AEDesignSize'] = Amaz.Vector2f(720, 1280),
    },
    ['LumiWarp_509-effect1'] = {
        ['warpStyle'] = 12,
        ['warpAxis'] = 0,
        ['bend'] = 0,
        ['AEDesignSize'] = Amaz.Vector2f(720, 1280),
    },
    ['LumiDeepGlow_509-effect2'] = {
        ['radius'] = 200,
        ['exposure'] = 0,
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
        ['quality'] = 1,
        ['AEDesignSize'] = Amaz.Vector2f(720, 1280),
    },
    ['LumiGaussianBlur_509-effect3'] = {
        ['blurIntensity'] = 0,
        ['quality'] = 0.5,
        ['spaceDither'] = 0,
        ['horizontalStrength'] = 1,
        ['verticalStrength'] = 1,
        ['blurDirection'] = 0,
        ['borderType'] = 0,
        ['blurAlpha'] = true,
        ['inverseGammaCorrection'] = true,
        ['AEDesignSize'] = Amaz.Vector2f(720, 1280),
    },
    ['LumiLinearWipe_555-effect0'] = {
        ['progress'] = 0.74,
        ['rotation'] = 180,
        ['feather'] = 0.03,
        ['AEDesignSize'] = Amaz.Vector2f(720, 1280),
    },
    ['LumiLayer_555-trs'] = {
        ['hasBlend'] = false,
        ['hasMatte'] = false,
        ['hasTransform'] = true,
        ['layerType'] = 'Solid',
        ['anchorPoint'] = Amaz.Vector3f(360, 640, 0),
        ['position'] = Amaz.Vector3f(360, 690, 0),
        ['scale'] = Amaz.Vector3f(100, 100, 100),
        ['orientation'] = Amaz.Vector3f(0, 0, 0),
        ['xRotation'] = 0,
        ['yRotation'] = 0,
        ['rotation'] = 0,
        ['opacity'] = 100,
        ['active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(720, 1280),
        ['layerSize'] = Amaz.Vector2f(720, 1280),
        ['mirrorEdge'] = false,
    },
    ['LumiLinearWipe_556-effect0'] = {
        ['progress'] = 0.74,
        ['rotation'] = 0,
        ['feather'] = 0.03,
        ['AEDesignSize'] = Amaz.Vector2f(720, 1280),
    },
    ['LumiLayer_556-trs-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = true,
        ['layerType'] = 'Solid',
        ['anchorPoint'] = Amaz.Vector3f(360, 640, 0),
        ['position'] = Amaz.Vector3f(360, 590, 0),
        ['scale'] = Amaz.Vector3f(100, 100, 100),
        ['orientation'] = Amaz.Vector3f(0, 0, 0),
        ['xRotation'] = 0,
        ['yRotation'] = 0,
        ['rotation'] = 0,
        ['opacity'] = 100,
        ['active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(720, 1280),
        ['layerSize'] = Amaz.Vector2f(720, 1280),
        ['mirrorEdge'] = false,
        ['blendMode'] = 0,
    },
    ['LumiLayer_509-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 0,
    },
    ['LumiLinearWipe_573-effect0'] = {
        ['progress'] = 0.5,
        ['rotation'] = 0,
        ['feather'] = 0.03,
        ['AEDesignSize'] = Amaz.Vector2f(720, 1280),
    },
    ['LumiLinearWipe_561-effect0'] = {
        ['progress'] = 0.5,
        ['rotation'] = 180,
        ['feather'] = 0.03,
        ['AEDesignSize'] = Amaz.Vector2f(720, 1280),
    },
    ['LumiLayer_561-trs'] = {
        ['hasBlend'] = false,
        ['hasMatte'] = false,
        ['hasTransform'] = true,
        ['layerType'] = 'Solid',
        ['anchorPoint'] = Amaz.Vector3f(360, 640, 0),
        ['position'] = Amaz.Vector3f(360, 1310, 0),
        ['scale'] = Amaz.Vector3f(100, 100, 100),
        ['orientation'] = Amaz.Vector3f(0, 0, 0),
        ['xRotation'] = 0,
        ['yRotation'] = 0,
        ['rotation'] = 0,
        ['opacity'] = 100,
        ['active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(720, 1280),
        ['layerSize'] = Amaz.Vector2f(720, 1280),
        ['mirrorEdge'] = false,
    },
    ['LumiLayer_573-trs-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = true,
        ['layerType'] = 'Solid',
        ['anchorPoint'] = Amaz.Vector3f(360, 640, 0),
        ['position'] = Amaz.Vector3f(360, -30, 0),
        ['scale'] = Amaz.Vector3f(100, 100, 100),
        ['orientation'] = Amaz.Vector3f(0, 0, 0),
        ['xRotation'] = 0,
        ['yRotation'] = 0,
        ['rotation'] = 0,
        ['opacity'] = 100,
        ['active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(720, 1280),
        ['layerSize'] = Amaz.Vector2f(720, 1280),
        ['mirrorEdge'] = false,
        ['blendMode'] = 0,
    },
    ['LumiLayer_575-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Precomp',
        ['blendMode'] = 0,
    },
    ['LumiLayer_576-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Precomp',
        ['blendMode'] = 0,
    },
}
data.ae_attribute = ae_attribute

local ae_keyframes = {
    ['LumiSShake_503-effect0#ampRatio#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.833333, 1.033333, }, 
		{{0.5, }, {0, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiFlicker_509-effect0#amp0#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.833333, 1.1, }, 
		{{0.2, }, {0, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiWarp_509-effect1#bend#number'] =
{
	{
		{0.33333333, 0, 0, 0.999999957, }, 
		{0.666667, 0.833333, }, 
		{{0, }, {45, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.33333333, 0, 0, 1.000000057, }, 
		{0.833333, 1, }, 
		{{45, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiDeepGlow_509-effect2#exposure#number'] =
{
	{
		{0.33333333, 0, 0, 1.000000054, }, 
		{0.666667, 0.833333, }, 
		{{0, }, {3, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.33333333, 0, 0, 1.000000109, }, 
		{0.833333, 1, }, 
		{{3, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiGaussianBlur_509-effect3#blurIntensity#number'] =
{
	{
		{0.33333333, 0, 0, 0.999999957, }, 
		{0.666667, 0.833333, }, 
		{{0, }, {20, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.33333333, 0, 0, 1.000000057, }, 
		{0.833333, 1, }, 
		{{20, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiLinearWipe_555-effect0#progress#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.666667, 0.833333, }, 
		{{0.74, }, {0.75, }, }, 
		{6417, }, 
		{1, }, 
	}, 
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.833333, 1, }, 
		{{0.75, }, {0.74, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiLinearWipe_555-effect0#feather#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.666667, 0.833333, }, 
		{{0.03, }, {0, }, }, 
		{6417, }, 
		{1, }, 
	}, 
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.833333, 1, }, 
		{{0, }, {0.03, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiLayer_555-trs#position#vector'] =
{
	{
		{1, 0, 0.631523, 0.999999, }, 
		{0, 0.833333, }, 
		{{360, 690, 0, }, {360, 0, 0, }, {360, 575, 0, }, {360, 0, 0, }, }, 
		{6413, }, 
		{0, }, 
	}, 
	{
		{0.0001, 0, 0, 0.999997, }, 
		{0.833333, 1.666667, }, 
		{{360, 0, 0, }, {360, 690, 0, }, {360, 0, 0, }, {360, 575, 0, }, }, 
		{6413, }, 
		{0, }, 
	}, 
},
    ['LumiLinearWipe_556-effect0#progress#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.666667, 0.833333, }, 
		{{0.74, }, {0.75, }, }, 
		{6417, }, 
		{1, }, 
	}, 
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.833333, 1, }, 
		{{0.75, }, {0.74, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiLinearWipe_556-effect0#feather#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.666667, 0.833333, }, 
		{{0.03, }, {0, }, }, 
		{6417, }, 
		{1, }, 
	}, 
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.833333, 1, }, 
		{{0, }, {0.03, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiLayer_556-trs-blend#position#vector'] =
{
	{
		{1, 0, 0.631523, 0.999999, }, 
		{0, 0.833333, }, 
		{{360, 590, 0, }, {360, 1280, 0, }, {360, 705, 0, }, {360, 1280, 0, }, }, 
		{6413, }, 
		{0, }, 
	}, 
	{
		{0.0001, 0, 0, 0.999995, }, 
		{0.833333, 1.666667, }, 
		{{360, 1280, 0, }, {360, 590, 0, }, {360, 1280, 0, }, {360, 705, 0, }, }, 
		{6413, }, 
		{0, }, 
	}, 
},
    ['LumiLinearWipe_573-effect0#feather#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0, 1.666667, }, 
		{{0.03, }, {0, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiLinearWipe_561-effect0#feather#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0, 0.833333, }, 
		{{0.03, }, {0, }, }, 
		{6417, }, 
		{1, }, 
	}, 
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.833333, 1.666667, }, 
		{{0, }, {0.03, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiLayer_561-trs#position#vector'] =
{
	{
		{1, 0, 0.631523, 1, }, 
		{0, 0.833333, }, 
		{{360, 1310, 0, }, {360, 640, 0, }, {360, 1198.33333587646, 0, }, {360, 640, 0, }, }, 
		{6413, }, 
		{0, }, 
	}, 
	{
		{0.0001, 0, 0, 1, }, 
		{0.833333, 1.666667, }, 
		{{360, 640, 0, }, {360, 1310, 0, }, {360, 640, 0, }, {360, 1198.33333587646, 0, }, }, 
		{6413, }, 
		{0, }, 
	}, 
},
    ['LumiLayer_573-trs-blend#position#vector'] =
{
	{
		{1, 0, 0.631523, 1, }, 
		{0, 0.833333, }, 
		{{360, -30, 0, }, {360, 640, 0, }, {360, 81.6666641235352, 0, }, {360, 640, 0, }, }, 
		{6413, }, 
		{0, }, 
	}, 
	{
		{0.0001, 0, 0, 1, }, 
		{0.833333, 1.666667, }, 
		{{360, 640, 0, }, {360, -30, 0, }, {360, 640, 0, }, {360, 81.6666641235352, 0, }, }, 
		{6413, }, 
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
