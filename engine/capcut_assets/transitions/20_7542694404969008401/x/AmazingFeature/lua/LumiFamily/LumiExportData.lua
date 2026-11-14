local data = {}

local ae_compDurations = {0, 1}
data.ae_compDurations = ae_compDurations

local ae_effectType = 'transition'
data.ae_effectType = ae_effectType

local ae_transitionInputIndex = {
    {'LumiLayer_45-trs', 'InputTex', 1},
    {'LumiLayer_46-trs-blend', 'InputTex', 0},
    {'LumiLayer_273-trs', 'InputTex', 1},
    {'LumiLayer_274-trs-blend', 'InputTex', 0},
}
data.ae_transitionInputIndex = ae_transitionInputIndex

local ae_durations = {
    ['LumiLayer_45-trs'] = {
        ['nodeDuration'] = {{0, 3}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 3}, },
        },
    },
    ['LumiLayer_46-trs-blend'] = {
        ['nodeDuration'] = {{0, 3}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 3}, },
            ['baseTex'] = {{0, 3}, },
        },
    },
    ['LumiBrightness_278-effect0'] = {
        ['nodeDuration'] = {{0, 3}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 3}, },
        },
    },
    ['LumiSaturation_278-effect1'] = {
        ['nodeDuration'] = {{0, 3}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 3}, },
        },
    },
    ['LumiLayer_278-blend'] = {
        ['nodeDuration'] = {{0, 3}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 3}, },
            ['baseTex'] = {{0, 3}, },
        },
    },
    ['LumiLayer_273-trs'] = {
        ['nodeDuration'] = {{0, 3}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 3}, },
        },
    },
    ['LumiLayer_274-trs-blend'] = {
        ['nodeDuration'] = {{0, 3}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 3}, },
            ['baseTex'] = {{0, 3}, },
        },
    },
    ['LumiCube_57-effect0'] = {
        ['nodeDuration'] = {{0, 3}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 3}, },
            ['imageFFront'] = {{0, 3}, },
            ['imageFRight'] = {{0, 3}, },
        },
    },
}
data.ae_durations = ae_durations

