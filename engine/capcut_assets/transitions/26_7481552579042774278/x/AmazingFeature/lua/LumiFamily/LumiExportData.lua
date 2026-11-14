local data = {}

local ae_compDurations = {0, 2}
data.ae_compDurations = ae_compDurations

local ae_effectType = 'transition'
data.ae_effectType = ae_effectType

local ae_transitionInputIndex = {
    {'LumiSShake_50-effect0', 'InputTex', 0},
    {'LumiSShake_51-effect0', 'InputTex', 1},
}
data.ae_transitionInputIndex = ae_transitionInputIndex

local ae_durations = {
    ['LumiSShake_50-effect0'] = {
        ['nodeDuration'] = {{0, 2}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 2}, },
        },
    },
    ['LumiSShake_51-effect0'] = {
        ['nodeDuration'] = {{1, 2}, },
        ['texDuration'] = {
            ['InputTex'] = {{1, 2}, },
        },
    },
    ['LumiLayer_51-blend'] = {
        ['nodeDuration'] = {{0, 2}, },
        ['texDuration'] = {
            ['InputTex'] = {{1, 2}, },
            ['baseTex'] = {{0, 2}, },
        },
    },
    ['LumiSaturation_54-effect0'] = {
        ['nodeDuration'] = {{0, 2}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 2}, },
        },
    },
    ['LumiDeepGlow_54-effect1'] = {
        ['nodeDuration'] = {{0, 2}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 2}, },
        },
    },
    ['LumiLayer_54-blend'] = {
        ['nodeDuration'] = {{0, 2}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 2}, },
            ['baseTex'] = {{0, 2}, },
        },
    },
    ['Lumi3DShape_61-effect0'] = {
        ['nodeDuration'] = {{0, 2}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 2}, },
        },
    },
    ['LumiGaussianBlur_61-effect1'] = {
        ['nodeDuration'] = {{0, 2}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 2}, },
        },
    },
    ['LumiLayer_61-trs-blend'] = {
        ['nodeDuration'] = {{0, 2}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 2}, },
            ['baseTex'] = {{0, 2}, },
        },
    },
}
data.ae_durations = ae_durations

local ae_attribute = {
    ['LumiSShake_50-effect0'] = {
        ['ampRatio'] = 0.6,
        ['frqRatio'] = 3,
        ['phase0'] = 0,
        ['scale0'] = 1,
        ['blurEnabled'] = true,
        ['blurIntensity'] = 1,
        ['blurQuality'] = 0,
        ['seed'] = 0,
        ['xFill'] = 2,
        ['yFill'] = 2,
        ['xAmpR'] = 30,
        ['xFrqR'] = 1,
        ['xAmp'] = 0,
        ['xFrq'] = 0.5,
        ['xPhase'] = 0,
        ['yAmpR'] = 30,
        ['yFrqR'] = 1,
        ['yAmp'] = 0,
        ['yFrq'] = 0.5,
        ['yPhase'] = 0,
        ['zAmpR'] = 10,
        ['zFrqR'] = 0.5,
        ['zAmp'] = 50,
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
    },
    ['LumiSShake_51-effect0'] = {
        ['ampRatio'] = 0.6,
        ['frqRatio'] = 3,
        ['phase0'] = 0,
        ['scale0'] = 1,
        ['blurEnabled'] = true,
        ['blurIntensity'] = 1,
        ['blurQuality'] = 0,
        ['seed'] = 0,
        ['xFill'] = 2,
        ['yFill'] = 2,
        ['xAmpR'] = 30,
        ['xFrqR'] = 1,
        ['xAmp'] = 0,
        ['xFrq'] = 0.5,
        ['xPhase'] = 0,
        ['yAmpR'] = 30,
        ['yFrqR'] = 1,
        ['yAmp'] = 0,
        ['yFrq'] = 0.5,
        ['yPhase'] = 0,
        ['zAmpR'] = 10,
        ['zFrqR'] = 0.5,
        ['zAmp'] = 50,
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
    },
    ['LumiLayer_51-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Precomp',
        ['blendMode'] = 0,
    },
    ['LumiSaturation_54-effect0'] = {
        ['saturationIntensity'] = -1,
    },
    ['LumiDeepGlow_54-effect1'] = {
        ['radius'] = 120,
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
    },
    ['LumiLayer_54-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 0,
    },
    ['Lumi3DShape_61-effect0'] = {
        ['fov'] = 34,
        ['meshType'] = 0,
        ['meshSize_x'] = 6,
        ['meshSize_y'] = 0.80999999977648,
        ['meshSize_z'] = 2,
        ['meshResX'] = 30,
        ['meshResY'] = 30,
        ['meshResZ'] = 30,
        ['reverseUV'] = false,
        ['cullBack'] = false,
        ['translucency'] = false,
        ['twoSide'] = false,
        ['Position_x'] = 0,
        ['Position_y'] = -6,
        ['Position_z'] = -6,
        ['Scale_x'] = 1,
        ['Scale_y'] = 1,
        ['Scale_z'] = 1,
        ['Rotate_x'] = 0,
        ['Rotate_y'] = 0,
        ['Rotate_z'] = 13,
        ['texFillMode'] = 2,
        ['uvScaleX'] = 1,
        ['uvScaleY'] = 1,
        ['uvWrapMode'] = 2,
        ['enableMask'] = false,
        ['maskChannel'] = 3,
    },
    ['LumiGaussianBlur_61-effect1'] = {
        ['blurIntensity'] = 20,
        ['quality'] = 0.5,
        ['spaceDither'] = 0,
        ['horizontalStrength'] = 1,
        ['verticalStrength'] = 1,
        ['blurDirection'] = 0,
        ['borderType'] = 0,
        ['blurAlpha'] = true,
        ['inverseGammaCorrection'] = true,
    },
    ['LumiLayer_61-trs-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = true,
        ['layerType'] = 'Solid',
        ['anchorPoint'] = Amaz.Vector3f(256, 256, 0),
        ['position'] = Amaz.Vector3f(256, 256, 0),
        ['scale'] = Amaz.Vector3f(100, 100, 100),
        ['orientation'] = Amaz.Vector3f(0, 0, 0),
        ['xRotation'] = 0,
        ['yRotation'] = 0,
        ['rotation'] = 0,
        ['opacity'] = 84,
        ['active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(512, 512),
        ['layerSize'] = Amaz.Vector2f(512, 512),
        ['mirrorEdge'] = false,
        ['blendMode'] = 0,
    },
}
data.ae_attribute = ae_attribute

local ae_keyframes = {
    ['LumiDeepGlow_54-effect1#exposure#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.72, 1, }, 
		{{0, }, {1, }, }, 
		{6417, }, 
		{1, }, 
	}, 
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{1, 1.28, }, 
		{{1, }, {0.37, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['Lumi3DShape_61-effect0#Position_y#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.72, 1.28, }, 
		{{-6, }, {5, }, }, 
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
