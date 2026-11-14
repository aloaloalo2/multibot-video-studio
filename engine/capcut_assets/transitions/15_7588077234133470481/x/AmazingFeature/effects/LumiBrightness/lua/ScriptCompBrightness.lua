---@class ScriptCompBrightness: ScriptComponent
---@field brightnessIntensity number [UI(Range={-1., 1.}, Drag)]
---@field InputTex Texture
---@field OutputTex Texture

local exports = exports or {}
local ScriptCompBrightness = ScriptCompBrightness or {}
ScriptCompBrightness.__index = ScriptCompBrightness

------------ util functions ------------
local function clamp(value, min, max)
    --[[
        Description: clamp value between [min, max]
    ]]
    return math.min(math.max(value, min), max)
end

------------ class functions for ScriptComponent ------------
function ScriptCompBrightness.new(construct, ...)
    local self = setmetatable({}, ScriptCompBrightness)

    if construct and ScriptCompBrightness.constructor then ScriptCompBrightness.constructor(self, ...) end
    -- user parameters
    self.brightnessIntensity = 0.

    -- other parameters
    self.MinIntensity = -1.
    self.MaxIntensity = 1.

    self.InputTex = nil
    self.OutputTex = nil
    return self
end

function ScriptCompBrightness:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value, _comp)
        if self[_key] ~= nil then
            self[_key] = _value
            if _comp and _comp.properties ~= nil then
                _comp.properties:set(_key, _value)
            end
        end
    end

    if key == "brightnessIntensity" then
        _setEffectAttr(key, value, comp)
    else
        _setEffectAttr(key, value, comp)
    end
end

function ScriptCompBrightness:onStart(comp)
    self.matBrightness = comp.entity:searchEntity("EntityBrightness"):getComponent("MeshRenderer").material
    self.camBrightness = comp.entity:searchEntity("CameraBrightness"):getComponent("Camera")
end

function ScriptCompBrightness:onUpdate(comp, deltaTime)
    -- prepare parameters
    self.brightnessIntensity = clamp(self.brightnessIntensity, self.MinIntensity, self.MaxIntensity)

    local intensity = self.brightnessIntensity
    if self.brightnessIntensity > 0 and self.brightnessIntensity <= 0.7 then
        intensity = 0.3 * self.brightnessIntensity
    elseif self.brightnessIntensity > 0.7 and self.brightnessIntensity <= 1.0 then
        intensity = 0.6333 * self.brightnessIntensity - 0.2333
    end

    -- set InputTex and OutputTex
    self.matBrightness:setTex("u_inputTexture", self.InputTex)
    self.camBrightness.renderTexture = self.OutputTex

    -- set material parameters
    self.matBrightness:setFloat("u_intensity", intensity)
end

exports.ScriptCompBrightness = ScriptCompBrightness
return exports
