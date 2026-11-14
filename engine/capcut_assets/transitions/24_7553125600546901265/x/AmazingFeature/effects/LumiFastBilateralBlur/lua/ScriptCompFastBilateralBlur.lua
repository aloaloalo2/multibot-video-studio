---@class ScriptCompFastBilateralBlur: ScriptComponent
---@field radius number [UI(Range={0., 100.}, Drag)]
---@field horizontalStrength number [UI(Range={0., 1.}, Drag)]
---@field verticalStrength number [UI(Range={0., 1.}, Drag)]
---@field steps number [UI(Range={0.1, 10.}, Drag)]
---@field threshold number [UI(Range={0., 1.}, Drag)]
---@field InputTex Texture
---@field OutputTex Texture
---@field lumiSharedRt Vector [UI(Type="Texture")]

local exports = exports or {}
local ScriptCompFastBilateralBlur = ScriptCompFastBilateralBlur or {}
ScriptCompFastBilateralBlur.__index = ScriptCompFastBilateralBlur

------------ util functions ------------
local function clamp(value, min, max)
    --[[
        Description: clamp value between [min, max]
    ]]
    return math.min(math.max(value, min), max)
end

local function getXYScale(width, height)
    --[[
        Description: get XY scale for adjusting width/height ratio.
    ]]
    -- the following computation for baseSize is to avoid too small or too large width/height ratio.
    local size1 = math.min(width, height)
    local size2 = math.max(width, height) / 2.
    local baseSize = math.max(size1, size2)

    local xScale = baseSize / width
    local yScale = baseSize / height
    return xScale, yScale
end

------------ class functions for ScriptComponent ------------
function ScriptCompFastBilateralBlur.new(construct, ...)
    local self = setmetatable({}, ScriptCompFastBilateralBlur)

    if construct and ScriptCompFastBilateralBlur.constructor then ScriptCompFastBilateralBlur.constructor(self, ...) end
    -- user parameters
    self.radius = 0.
    self.horizontalStrength = 1.
    self.verticalStrength = 1.
    self.steps = 1.
    self.threshold = 0.03

    -- other parameters
    self.NormalizationSize = 1000.
    self.MaxRadius = 100.
    self.MinSteps = 0.1
    self.MaxSteps = 10.
    self.RadiusOverSigma = 2.5
    self.Eps = 1e-5

    self.InputTex = nil
    self.OutputTex = nil
    return self
end

function ScriptCompFastBilateralBlur:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value, _comp)
        if self[_key] ~= nil then
            self[_key] = _value
            if _comp and _comp.properties ~= nil then
                _comp.properties:set(_key, _value)
            end
        end
    end

    _setEffectAttr(key, value, comp)
end

function ScriptCompFastBilateralBlur:onStart(comp)
    self.camFastBilateralBlurX = comp.entity:searchEntity("CameraFastBilateralBlurX"):getComponent("Camera")
    self.camFastBilateralBlurY = comp.entity:searchEntity("CameraFastBilateralBlurY"):getComponent("Camera")

    self.matFastBilateralBlurX = comp.entity:searchEntity("EntityFastBilateralBlurX"):getComponent("MeshRenderer").material
    self.matFastBilateralBlurY = comp.entity:searchEntity("EntityFastBilateralBlurY"):getComponent("MeshRenderer").material

    self.midTex = self.lumiSharedRt:get(0)
    self.camFastBilateralBlurX.renderTexture = self.midTex
    self.matFastBilateralBlurY:setTex("u_inputTexture", self.midTex)
end

function ScriptCompFastBilateralBlur:onUpdate(comp, deltaTime)
    local textureWidth = self.OutputTex.width
    local textureHeight = self.OutputTex.height
    if self.midTex.width ~= textureWidth or self.midTex.height ~= textureHeight then
        self.midTex.width = textureWidth
        self.midTex.height = textureHeight
    end

    -- prepare parameters
    self.radius = clamp(self.radius, 0., self.MaxRadius)
    self.horizontalStrength = clamp(self.horizontalStrength, 0., 1.)
    self.verticalStrength = clamp(self.verticalStrength, 0., 1.)
    local sampleX = self.radius * self.horizontalStrength
    local sampleY = self.radius * self.verticalStrength
    self.steps = clamp(self.steps, self.MinSteps, self.MaxSteps)

    -- compute dx, dy
    local xScale, yScale = getXYScale(textureWidth, textureHeight)
    local dx = self.steps * xScale / self.NormalizationSize
    local dy = self.steps * yScale / self.NormalizationSize

    -- compute sigmaX, sigmaY. Note that radiusX = sampleX * dx, radiusY = sampleY * dy
    local sigmaX = sampleX * dx / self.RadiusOverSigma
    local sigmaY = sampleY * dy / self.RadiusOverSigma
    local sigmaColor = math.max(self.threshold, self.Eps)

    -- set InputTex, OutputTex
    self.matFastBilateralBlurX:setTex("u_inputTexture", self.InputTex)
    self.camFastBilateralBlurY.renderTexture = self.OutputTex

    -- set parameters for materials
    self.matFastBilateralBlurX:setFloat("u_sampleX", sampleX)
    self.matFastBilateralBlurX:setFloat("u_sigmaX", sigmaX)
    self.matFastBilateralBlurX:setFloat("u_stepX", dx)
    self.matFastBilateralBlurX:setFloat("u_sigmaColor", sigmaColor)

    self.matFastBilateralBlurY:setFloat("u_sampleY", sampleY)
    self.matFastBilateralBlurY:setFloat("u_sigmaY", sigmaY)
    self.matFastBilateralBlurY:setFloat("u_stepY", dy)
    self.matFastBilateralBlurY:setFloat("u_sigmaColor", sigmaColor)
end

exports.ScriptCompFastBilateralBlur = ScriptCompFastBilateralBlur
return exports
