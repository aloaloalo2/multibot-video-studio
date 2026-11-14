--write by editor  EffectSDK:17.1.0 EngineVersion:17.1.0 EditorBuildTime:Aug_13_2024_15_04_02
--sliderVersion: 20230517  Lua generation date: Mon Aug 18 11:08:10 2025


local exports = exports or {}
local ImageBusinessSlider = ImageBusinessSlider or {}
ImageBusinessSlider.__index = ImageBusinessSlider


function ImageBusinessSlider.new(construct, ...)
    local self = setmetatable({}, ImageBusinessSlider)
    if construct and ImageBusinessSlider.constructor then
        ImageBusinessSlider.constructor(self, ...)
    end
    return self
end


local function remap(x, a, b)
    return x * (b - a) + a
end


function ImageBusinessSlider:onStart(sys)
end


function ImageBusinessSlider:onEvent(sys,event)
end


exports.ImageBusinessSlider = ImageBusinessSlider
return exports