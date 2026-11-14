---@class ScriptCompSaturation: ScriptComponent
---@field saturationIntensity number [UI(Range={-1., 1.}, Drag)]
---@field InputTex Texture
---@field OutputTex Texture

local exports = exports or {}
local ScriptCompSaturation = ScriptCompSaturation or {}
ScriptCompSaturation.__index = ScriptCompSaturation

------------ util functions ------------
local function clamp(value, min, max)
    --[[
        Description: clamp value between [min, max]
    ]]
    return math.min(math.max(value, min), max)
end

------------ class functions for ScriptComponent ------------
function ScriptCompSaturation.new(construct, ...)
    local self = setmetatable({}, ScriptCompSaturation)

    if construct and ScriptCompSaturation.constructor then ScriptCompSaturation.constructor(self, ...) end
    -- user parameters
    self.saturationIntensity = 0.

    -- other parameters
    self.MinIntensity = -1.
    self.MaxIntensity = 1.

    self.InputTex = nil
    self.OutputTex = nil
    return self
end

function ScriptCompSaturation:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value, _comp)
        if self[_key] ~= nil then
            self[_key] = _value
            if _comp and _comp.properties ~= nil then
                _comp.properties:set(_key, _value)
            end
        end
    end

    if key == "saturationIntensity" then
        _setEffectAttr(key, value, comp)
    else
        _setEffectAttr(key, value, comp)
    end
end

function ScriptCompSaturation:onStart(comp)
    self.matSaturation = comp.entity:searchEntity("EntitySaturation"):getComponent("MeshRenderer").material
    self.camSaturation = comp.entity:searchEntity("CameraSaturation"):getComponent("Camera")
end

function ScriptCompSaturation:onUpdate(comp, deltaTime)
    -- prepare parameters
    self.saturationIntensity = clamp(self.saturationIntensity, self.MinIntensity, self.MaxIntensity)
    local intensity = self.saturationIntensity + 1.0

    -- set InputTex and OutputTex
    self.matSaturation:setTex("u_inputTexture", self.InputTex)
    self.camSaturation.renderTexture = self.OutputTex

    -- set material parameters
    self.matSaturation:setFloat("u_intensity", intensity)
end

exports.ScriptCompSaturation = ScriptCompSaturation
return exports
