local data = {}

local ae_compDurations = {0, 1}
data.ae_compDurations = ae_compDurations

local ae_effectType = 'transition'
data.ae_effectType = ae_effectType

local ae_transitionInputIndex = {
    {'LumiExtractFrame_11902-effect0', 'InputTex', 0},
    {'LumiLayer_11901-trs', 'InputTex', 0},
    {'LumiRoundCorner_9404-effect0', 'InputTex', 1},
}
data.ae_transitionInputIndex = ae_transitionInputIndex

local ae_durations = {
    ['LumiExtractFrame_11902-effect0'] = {
        ['nodeDuration'] = {{0, 0.96666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.96666666666667}, },
        },
    },
    ['LumiSaturation_11902-effect1'] = {
        ['nodeDuration'] = {{0, 0.96666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.96666666666667}, },
        },
    },
    ['LumiContrast_11902-effect2'] = {
        ['nodeDuration'] = {{0, 0.96666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.96666666666667}, },
        },
    },
    ['LumiVignette_11902-effect3'] = {
        ['nodeDuration'] = {{0, 0.96666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.96666666666667}, },
        },
    },
    ['LumiRoundCorner_11903-effect0'] = {
        ['nodeDuration'] = {{0, 0.96666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.96666666666667}, },
        },
    },
    ['LumiLayer_11901-trs'] = {
        ['nodeDuration'] = {{0, 0.96666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.96666666666667}, },
        },
    },
    ['LumiLayer_11902-matte-blend'] = {
        ['nodeDuration'] = {{0, 0.96666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.96666666666667}, },
            ['baseTex'] = {{0, 0.96666666666667}, },
            ['maskTex'] = {{0, 0.96666666666667}, },
        },
    },
    ['LumiMotionBlur3D_9402-effect0'] = {
        ['nodeDuration'] = {{0, 0.96666666666667}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.96666666666667}, },
        },
    },
    ['LumiRoundCorner_9404-effect0'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1}, },
        },
    },
    ['LumiBrightness_9404-effect1'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1}, },
        },
    },
    ['LumiLayer_9404-trs'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1}, },
        },
    },
    ['LumiGaussianBlur_9403-effect0'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1}, },
        },
    },
    ['LumiLayer_9403-blend'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1}, },
            ['baseTex'] = {{0, 1}, },
        },
    },
    ['LumiLayer_9402-blend'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.96666666666667}, },
            ['baseTex'] = {{0, 1}, },
        },
    },
    ['LumiDeepGlow_9401-effect0'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1}, },
        },
    },
    ['LumiLayer_9401-blend'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 1}, },
            ['baseTex'] = {{0, 1}, },
        },
    },
}
data.ae_durations = ae_durations

