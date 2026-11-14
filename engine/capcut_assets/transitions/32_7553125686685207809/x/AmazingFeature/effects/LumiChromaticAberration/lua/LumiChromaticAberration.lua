---@class LumiChromaticAberration: ScriptComponent
---@field offsetX number [UI(Range={-1., 1.}, Drag)]
---@field offsetY number [UI(Range={-1., 1.}, Drag)]
---@field InputTex Texture
---@field OutputTex Texture

local exports = exports or {}
local LumiChromaticAberration = LumiChromaticAberration or {}
LumiChromaticAberration.__index = LumiChromaticAberration

------------ util functions ------------
local function clamp(value, min, max)
    --[[
        Description: clamp value between [min, max]
    ]]
    return math.min(math.max(value, min), max)
end

------------ class functions for ScriptComponent ------------
function LumiChromaticAberration.new(construct, ...)
    local self = setmetatable({}, LumiChromaticAberration)

    if construct and LumiChromaticAberration.constructor then LumiChromaticAberration.constructor(self, ...) end
    -- user parameters
    self.offsetX = 0.
    self.offsetY = 0.

    -- other parameters
    self.OffsetScale = 0.2

    self.InputTex = nil
    self.OutputTex = nil

    return self
end

function LumiChromaticAberration:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value, _comp)
        if self[_key] ~= nil then
            self[_key] = _value
            if _comp and _comp.properties ~= nil then
                _comp.properties:set(_key, _value)
            end
        end
    end

    if key == "offsetX" or key == "offsetY" then
        _setEffectAttr(key, value, comp)
    else
        _setEffectAttr(key, value, comp)
    end
end

function LumiChromaticAberration:onStart(comp)
    self.camOffset = comp.entity:searchEntity("CameraOffset"):getComponent("Camera")
    self.matOffset= comp.entity:searchEntity("EntityOffset"):getComponent("MeshRenderer").material
end

function LumiChromaticAberration:onUpdate(comp, deltaTime)
    -- prepare parameters
    self.offsetX = clamp(self.offsetX, -1., 1.)
    self.offsetY = clamp(self.offsetY, -1., 1.)
    local offsetX = self.offsetX * self.OffsetScale
    local offsetY = self.offsetY * self.OffsetScale

    -- set InputTex, OutputTex
    self.matOffset:setTex("u_inputTexture", self.InputTex)
    self.camOffset.renderTexture = self.OutputTex

    self.matOffset:setFloat("u_offsetX", offsetX)
    self.matOffset:setFloat("u_offsetY", offsetY)
end

exports.LumiChromaticAberration = LumiChromaticAberration
return exports
