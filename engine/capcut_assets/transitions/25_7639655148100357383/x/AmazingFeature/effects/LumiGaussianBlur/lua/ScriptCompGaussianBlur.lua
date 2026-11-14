---@class ScriptCompGaussianBlur: ScriptComponent
---@field blurIntensity number [UI(Range={0., 1000.}, Drag)]
---@field horizontalStrength number [UI(Range={0., 1.}, Drag)]
---@field verticalStrength number [UI(Range={0., 1.}, Drag)]
---@field quality number [UI(Range={0., 1.}, Drag)]
---@field spaceDither number [UI(Range={0, 1.}, Drag)]
---@field blurDirection string [UI(Option={"Horizontal and Vertical", "Horizontal", "Vertical"})]
---@field borderType string [UI(Option={"Normal", "Replicate", "Black", "Reflect"})]
---@field blurAlpha boolean
---@field inverseGammaCorrection boolean
---@field InputTex Texture
---@field OutputTex Texture
---@field downsampleXTex Texture
---@field downsampleYTex Texture
---@field downsampleRT Vector [UI(Type="Texture")]

local exports = exports or {}
local ScriptCompGaussianBlur = ScriptCompGaussianBlur or {}
ScriptCompGaussianBlur.__index = ScriptCompGaussianBlur

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

local function getBorderType(borderType)
    --[[
        Description: convert borderType from string to int
    ]]
    local borderTypeTable = {
        ["Normal"] = 0, -- default
        ["Replicate"] = 1,
        ["Black"] = 2,
        ["Reflect"] = 3
    }
    local flag = borderTypeTable[borderType]
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
    if intensity <= 30 then
        scale = 0.5
        bias = 2.
        s = 0.78
    elseif intensity <= 100 then
        scale = 0.5
        bias = 10
        s = 0.66
    elseif intensity <= 200 then
        scale = 0.25
        bias = 50.
        s = 0.7
    else
        scale = 0.125
        bias = 80.
        s = 0.8
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
function ScriptCompGaussianBlur.new(construct, ...)
    local self = setmetatable({}, ScriptCompGaussianBlur)

    if construct and ScriptCompGaussianBlur.constructor then ScriptCompGaussianBlur.constructor(self, ...) end
    -- user parameters
    self.blurIntensity = 0.
    self.horizontalStrength = 1.
    self.verticalStrength = 1.
    self.quality = 0.5
    self.blurDirection = "Horizontal and Vertical"
    self.borderType = "Normal"
    self.blurAlpha = true
    self.inverseGammaCorrection = true
    self.spaceDither = 0.

    -- other parameters
    self.NormalizationSize = 1000.
    self.MaxIntensity = 1000.
    self.RadiusOverSigma = 2.5
    self.Gamma = 2.2
    self.Eps = 1e-5

    self.InputTex = nil
    self.OutputTex = nil
    return self
end

function ScriptCompGaussianBlur:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value, _comp)
        if self[_key] ~= nil then
            self[_key] = _value
            if _comp and _comp.properties ~= nil then
                _comp.properties:set(_key, _value)
            end
        end
    end

    if key == "blurDirection" then
        local typeTable = {
            [0] = "Horizontal and Vertical",
            [1] = "Horizontal",
            [2] = "Vertical"
        }
        local blurDirection = typeTable[value]
        if blurDirection == nil then blurDirection = "Horizontal and Vertical" end
        _setEffectAttr(key, blurDirection, comp)
    elseif key == "borderType" then
        local typeTable = {
            [0] = "Normal",
            [1] = "Replicate",
            [2] = "Black",
            [3] = "Reflect"
        }
        local borderType = typeTable[value]
        if borderType == nil then borderType = "Normal" end
        _setEffectAttr(key, borderType, comp)
    else
        _setEffectAttr(key, value, comp)
    end
end

function ScriptCompGaussianBlur:onStart(comp)
    self.camGaussianBlurX = comp.entity:searchEntity("CameraGaussianBlurX"):getComponent("Camera")
    self.camGaussianBlurY = comp.entity:searchEntity("CameraGaussianBlurY"):getComponent("Camera")
    self.camDownScale = comp.entity:searchEntity("CameraDownScale"):getComponent("Camera")
    self.camUpScale = comp.entity:searchEntity("CameraUpScale"):getComponent("Camera")

    self.matGaussianBlurX = comp.entity:searchEntity("EntityGaussianBlurX"):getComponent("MeshRenderer").material
    self.matGaussianBlurY = comp.entity:searchEntity("EntityGaussianBlurY"):getComponent("MeshRenderer").material
end

function ScriptCompGaussianBlur:updateDownsampleRT(textureWidth, textureHeight, downScale)
    local x2= self.downsampleRT:get(0)
    local y2= self.downsampleRT:get(1)
    local x4= self.downsampleRT:get(2)
    local y4= self.downsampleRT:get(3)
    local x8= self.downsampleRT:get(4)
    local y8= self.downsampleRT:get(5)
    x2.width = textureWidth / 2
    x2.height = textureHeight / 2
    y2.width = textureWidth / 2
    y2.height = textureHeight / 2
    x4.width = textureWidth / 4
    x4.height = textureHeight / 4
    y4.width = textureWidth / 4
    y4.height = textureHeight / 4
    x8.width = textureWidth / 8
    x8.height = textureHeight / 8
    y8.width = textureWidth / 8
    y8.height = textureHeight / 8
    if downScale <= 0.125 + self.Eps then
        self.downsampleXTex = x8
        self.downsampleYTex = y8
    elseif downScale <= 0.25 + self.Eps then
        self.downsampleXTex = x4
        self.downsampleYTex = y4
    else
        self.downsampleXTex = x2
        self.downsampleYTex = y2
    end
