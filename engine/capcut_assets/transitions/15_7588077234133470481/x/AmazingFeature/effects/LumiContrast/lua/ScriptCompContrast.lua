---@class ScriptCompContrast: ScriptComponent
---@field contrastIntensity number [UI(Range={0., 2.}, Drag)]
---@field pivot number [UI(Range={0., 1.}, Drag)]
---@field InputTex Texture
---@field OutputTex Texture

local exports = exports or {}
local ScriptCompContrast = ScriptCompContrast or {}
ScriptCompContrast.__index = ScriptCompContrast

------------ util functions ------------
local function clamp(value, min, max)
    --[[
        Description: clamp value between [min, max]
    ]]
    return math.min(math.max(value, min), max)
end

local function getSigmoidXFactor(intensity)
    return math.exp(8.33 * intensity - 12.16) + 5.82 * intensity - 1.72
end

local function getSigmoid(x, intensity, pivot)
    local a = getSigmoidXFactor(intensity)
    local s = 1.0 / (1.0 + math.exp(-a * (x - pivot)))
    local y = s + pivot - 0.5       -- sigmoid value
    local k = a * s * (1.0 - s)     -- sigmoid derivative
    return y, k
end

------------ class functions for ScriptComponent ------------
function ScriptCompContrast.new(construct, ...)
    local self = setmetatable({}, ScriptCompContrast)

    if construct and ScriptCompContrast.constructor then ScriptCompContrast.constructor(self, ...) end
    -- user parameters
    self.contrastIntensity = 1.
    self.pivot = 0.43

    -- other parameters
    self.MinIntensity = 0.
    self.MaxIntensity = 2.
    self.Eps = 1e-5

    self.InputTex = nil
    self.OutputTex = nil
    return self
end

function ScriptCompContrast:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value, _comp)
        if self[_key] ~= nil then
            self[_key] = _value
            if _comp and _comp.properties ~= nil then
                _comp.properties:set(_key, _value)
            end
        end
    end

    if key == "contrastIntensity"
        or key == "pivot"
    then
        _setEffectAttr(key, value, comp)
    else
        _setEffectAttr(key, value, comp)
    end
end

function ScriptCompContrast:onStart(comp)
    self.matContrast = comp.entity:searchEntity("EntityContrast"):getComponent("MeshRenderer").material
    self.camContrast = comp.entity:searchEntity("CameraContrast"):getComponent("Camera")
end

function ScriptCompContrast:onUpdate(comp, deltaTime)
    -- prepare parameters
    self.contrastIntensity = clamp(self.contrastIntensity, self.MinIntensity, self.MaxIntensity)
    self.pivot = clamp(self.pivot, 0., 1.)

    local xFactor = getSigmoidXFactor(self.contrastIntensity)
    local leftValue, leftSlope = getSigmoid(0.0, self.contrastIntensity, self.pivot)
    local rightValue, rightSlope = getSigmoid(1.0, self.contrastIntensity, self.pivot)
    local pivotValue, pivotSlope = getSigmoid(self.pivot, self.contrastIntensity, self.pivot)
    local leftDiff = 0.0 - leftValue
    local rightDiff = 1.0 - rightValue
    local leftSlopeDiff = pivotSlope - leftSlope
    local rightSlopeDiff = pivotSlope - rightSlope

    -- set InputTex and OutputTex
    self.matContrast:setTex("u_inputTexture", self.InputTex)
    self.camContrast.renderTexture = self.OutputTex

    -- set material parameters
    self.matContrast:setFloat("u_intensity", self.contrastIntensity)
    self.matContrast:setFloat("u_pivot", self.pivot)

    self.matContrast:setFloat("u_xFactor", xFactor)
    self.matContrast:setFloat("u_leftDiff", leftDiff)
    self.matContrast:setFloat("u_rightDiff", rightDiff)
    self.matContrast:setFloat("u_leftSlopeDiff", leftSlopeDiff)
    self.matContrast:setFloat("u_rightSlopeDiff", rightSlopeDiff)
    self.matContrast:setFloat("u_pivotSlope", pivotSlope)
end

exports.ScriptCompContrast = ScriptCompContrast
return exports
