---@class ScriptCompSoftGlow: ScriptComponent
---@field thresholdType string [UI(Option={"S", "D"})]
---@field thresholdLow number [UI(Range={0., 1.}, Drag)]
---@field thresholdHigh number [UI(Range={0., 1.}, Drag)]
---@field thresholdSmooth number [UI(Range={0., 1.}, Drag)]
---@field grayScale number [UI(Range={0., 1.}, Drag)]
---@field exposure number [UI(Range={0., 10.}, Drag)]
---@field glowIntensity number [UI(Range={0., 500.}, Drag)]
---@field quality number [UI(Range={0., 1.}, Drag)]
---@field glowColor Color [UI(NoAlpha)]
---@field displayGlow boolean
---@field InputTex Texture
---@field OutputTex Texture
---@field downsampleXTex Texture
---@field downsampleYTex Texture
---@field lumiSharedRt Vector [UI(Type="Texture")]

local exports = exports or {}
local ScriptCompSoftGlow = ScriptCompSoftGlow or {}
ScriptCompSoftGlow.__index = ScriptCompSoftGlow


function ScriptCompSoftGlow.new(construct, ...)
    local self = setmetatable({}, ScriptCompSoftGlow)

    if construct and ScriptCompSoftGlow.constructor then ScriptCompSoftGlow.constructor(self, ...) end
    -- user parameters
    self.thresholdType = "S"
    self.thresholdLow = 0.5
    self.thresholdHigh = 1.
    self.thresholdSmooth = 0.
    self.grayScale = 0.
    self.exposure = 1.
    self.glowIntensity = 0.
    self.quality = 0.5
    self.glowColor = Amaz.Color(1., 1., 1.)
    self.displayGlow = false

    -- other parameters
    self.NormalizationSize = 1000.
    self.MaxIntensity = 500.
    self.RadiusOverSigma = 2.5
    self.Eps = 1e-5

    self.InputTex = nil
    self.OutputTex = nil
    self.downsampleXTex = nil
    self.downsampleYTex = nil
    self.midTex = nil
    return self
end

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


local function boolToInt(flag)
    --[[
        Description: convert flag from bool to int
    ]]
    if flag then return 1 end
    return 0
end


local function getThresholdType(thresholdType)
    --[[
        Description: convert thresholdType from string to int
    ]]
    local thresholdTypeTable = {
        ["S"] = 0, -- default
        ["D"] = 1,
    }
    local flag = thresholdTypeTable[thresholdType]
    if flag == nil then flag = 0 end
    return flag
end


local function getSampleNum(intensity)
    --[[
        Description: get sample number and downsample scale
    ]]
    local scale = 1.
    local bias = 0.
    local s = scale
    if intensity <= 10 then
        scale = 0.8
        bias = 0.
        s = 1.0
    elseif intensity <= 50 then
        scale = 0.7
        bias = 2.
        s = 0.78
    elseif intensity <= 200 then
        scale = 0.5
        bias = 10
        s = 0.66
    else
        scale = 0.25
        bias = 60.
        s = 0.7
    end

    local sampleNum = scale * intensity + bias
    sampleNum = sampleNum * s
    if sampleNum < 2. then
        sampleNum = math.floor(sampleNum + 0.5)
    end
    return sampleNum, scale
end


local function getQualityParam(quality)
    local qualityParam = quality * 2. - 1.
    if qualityParam < 0. then
        qualityParam = 10 ^ qualityParam
    else
        qualityParam = qualityParam * 2. + 1.
    end
    return qualityParam
end


------------ class functions for ScriptComponent ------------
function ScriptCompSoftGlow:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value, _comp)
        if self[_key] ~= nil then
            self[_key] = _value
            if _comp and _comp.properties ~= nil then
                _comp.properties:set(_key, _value)
            end
        end
    end

    if key == "thresholdType" then
        local typeTable = { "S", "D" }
        local thresholdType = typeTable[value + 1]
        if thresholdType == nil then thresholdType = "S" end
        _setEffectAttr(key, thresholdType, comp)
    else
        _setEffectAttr(key, value, comp)
    end
end

function ScriptCompSoftGlow:onStart(comp)
    self.camGaussianBlurX = comp.entity:searchEntity("CameraGaussianBlurX"):getComponent("Camera")
    self.camGaussianBlurY = comp.entity:searchEntity("CameraGaussianBlurY"):getComponent("Camera")
    self.camThreshold = comp.entity:searchEntity("CameraThreshold"):getComponent("Camera")
    self.camDownScale = comp.entity:searchEntity("CameraDownScale"):getComponent("Camera")
    self.camBlend = comp.entity:searchEntity("CameraBlend"):getComponent("Camera")

    self.matGaussianBlurX = comp.entity:searchEntity("EntityGaussianBlurX"):getComponent("MeshRenderer").material
    self.matGaussianBlurY = comp.entity:searchEntity("EntityGaussianBlurY"):getComponent("MeshRenderer").material
    self.matThreshold = comp.entity:searchEntity("EntityThreshold"):getComponent("MeshRenderer").material
    self.matBlend = comp.entity:searchEntity("EntityBlend"):getComponent("MeshRenderer").material

    self.midTex = self.lumiSharedRt:get(0)