local ae_attribute = {
    ['LumiExtractFrame_11902-effect0'] = {
        ['fps'] = 0.00999999977648,
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1440),
    },
    ['LumiSaturation_11902-effect1'] = {
        ['saturationIntensity'] = -0.4,
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1440),
    },
    ['LumiContrast_11902-effect2'] = {
        ['contrastIntensity'] = 1.3,
        ['pivot'] = 0.35,
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1440),
    },
    ['LumiVignette_11902-effect3'] = {
        ['color'] = Amaz.Color(0, 0, 0, 1),
        ['amount'] = 0.66,
        ['midpoint'] = 0.6,
        ['roundness'] = 0,
        ['feather'] = 0.72,
        ['highlight'] = 0,
        ['transparent'] = false,
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1440),
    },
    ['LumiRoundCorner_11903-effect0'] = {
        ['radius'] = 9,
        ['fade'] = 0,
        ['fadeType'] = 0,
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1440),
    },
    ['LumiLayer_11901-trs'] = {
        ['hasBlend'] = false,
        ['hasMatte'] = false,
        ['hasTransform'] = true,
        ['layerType'] = 'Precomp',
        ['anchorPoint'] = Amaz.Vector3f(540, 720, 0),
        ['position'] = Amaz.Vector3f(540, 644, 0),
        ['scale'] = Amaz.Vector3f(94, 82, 100),
        ['orientation'] = Amaz.Vector3f(0, 0, 0),
        ['xRotation'] = 0,
        ['yRotation'] = 0,
        ['rotation'] = 0,
        ['opacity'] = 100,
        ['active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(1080, 1440),
        ['layerSize'] = Amaz.Vector2f(1080, 1440),
        ['mirrorEdge'] = false,
    },
    ['LumiLayer_11902-matte-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = true,
        ['hasTransform'] = false,
        ['layerType'] = 'Precomp',
        ['matteMode'] = 0,
        ['blendMode'] = 0,
    },
    ['LumiMotionBlur3D_9402-effect0'] = {
        ['active_cam_fovx'] = 39.5999984741211,
        ['pivot'] = Amaz.Vector3f(0.5, 0.5, 0),
        ['ae_pre_pivot'] = Amaz.Vector3f(0.5, 0.5, 0),
        ['position'] = Amaz.Vector3f(0.3794586318288, 0.59982447980452, 1.56680759063315),
        ['ae_pre_position'] = Amaz.Vector3f(0.3794586318288, 0.59982447980452, 1.56680759063315),
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
        ['rotation_x'] = -37.929200773302,
        ['ae_pre_rotation_x'] = -37.929200773302,
        ['rotation_y'] = 18.9652187305375,
        ['ae_pre_rotation_y'] = 18.9652187305375,
        ['rotation_z'] = 5.18253346084408,
        ['ae_pre_rotation_z'] = 5.18253346084408,
        ['vIntensity'] = 0.66,
        ['vCenter'] = 0,
        ['samples'] = 10,
        ['alpha'] = 1,
        ['mirrorEdge'] = false,
        ['dither'] = 1,
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1440),
    },
    ['LumiRoundCorner_9404-effect0'] = {
        ['radius'] = 18.8848795956494,
        ['fade'] = 0,
        ['fadeType'] = 0,
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1440),
    },
    ['LumiBrightness_9404-effect1'] = {
        ['brightnessIntensity'] = -0.56654638786948,
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1440),
    },
    ['LumiLayer_9404-trs'] = {
        ['hasBlend'] = false,
        ['hasMatte'] = false,
        ['hasTransform'] = true,
        ['layerType'] = 'Precomp',
        ['anchorPoint'] = Amaz.Vector3f(540, 720, 0),
        ['position'] = Amaz.Vector3f(540, 775.587367387541, 326.98451404436),
        ['scale'] = Amaz.Vector3f(100, 100, 100),
        ['orientation'] = Amaz.Vector3f(18.8148285288351, 9.75475989782071, 4.8296928570837),
        ['xRotation'] = 0,
        ['yRotation'] = 0,
        ['rotation'] = 0,
        ['opacity'] = 100,
        ['active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(1080, 1440),
        ['layerSize'] = Amaz.Vector2f(1080, 1440),
        ['mirrorEdge'] = false,
    },
    ['LumiGaussianBlur_9403-effect0'] = {
        ['blurIntensity'] = 9,
        ['quality'] = 0.35452631578947,
        ['spaceDither'] = 0,
        ['horizontalStrength'] = 1,
        ['verticalStrength'] = 1,
        ['blurDirection'] = 0,
        ['borderType'] = 0,
        ['blurAlpha'] = true,
        ['inverseGammaCorrection'] = true,
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1440),
    },
    ['LumiLayer_9403-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 0,
    },
    ['LumiLayer_9402-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Precomp',
        ['blendMode'] = 0,
    },
    ['LumiDeepGlow_9401-effect0'] = {
        ['radius'] = 500,
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
        ['quality'] = 0.44315789473684,
        ['AEDesignSize'] = Amaz.Vector2f(1080, 1440),
    },
    ['LumiLayer_9401-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 0,
    },
}
data.ae_attribute = ae_attribute