local ae_attribute = {
    ['LumiLayer_45-trs'] = {
        ['hasBlend'] = false,
        ['hasMatte'] = false,
        ['hasTransform'] = true,
        ['layerType'] = 'Precomp',
        ['anchorPoint'] = Amaz.Vector3f(500, 500, 0),
        ['position'] = Amaz.Vector3f(550, 50, 0),
        ['scale'] = Amaz.Vector3f(100, 100, 100),
        ['orientation'] = Amaz.Vector3f(0, 0, 0),
        ['xRotation'] = 0,
        ['yRotation'] = 0,
        ['rotation'] = 0,
        ['opacity'] = 100,
        ['active_cam_fovx'] = 39.6,
        ['p0_anchorPoint'] = Amaz.Vector3f(50, 50, 0),
        ['p0_position'] = Amaz.Vector3f(75.1559471588654, 500, 0),
        ['p0_scale'] = Amaz.Vector3f(100, 100, 100),
        ['p0_orientation'] = Amaz.Vector3f(0, 0, 0),
        ['p0_xRotation'] = 0,
        ['p0_yRotation'] = 0,
        ['p0_rotation'] = 0,
        ['p0_opacity'] = 100,
        ['p0_active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(1000, 1000),
        ['layerSize'] = Amaz.Vector2f(1000, 1000),
        ['mirrorEdge'] = false,
    },
    ['LumiLayer_46-trs-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = true,
        ['layerType'] = 'Precomp',
        ['anchorPoint'] = Amaz.Vector3f(500, 500, 0),
        ['position'] = Amaz.Vector3f(-450, 50, 0),
        ['scale'] = Amaz.Vector3f(100, 100, 100),
        ['orientation'] = Amaz.Vector3f(0, 0, 0),
        ['xRotation'] = 0,
        ['yRotation'] = 0,
        ['rotation'] = 0,
        ['opacity'] = 100,
        ['active_cam_fovx'] = 39.6,
        ['p0_anchorPoint'] = Amaz.Vector3f(50, 50, 0),
        ['p0_position'] = Amaz.Vector3f(75.1559471588654, 500, 0),
        ['p0_scale'] = Amaz.Vector3f(100, 100, 100),
        ['p0_orientation'] = Amaz.Vector3f(0, 0, 0),
        ['p0_xRotation'] = 0,
        ['p0_yRotation'] = 0,
        ['p0_rotation'] = 0,
        ['p0_opacity'] = 100,
        ['p0_active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(1000, 1000),
        ['layerSize'] = Amaz.Vector2f(1000, 1000),
        ['mirrorEdge'] = false,
        ['blendMode'] = 0,
    },
    ['LumiBrightness_278-effect0'] = {
        ['brightnessIntensity'] = -0.98305760085349,
        ['AEDesignSize'] = Amaz.Vector2f(1000, 1000),
    },
    ['LumiSaturation_278-effect1'] = {
        ['saturationIntensity'] = -0.49152880042675,
        ['AEDesignSize'] = Amaz.Vector2f(1000, 1000),
    },
    ['LumiLayer_278-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Adjustment',
        ['blendMode'] = 0,
    },
    ['LumiLayer_273-trs'] = {
        ['hasBlend'] = false,
        ['hasMatte'] = false,
        ['hasTransform'] = true,
        ['layerType'] = 'Precomp',
        ['anchorPoint'] = Amaz.Vector3f(500, 500, 0),
        ['position'] = Amaz.Vector3f(550, 50, 0),
        ['scale'] = Amaz.Vector3f(100, 100, 100),
        ['orientation'] = Amaz.Vector3f(0, 0, 0),
        ['xRotation'] = 0,
        ['yRotation'] = 0,
        ['rotation'] = 0,
        ['opacity'] = 100,
        ['active_cam_fovx'] = 39.6,
        ['p0_anchorPoint'] = Amaz.Vector3f(50, 50, 0),
        ['p0_position'] = Amaz.Vector3f(75.1559471588654, 500, 0),
        ['p0_scale'] = Amaz.Vector3f(100, 100, 100),
        ['p0_orientation'] = Amaz.Vector3f(0, 0, 0),
        ['p0_xRotation'] = 0,
        ['p0_yRotation'] = 0,
        ['p0_rotation'] = 0,
        ['p0_opacity'] = 100,
        ['p0_active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(1000, 1000),
        ['layerSize'] = Amaz.Vector2f(1000, 1000),
        ['mirrorEdge'] = false,
    },
    ['LumiLayer_274-trs-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = true,
        ['layerType'] = 'Precomp',
        ['anchorPoint'] = Amaz.Vector3f(500, 500, 0),
        ['position'] = Amaz.Vector3f(-450, 50, 0),
        ['scale'] = Amaz.Vector3f(100, 100, 100),
        ['orientation'] = Amaz.Vector3f(0, 0, 0),
        ['xRotation'] = 0,
        ['yRotation'] = 0,
        ['rotation'] = 0,
        ['opacity'] = 100,
        ['active_cam_fovx'] = 39.6,
        ['p0_anchorPoint'] = Amaz.Vector3f(50, 50, 0),
        ['p0_position'] = Amaz.Vector3f(75.1559471588654, 500, 0),
        ['p0_scale'] = Amaz.Vector3f(100, 100, 100),
        ['p0_orientation'] = Amaz.Vector3f(0, 0, 0),
        ['p0_xRotation'] = 0,
        ['p0_yRotation'] = 0,
        ['p0_rotation'] = 0,
        ['p0_opacity'] = 100,
        ['p0_active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(1000, 1000),
        ['layerSize'] = Amaz.Vector2f(1000, 1000),
        ['mirrorEdge'] = false,
        ['blendMode'] = 0,
    },
    ['LumiCube_57-effect0'] = {
        ['twoSide'] = false,
        ['cullBack'] = false,
        ['translucency'] = false,
        ['separateSurface'] = true,
        ['multiRatio'] = 0,
        ['fov'] = 60,
        ['position'] = Amaz.Vector3f(0.5, 0.5, 0),
        ['scale'] = Amaz.Vector3f(0.08081929139602, 0.91918070860398, 0.08081929139602),
        ['rotateX'] = 0,
        ['rotateY'] = 76.6506380275343,
        ['rotateZ'] = 0,
        ['meshSize'] = Amaz.Vector3f(1, 0, 1),
        ['meshRound'] = 0,
        ['meshCount'] = 2,
        ['fillModeFDefault'] = 0,
        ['wrapModeFDefault'] = 2,
        ['uvCenterFDefault'] = Amaz.Vector2f(0, 1),
        ['uvScaleFDefault'] = Amaz.Vector2f(0.1, 0.9),
        ['uvRotateFDefault'] = 0,
        ['fillModeBDefault'] = 0,
        ['wrapModeBDefault'] = 2,
        ['uvCenterBDefault'] = Amaz.Vector2f(0, 1),
        ['uvScaleBDefault'] = Amaz.Vector2f(0.1, 0.9),
        ['uvRotateBDefault'] = 0,
        ['translateFront'] = Amaz.Vector3f(0, 1, 0),
        ['scaleFront'] = Amaz.Vector3f(0.1, 0.9, 0.1),
        ['rotateFront'] = Amaz.Vector3f(0, 1, 0),
        ['fillModeFFront'] = 0,
        ['wrapModeFFront'] = 2,
        ['uvCenterFFront'] = Amaz.Vector2f(0, 1),
        ['uvScaleFFront'] = Amaz.Vector2f(0.1, 0.9),
        ['uvRotateFFront'] = 0,
        ['fillModeBFront'] = 0,
        ['wrapModeBFront'] = 2,
        ['uvCenterBFront'] = Amaz.Vector2f(0, 1),
        ['uvScaleBFront'] = Amaz.Vector2f(0.1, 0.9),
        ['uvRotateBFront'] = 0,
        ['translateBack'] = Amaz.Vector3f(0, 1, 0),
        ['scaleBack'] = Amaz.Vector3f(0.1, 0.9, 0.1),
        ['rotateBack'] = Amaz.Vector3f(0, 1, 0),
        ['fillModeFBack'] = 0,
        ['wrapModeFBack'] = 2,
        ['uvCenterFBack'] = Amaz.Vector2f(0, 1),
        ['uvScaleFBack'] = Amaz.Vector2f(0.1, 0.9),
        ['uvRotateFBack'] = 0,
        ['fillModeBBack'] = 0,
        ['wrapModeBBack'] = 2,
        ['uvCenterBBack'] = Amaz.Vector2f(0, 1),
        ['uvScaleBBack'] = Amaz.Vector2f(0.1, 0.9),
        ['uvRotateBBack'] = 0,
        ['translateTop'] = Amaz.Vector3f(0, 1, 0),
        ['scaleTop'] = Amaz.Vector3f(0.1, 0.9, 0.1),
        ['rotateTop'] = Amaz.Vector3f(0, 1, 0),
        ['fillModeFTop'] = 0,
        ['wrapModeFTop'] = 2,
        ['uvCenterFTop'] = Amaz.Vector2f(0, 1),
        ['uvScaleFTop'] = Amaz.Vector2f(0.1, 0.9),
        ['uvRotateFTop'] = 0,
        ['fillModeBTop'] = 0,
        ['wrapModeBTop'] = 2,
        ['uvCenterBTop'] = Amaz.Vector2f(0, 1),
        ['uvScaleBTop'] = Amaz.Vector2f(0.1, 0.9),
        ['uvRotateBTop'] = 0,
        ['translateBottom'] = Amaz.Vector3f(0, 1, 0),
        ['scaleBottom'] = Amaz.Vector3f(0.1, 0.9, 0.1),
        ['rotateBottom'] = Amaz.Vector3f(0, 1, 0),
        ['fillModeFBottom'] = 0,
        ['wrapModeFBottom'] = 2,
        ['uvCenterFBottom'] = Amaz.Vector2f(0, 1),
        ['uvScaleFBottom'] = Amaz.Vector2f(0.1, 0.9),
        ['uvRotateFBottom'] = 0,
        ['fillModeBBottom'] = 0,
        ['wrapModeBBottom'] = 2,
        ['uvCenterBBottom'] = Amaz.Vector2f(0, 1),
        ['uvScaleBBottom'] = Amaz.Vector2f(0.1, 0.9),
        ['uvRotateBBottom'] = 0,
        ['translateLeft'] = Amaz.Vector3f(0, 1, 0),
        ['scaleLeft'] = Amaz.Vector3f(0.1, 0.9, 0.1),
        ['rotateLeft'] = Amaz.Vector3f(0, 1, 0),
        ['fillModeFLeft'] = 0,
        ['wrapModeFLeft'] = 2,
        ['uvCenterFLeft'] = Amaz.Vector2f(0, 1),
        ['uvScaleFLeft'] = Amaz.Vector2f(0.1, 0.9),
        ['uvRotateFLeft'] = 0,
        ['fillModeBLeft'] = 0,
        ['wrapModeBLeft'] = 2,
        ['uvCenterBLeft'] = Amaz.Vector2f(0, 1),
        ['uvScaleBLeft'] = Amaz.Vector2f(0.1, 0.9),
        ['uvRotateBLeft'] = 0,
        ['translateRight'] = Amaz.Vector3f(0, 1, 0),
        ['scaleRight'] = Amaz.Vector3f(0.1, 0.9, 0.1),
        ['rotateRight'] = Amaz.Vector3f(0, 1, 0),
        ['fillModeFRight'] = 0,
        ['wrapModeFRight'] = 2,
        ['uvCenterFRight'] = Amaz.Vector2f(0, 1),
        ['uvScaleFRight'] = Amaz.Vector2f(0.1, 0.9),
        ['uvRotateFRight'] = 0,
        ['fillModeBRight'] = 0,
        ['wrapModeBRight'] = 2,
        ['uvCenterBRight'] = Amaz.Vector2f(0, 1),
        ['uvScaleBRight'] = Amaz.Vector2f(0.1, 0.9),
        ['uvRotateBRight'] = 0,
        ['maskChannel'] = 3,
        ['AEDesignSize'] = Amaz.Vector2f(1000, 1000),
    },
}
data.ae_attribute = ae_attribute

local ae_keyframes = {
    ['LumiLayer_45-trs#p0_position#vector'] =
{
	{
		{0.77, 0, 0.63, 1, }, 
		{0, 0.666667, }, 
		{{1000, 500, 0, }, {0, 500, 0, }, {1000, 500, 0, }, {0, 500, 0, }, }, 
		{6413, }, 
		{0, }, 
	}, 
},
    ['LumiLayer_46-trs-blend#p0_position#vector'] =
{
	{
		{0.77, 0, 0.63, 1, }, 
		{0, 0.666667, }, 
		{{1000, 500, 0, }, {0, 500, 0, }, {1000, 500, 0, }, {0, 500, 0, }, }, 
		{6413, }, 
		{0, }, 
	}, 
},
    ['LumiBrightness_278-effect0#brightnessIntensity#number'] =
{
	{
		{0.18, 0, 0.31, 1, }, 
		{0, 0.666667, }, 
		{{0, }, {-1, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiSaturation_278-effect1#saturationIntensity#number'] =
{
	{
		{0.18, 0, 0.31, 1, }, 
		{0, 0.666667, }, 
		{{0, }, {-0.5, }, }, 
		{6417, }, 
		{0, }, 
	}, 
},
    ['LumiLayer_273-trs#p0_position#vector'] =
{
	{
		{0.77, 0, 0.63, 1, }, 
		{0, 0.666667, }, 
		{{1000, 500, 0, }, {0, 500, 0, }, {1000, 500, 0, }, {0, 500, 0, }, }, 
		{6413, }, 
		{0, }, 
	}, 
},
    ['LumiLayer_274-trs-blend#p0_position#vector'] =
{
	{
		{0.77, 0, 0.63, 1, }, 
		{0, 0.666667, }, 
		{{1000, 500, 0, }, {0, 500, 0, }, {1000, 500, 0, }, {0, 500, 0, }, }, 
		{6413, }, 
		{0, }, 
	}, 
},
    ['LumiCube_57-effect0#scale#vector'] =
{
	{
		{0.15, 0, 0.09, 1, }, 
		{0, 0.8, }, 
		{{0.1, 0.9, 0.1, }, {0.08, 0.92, 0.08, }, {0.1, 0.9, 0.1, }, {0.08, 0.92, 0.08, }, }, 
		{6413, }, 
		{0, }, 
	}, 
	{
		{0.15, 0, 0.63, 1, }, 
		{0.8, 1, }, 
		{{0.08, 0.92, 0.08, }, {0.1, 0.9, 0.1, }, {0.08, 0.92, 0.08, }, {0.1, 0.9, 0.1, }, }, 
		{6413, }, 
		{0, }, 
	}, 
},
    ['LumiCube_57-effect0#rotateY#number'] =
{
	{
		{0.52, 0, 0.49, 1, }, 
		{0, 0.8, }, 
		{{0, }, {90, }, }, 
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