end

function ScriptCompSoftGlow:getBlurParam(intensity, xScale, yScale, sampleNum, qualityParam)
    local radiusX = xScale * intensity / self.NormalizationSize
    local radiusY = yScale * intensity / self.NormalizationSize
    local sigmaX = radiusX / self.RadiusOverSigma
    local sigmaY = radiusY / self.RadiusOverSigma
    local sampleX = sampleNum * qualityParam
    local sampleY = sampleNum * qualityParam
    local dx = radiusX / math.max(sampleX, self.Eps)
    local dy = radiusY / math.max(sampleY, self.Eps)
    return sampleX, sampleY, sigmaX, sigmaY, dx, dy
end

function ScriptCompSoftGlow:onUpdate(comp, deltaTime)
    local textureWidth = self.OutputTex.width
    local textureHeight = self.OutputTex.height
    if self.midTex.width ~= textureWidth or self.midTex.height ~= textureHeight then
        self.midTex.width = textureWidth
        self.midTex.height = textureHeight
    end

    local thresholdType = getThresholdType(self.thresholdType)
    self.thresholdLow = clamp(self.thresholdLow, 0., 1.)
    self.thresholdHigh = clamp(self.thresholdHigh, 0., 1.)
    local thresholdHigh = math.max(self.thresholdHigh, self.thresholdHigh)
    self.thresholdSmooth = clamp(self.thresholdSmooth, 0., 1.)
    self.grayScale = clamp(self.grayScale, 0., 1.)
    self.exposure = clamp(self.exposure, 0., 10.)
    local displayGlow = boolToInt(self.displayGlow)

    -- exposure attenuation when intensity is low
    local exposure = self.exposure
    local attenuationIntensity = 20.
    if self.glowIntensity < attenuationIntensity then
        exposure = exposure * (self.glowIntensity / attenuationIntensity) ^ 2.
    end

    -- compute intensity. intensity is the only factors that affect blur intensity
    self.glowIntensity = clamp(self.glowIntensity, 0., self.MaxIntensity)
    local sampleNum, downScale = getSampleNum(self.glowIntensity)
    local qualityParam = getQualityParam(self.quality)
    local xScale, yScale = getXYScale(textureWidth, textureHeight)
    local sampleX, sampleY, sigmaX, sigmaY, dx, dy = self:getBlurParam(self.glowIntensity, xScale, yScale, sampleNum, qualityParam)

    self.downsampleXTex.width = textureWidth * downScale
    self.downsampleXTex.height = textureHeight * downScale
    self.downsampleYTex.width = textureWidth * downScale
    self.downsampleYTex.height = textureHeight * downScale

    -- set textures
    self.matThreshold:setTex("u_inputTexture", self.InputTex)
    self.camThreshold.renderTexture = self.midTex
    self.camDownScale.inputTexture = self.midTex
    self.camDownScale.renderTexture = self.downsampleYTex
    self.matGaussianBlurX:setTex("u_inputTexture", self.downsampleYTex)
    self.camGaussianBlurX.renderTexture = self.downsampleXTex
    self.matGaussianBlurY:setTex("u_inputTexture", self.downsampleXTex)
    self.camGaussianBlurY.renderTexture = self.downsampleYTex
    self.matBlend:setTex("u_inputTexture", self.InputTex)
    self.matBlend:setTex("u_glowTexture", self.downsampleYTex)
    self.camBlend.renderTexture = self.OutputTex

    -- set parameters for materials
    self.matThreshold:setFloat("u_thresholdLow", self.thresholdLow)
    self.matThreshold:setFloat("u_thresholdHigh", thresholdHigh)
    self.matThreshold:setFloat("u_thresholdSmooth", self.thresholdSmooth)
    self.matThreshold:setFloat("u_grayScale", self.grayScale)
    self.matThreshold:setInt("u_thresholdType", thresholdType)

    self.matBlend:setFloat("u_exposure", exposure)
    self.matBlend:setInt("u_displayGlow", displayGlow)
    self.matBlend:setVec3("u_glowColor", Amaz.Vector3f(self.glowColor.r, self.glowColor.g, self.glowColor.b))

    self.matGaussianBlurX:setFloat("u_sampleX", sampleX)
    self.matGaussianBlurX:setFloat("u_sigmaX", sigmaX)
    self.matGaussianBlurX:setFloat("u_stepX", dx)

    self.matGaussianBlurY:setFloat("u_sampleY", sampleY)
    self.matGaussianBlurY:setFloat("u_sigmaY", sigmaY)
    self.matGaussianBlurY:setFloat("u_stepY", dy)
    self.matGaussianBlurY:setFloat("u_exposure", exposure)
end

exports.ScriptCompSoftGlow = ScriptCompSoftGlow
return exports