local ae_keyframes = {
    ['LumiExtractFrame_11902-effect0#fps#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.266667, 0.3, }, 
		{{30, }, {0.01, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiSaturation_11902-effect1#saturationIntensity#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.266667, 0.433333, }, 
		{{0, }, {-0.4, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiContrast_11902-effect2#contrastIntensity#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.266667, 0.433333, }, 
		{{1, }, {1.3, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiVignette_11902-effect3#amount#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.266667, 0.433333, }, 
		{{0, }, {0.66, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiLayer_11901-trs#position#vector'] =
{
	{
		{0.001, 0, 0.5, 1, }, 
		{0.266667, 0.433333, }, 
		{{540, 720, 0, }, {540, 644, 0, }, {540, 720, 0, }, {540, 644, 0, }, }, 
		{6413, }, 
		{0, }, 
	}, 
},
    ['LumiLayer_11901-trs#scale#vector'] =
{
	{
		{0.001,0.001,0.001, 0,0,0.001, 0.5,0.5,0.5, 1,1,0.5, }, 
		{0.266667, 0.433333, }, 
		{{100, 100, 100, }, {94, 82, 100, }, }, 
		{6414, }, 
		{0, }, 
	}, 
},
    ['LumiMotionBlur3D_9402-effect0#ae_pre_position#vector'] =
{
	{
		{0.52, 0.074, 0.67, 0.963, }, 
		{0.03333333333333, 0.23333333333333, }, 
		{{0.5, 0.5, 0, }, {0.5, 0.5, -0.25, }, {0.5, 0.5, 0, }, {0.5, 0.5, -0.25, }, }, 
		{6413, }, 
		{0, }, 
	}, 
	{
		{0.34, 0, 0.5, 1, }, 
		{0.23333333333333, 0.50000033333333, }, 
		{{0.5, 0.5, -0.25, }, {0.5, 0.65277777777778, 1.59722222222222, }, {0.5, 0.5, -0.25, }, {0.5, 0.65277777777778, 1.59722222222222, }, }, 
		{6413, }, 
		{0, }, 
	}, 
	{
		{0.166667, 0.166667, 0.833333, 0.833333, }, 
		{0.50000033333333, 0.53333333333333, }, 
		{{0.5, 0.65277777777778, 1.59722222222222, }, {0.5, 0.65277777777778, 1.59722222222222, }, {0.5, 0.65277777777778, 1.59722222222222, }, {0.5, 0.65277777777778, 1.59722222222222, }, }, 
		{6413, }, 
		{1, }, 
	}, 
	{
		{1, 0, 0.999, 1, }, 
		{0.53333333333333, 0.96666633333333, }, 
		{{0.5, 0.65277777777778, 1.59722222222222, }, {-1.49814814814815, -0.225, 1.09305555555556, }, {0.5, 0.65277777777778, 1.59722222222222, }, {-1.49814814814815, -0.225, 1.09305555555556, }, }, 
		{6413, }, 
		{0, }, 
	}, 
	{
		{0.166667, 0.166667, 0.833333, 0.833333, }, 
		{0.96666633333333, 1.00000033333333, }, 
		{{-1.49814814814815, -0.225, 1.09305555555556, }, {-4.06759259259259, -1.31180555555556, 0.31875, }, {-1.49814814814815, -0.225, 1.09305555555556, }, {-4.06759259259259, -1.31180555555556, 0.31875, }, }, 
		{6413, }, 
		{1, }, 
	}, 
},
    ['LumiMotionBlur3D_9402-effect0#position#vector'] =
{
	{
		{0.52, 0.074, 0.67, 0.963, }, 
		{0, 0.2, }, 
		{{0.5, 0.5, 0, }, {0.5, 0.5, -0.25, }, {0.5, 0.5, 0, }, {0.5, 0.5, -0.25, }, }, 
		{6413, }, 
		{0, }, 
	}, 
	{
		{0.34, 0, 0.5, 1, }, 
		{0.2, 0.466667, }, 
		{{0.5, 0.5, -0.25, }, {0.5, 0.65277777777778, 1.59722222222222, }, {0.5, 0.5, -0.25, }, {0.5, 0.65277777777778, 1.59722222222222, }, }, 
		{6413, }, 
		{0, }, 
	}, 
	{
		{0.166667, 0.166667, 0.833333, 0.833333, }, 
		{0.466667, 0.5, }, 
		{{0.5, 0.65277777777778, 1.59722222222222, }, {0.5, 0.65277777777778, 1.59722222222222, }, {0.5, 0.65277777777778, 1.59722222222222, }, {0.5, 0.65277777777778, 1.59722222222222, }, }, 
		{6413, }, 
		{1, }, 
	}, 
	{
		{1, 0, 0.999, 1, }, 
		{0.5, 0.933333, }, 
		{{0.5, 0.65277777777778, 1.59722222222222, }, {-1.49814814814815, -0.225, 1.09305555555556, }, {0.5, 0.65277777777778, 1.59722222222222, }, {-1.49814814814815, -0.225, 1.09305555555556, }, }, 
		{6413, }, 
		{0, }, 
	}, 
	{
		{0.166667, 0.166667, 0.833333, 0.833333, }, 
		{0.933333, 0.966667, }, 
		{{-1.49814814814815, -0.225, 1.09305555555556, }, {-4.06759259259259, -1.31180555555556, 0.31875, }, {-1.49814814814815, -0.225, 1.09305555555556, }, {-4.06759259259259, -1.31180555555556, 0.31875, }, }, 
		{6413, }, 
		{1, }, 
	}, 
},
    ['LumiMotionBlur3D_9402-effect0#ae_pre_rotation_x#number'] =
{
	{
		{0.3, 0, 0.83, 1, }, 
		{0.03333333333333, 0.16666633333333, }, 
		{{0, }, {9, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.3, 0, 0.51, 1, }, 
		{0.16666633333333, 0.50000033333333, }, 
		{{9, }, {-32, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.50000033333333, 0.53333333333333, }, 
		{{-32, }, {-32, }, }, 
		{6417, }, 
		{1, }, 
	}, 
	{
		{0.6, 0, 0.999, 1, }, 
		{0.53333333333333, 0.96666633333333, }, 
		{{-32, }, {-75, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.96666633333333, 1.00000033333333, }, 
		{{-75, }, {-85, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiMotionBlur3D_9402-effect0#rotation_x#number'] =
{
	{
		{0.3, 0, 0.83, 1, }, 
		{0, 0.133333, }, 
		{{0, }, {9, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.3, 0, 0.51, 1, }, 
		{0.133333, 0.466667, }, 
		{{9, }, {-32, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.466667, 0.5, }, 
		{{-32, }, {-32, }, }, 
		{6417, }, 
		{1, }, 
	}, 
	{
		{0.6, 0, 0.999, 1, }, 
		{0.5, 0.933333, }, 
		{{-32, }, {-75, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.933333, 0.966667, }, 
		{{-75, }, {-85, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiMotionBlur3D_9402-effect0#ae_pre_rotation_y#number'] =
{
	{
		{0.57, 0, 0.86, 1, }, 
		{0.03333333333333, 0.50000033333333, }, 
		{{0, }, {18, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.50000033333333, 0.53333333333333, }, 
		{{18, }, {18, }, }, 
		{6417, }, 
		{1, }, 
	}, 
	{
		{0.6, 0, 0.999, 1, }, 
		{0.53333333333333, 0.96666633333333, }, 
		{{18, }, {25, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.96666633333333, 1.00000033333333, }, 
		{{25, }, {26.5, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiMotionBlur3D_9402-effect0#rotation_y#number'] =
{
	{
		{0.57, 0, 0.86, 1, }, 
		{0, 0.466667, }, 
		{{0, }, {18, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.466667, 0.5, }, 
		{{18, }, {18, }, }, 
		{6417, }, 
		{1, }, 
	}, 
	{
		{0.6, 0, 0.999, 1, }, 
		{0.5, 0.933333, }, 
		{{18, }, {25, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.933333, 0.966667, }, 
		{{25, }, {26.5, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiMotionBlur3D_9402-effect0#ae_pre_rotation_z#number'] =
{
	{
		{0.421101892, 0, 0.849206025, 1, }, 
		{0.03333333333333, 0.50000033333333, }, 
		{{0, }, {-10, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.166666667, 0, 0.833333333, 0, }, 
		{0.50000033333333, 0.53333333333333, }, 
		{{-10, }, {-10, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.47, 0, 0.999, 1, }, 
		{0.53333333333333, 0.96666633333333, }, 
		{{-10, }, {73.630464, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.96666633333333, 1.00000033333333, }, 
		{{73.630464, }, {85, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiMotionBlur3D_9402-effect0#rotation_z#number'] =
{
	{
		{0.421101892, 0, 0.849206025, 1, }, 
		{0, 0.466667, }, 
		{{0, }, {-10, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.166666667, 0, 0.833333333, 0, }, 
		{0.466667, 0.5, }, 
		{{-10, }, {-10, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.47, 0, 0.999, 1, }, 
		{0.5, 0.933333, }, 
		{{-10, }, {73.630464, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.933333, 0.966667, }, 
		{{73.630464, }, {85, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiRoundCorner_9404-effect0#radius#number'] =
{
	{
		{0.73, 0, 0.66, 1, }, 
		{0.466667, 0.966667, }, 
		{{22, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiBrightness_9404-effect1#brightnessIntensity#number'] =
{
	{
		{0.73, 0, 0.66, 1, }, 
		{0.466667, 0.966667, }, 
		{{-0.66, }, {0, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiLayer_9404-trs#position#vector'] =
{
	{
		{0.63, 0, 0.66, 1, }, 
		{0.466667, 0.966667, }, 
		{{540, 788, 400, }, {540, 720, 0, }, {540, 788, 400, }, {540, 720, 0, }, }, 
		{6413, }, 
		{0, }, 
	}, 
},
    ['LumiLayer_9404-trs#orientation#vector'] =
{
	{
		{0.81, 0, 0.66, 1, }, 
		{0.233333, 0.966667, }, 
		{{28, 15, 6, }, {0, 0, 0, }, }, 
		{6414, }, 
		{0, }, 
	}, 
},
    ['LumiGaussianBlur_9403-effect0#blurIntensity#number'] =
{
	{
		{0.166666667, 0.166666667, 0.833333333, 0.833333333, }, 
		{0.466667, 0.966667, }, 
		{{15, }, {0, }, }, 
		{6417, }, 
		{1, }, 
	}, 
},
    ['LumiDeepGlow_9401-effect0#exposure#number'] =
{
	{
		{0.001, 0, 0.8, 0.21, }, 
		{0.233333, 0.266667, }, 
		{{0, }, {1.3, }, }, 
		{6417, }, 
		{0, }, 
	}, 
	{
		{0.001, 0, 0.34, 0.65, }, 
		{0.266667, 0.5, }, 
		{{1.3, }, {0, }, }, 
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
