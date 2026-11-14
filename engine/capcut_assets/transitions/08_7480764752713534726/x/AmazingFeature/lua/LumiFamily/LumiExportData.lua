local data = {}

local ae_compDurations = {0, 1}
data.ae_compDurations = ae_compDurations

local ae_effectType = 'transition'
data.ae_effectType = ae_effectType

local ae_transitionInputIndex = {
    {'LumiLayer_97-trs-blend', 'InputTex', 1},
    {'LumiLayer_199-trs-blend', 'InputTex', 1},
    {'LumiLayer_200-trs-blend', 'InputTex', 1},
    {'LumiLayer_201-trs-blend', 'InputTex', 1},
    {'LumiLayer_202-trs-blend', 'InputTex', 1},
    {'LumiLayer_203-blend', 'InputTex', 1},
}
data.ae_transitionInputIndex = ae_transitionInputIndex

local ae_durations = {
    ['LumiLayer_97-trs-blend'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0, 0.16666666666667}, },
            ['baseTex'] = {{0, 1}, },
        },
    },
    ['LumiLayer_199-trs-blend'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.16666666666667, 0.33333333333333}, },
            ['baseTex'] = {{0, 1}, },
        },
    },
    ['LumiLayer_200-trs-blend'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.33333333333333, 0.5}, },
            ['baseTex'] = {{0, 1}, },
        },
    },
    ['LumiLayer_201-trs-blend'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.5, 0.66666666666667}, },
            ['baseTex'] = {{0, 1}, },
        },
    },
    ['LumiLayer_202-trs-blend'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.66666666666667, 0.83333333333333}, },
            ['baseTex'] = {{0, 1}, },
        },
    },
    ['LumiLayer_203-blend'] = {
        ['nodeDuration'] = {{0, 1}, },
        ['texDuration'] = {
            ['InputTex'] = {{0.83333333333333, 1}, },
            ['baseTex'] = {{0, 1}, },
        },
    },
}
data.ae_durations = ae_durations

local ae_attribute = {
    ['LumiLayer_97-trs-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = true,
        ['layerType'] = 'Precomp',
        ['anchorPoint'] = Amaz.Vector3f(640, 360, 0),
        ['position'] = Amaz.Vector3f(640, 360, 0),
        ['scale'] = Amaz.Vector3f(0, 0, 100),
        ['orientation'] = Amaz.Vector3f(0, 0, 0),
        ['xRotation'] = 0,
        ['yRotation'] = 0,
        ['rotation'] = 0,
        ['opacity'] = 100,
        ['active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(1280, 720),
        ['layerSize'] = Amaz.Vector2f(1280, 720),
        ['mirrorEdge'] = false,
        ['blendMode'] = 0,
    },
    ['LumiLayer_199-trs-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = true,
        ['layerType'] = 'Precomp',
        ['anchorPoint'] = Amaz.Vector3f(640, 360, 0),
        ['position'] = Amaz.Vector3f(640, 360, 0),
        ['scale'] = Amaz.Vector3f(20, 20, 100),
        ['orientation'] = Amaz.Vector3f(0, 0, 0),
        ['xRotation'] = 0,
        ['yRotation'] = 0,
        ['rotation'] = 0,
        ['opacity'] = 100,
        ['active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(1280, 720),
        ['layerSize'] = Amaz.Vector2f(1280, 720),
        ['mirrorEdge'] = false,
        ['blendMode'] = 0,
    },
    ['LumiLayer_200-trs-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = true,
        ['layerType'] = 'Precomp',
        ['anchorPoint'] = Amaz.Vector3f(640, 360, 0),
        ['position'] = Amaz.Vector3f(640, 360, 0),
        ['scale'] = Amaz.Vector3f(40, 40, 100),
        ['orientation'] = Amaz.Vector3f(0, 0, 0),
        ['xRotation'] = 0,
        ['yRotation'] = 0,
        ['rotation'] = 0,
        ['opacity'] = 100,
        ['active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(1280, 720),
        ['layerSize'] = Amaz.Vector2f(1280, 720),
        ['mirrorEdge'] = false,
        ['blendMode'] = 0,
    },
    ['LumiLayer_201-trs-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = true,
        ['layerType'] = 'Precomp',
        ['anchorPoint'] = Amaz.Vector3f(640, 360, 0),
        ['position'] = Amaz.Vector3f(640, 360, 0),
        ['scale'] = Amaz.Vector3f(60, 60, 100),
        ['orientation'] = Amaz.Vector3f(0, 0, 0),
        ['xRotation'] = 0,
        ['yRotation'] = 0,
        ['rotation'] = 0,
        ['opacity'] = 100,
        ['active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(1280, 720),
        ['layerSize'] = Amaz.Vector2f(1280, 720),
        ['mirrorEdge'] = false,
        ['blendMode'] = 0,
    },
    ['LumiLayer_202-trs-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = true,
        ['layerType'] = 'Precomp',
        ['anchorPoint'] = Amaz.Vector3f(640, 360, 0),
        ['position'] = Amaz.Vector3f(640, 360, 0),
        ['scale'] = Amaz.Vector3f(80, 80, 100),
        ['orientation'] = Amaz.Vector3f(0, 0, 0),
        ['xRotation'] = 0,
        ['yRotation'] = 0,
        ['rotation'] = 0,
        ['opacity'] = 100,
        ['active_cam_fovx'] = 39.6,
        ['compositeSize'] = Amaz.Vector2f(1280, 720),
        ['layerSize'] = Amaz.Vector2f(1280, 720),
        ['mirrorEdge'] = false,
        ['blendMode'] = 0,
    },
    ['LumiLayer_203-blend'] = {
        ['hasBlend'] = true,
        ['hasMatte'] = false,
        ['hasTransform'] = false,
        ['layerType'] = 'Precomp',
        ['blendMode'] = 0,
    },
}
data.ae_attribute = ae_attribute

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