end

function ScriptCompGaussianBlur:onUpdate(comp, deltaTime)
    local textureWidth = self.OutputTex.width
    local textureHeight = self.OutputTex.height

    -- compute intensity. intensityX/Y are the only factors that affect blur intensity
    self.blurIntensity = clamp(self.blurIntensity, 0., self.MaxIntensity)
    self.horizontalStrength = clamp(self.horizontalStrength, 0., 1.)
    self.verticalStrength = clamp(self.verticalStrength, 0., 1.)
    local xStrenth = self.horizontalStrength
    local yStrenth = self.verticalStrength
    if self.blurDirection == "Horizontal" then
        yStrenth = 0.
    elseif self.blurDirection == "Vertical" then
        xStrenth = 0.
    end
    local intensityX = self.blurIntensity * xStrenth
    local intensityY = self.blurIntensity * yStrenth
    local sampleNum, downScale = getSampleNum(self.blurIntensity)
    self.quality = clamp(self.quality, 0., 1.)
    local qualityParam = getQualityParam(self.quality)
    local borderType = getBorderType(self.borderType)
    local inverseGammaCorrection = boolToInt(self.inverseGammaCorrection)
    local blurAlpha = boolToInt(self.blurAlpha)
    self.spaceDither = clamp(self.spaceDither, 0., 1.)

    self:updateDownsampleRT(textureWidth, textureHeight, downScale)

    -- compute sigmaX/Y, sampleX/Y, dx/y.
    local xScale, yScale = getXYScale(textureWidth, textureHeight)
    local radiusX = xScale * intensityX / self.NormalizationSize
    local radiusY = yScale * intensityY / self.NormalizationSize
    local sigmaX = radiusX / self.RadiusOverSigma
    local sigmaY = radiusY / self.RadiusOverSigma
    local sampleX = sampleNum * self.horizontalStrength * qualityParam
    local sampleY = sampleNum * self.verticalStrength * qualityParam
    local dx = radiusX / math.max(sampleX, self.Eps)
    local dy = radiusY / math.max(sampleY, self.Eps)

    -- set Textures
    self.camDownScale.inputTexture = self.InputTex
    self.camDownScale.renderTexture = self.downsampleYTex
    self.camUpScale.renderTexture = self.OutputTex
    if self.blurIntensity <= 0.01 then
        self.camGaussianBlurX.entity.visible = false
        self.camGaussianBlurY.entity.visible = false
        self.camDownScale.entity.visible = false
        self.camUpScale.inputTexture = self.InputTex
    elseif self.blurDirection == "Horizontal" then
        self.camGaussianBlurX.entity.visible = true
        self.camGaussianBlurY.entity.visible = false
        self.camDownScale.entity.visible = true
        self.camDownScale.renderTexture = self.downsampleYTex
        self.matGaussianBlurX:setTex("u_inputTexture", self.downsampleYTex)
        self.camGaussianBlurX.renderTexture = self.downsampleXTex
        self.camUpScale.inputTexture = self.downsampleXTex
    elseif self.blurDirection == "Vertical" then
        self.camGaussianBlurX.entity.visible = false
        self.camGaussianBlurY.entity.visible = true
        self.camDownScale.entity.visible = true
        self.camDownScale.renderTexture = self.downsampleYTex
        self.matGaussianBlurY:setTex("u_inputTexture", self.downsampleYTex)
        self.camGaussianBlurY.renderTexture = self.downsampleXTex
        self.camUpScale.inputTexture = self.downsampleXTex
    else
        self.camGaussianBlurX.entity.visible = true
        self.camGaussianBlurY.entity.visible = true
        self.camDownScale.entity.visible = true
        self.matGaussianBlurX:setTex("u_inputTexture", self.downsampleYTex)
        self.camGaussianBlurX.renderTexture = self.downsampleXTex
        self.matGaussianBlurY:setTex("u_inputTexture", self.downsampleXTex)
        self.camGaussianBlurY.renderTexture = self.downsampleYTex
        self.camUpScale.inputTexture = self.downsampleYTex
    end

    -- set parameters for materials
    self.matGaussianBlurX:setFloat("u_sampleX", sampleX)
    self.matGaussianBlurX:setFloat("u_sigmaX", sigmaX)
    self.matGaussianBlurX:setFloat("u_stepX", dx)
    self.matGaussianBlurX:setFloat("u_stepY", dy)
    self.matGaussianBlurX:setFloat("u_gamma", self.Gamma)
    self.matGaussianBlurX:setFloat("u_spaceDither", self.spaceDither)
    self.matGaussianBlurX:setInt("u_borderType", borderType)
    self.matGaussianBlurX:setInt("u_inverseGammaCorrection", inverseGammaCorrection)
    self.matGaussianBlurX:setInt("u_blurAlpha", blurAlpha)

    self.matGaussianBlurY:setFloat("u_sampleY", sampleY)
    self.matGaussianBlurY:setFloat("u_sigmaY", sigmaY)
    self.matGaussianBlurY:setFloat("u_stepX", dx)
    self.matGaussianBlurY:setFloat("u_stepY", dy)
    self.matGaussianBlurY:setFloat("u_gamma", self.Gamma)
    self.matGaussianBlurY:setFloat("u_spaceDither", self.spaceDither)
    self.matGaussianBlurY:setInt("u_borderType", borderType)
    self.matGaussianBlurY:setInt("u_inverseGammaCorrection", inverseGammaCorrection)
    self.matGaussianBlurY:setInt("u_blurAlpha", blurAlpha)
end

exports.ScriptCompGaussianBlur = ScriptCompGaussianBlur
return exports
