---@class ScriptCompRadialBlur: ScriptComponent
---@field blurType string [UI(Option={"Straight Zoom", "Fading Zoom", "Centered Zoom", "Rotate", "Scratch", "Rotate Fading"})]
---@field amount number [UI(Range={-250., 250.}, Drag)]
---@field quality number [UI(Range={0.1, 1}, Drag)]
---@field center Vector2f
---@field weightDecay number [UI(Range={0.0, 1.0}, Drag)]
---@field dither number [UI(Range={0.0, 1.0}, Drag)]
---@field borderType string [UI(Option={"Black", "Normal"})]
---@field blurAlpha boolean 
---@field inverseGammaCorrection boolean
---@field InputTex Texture
---@field OutputTex Texture

local exports = exports or {}
local ScriptCompRadialBlur = ScriptCompRadialBlur or {}
ScriptCompRadialBlur.__index = ScriptCompRadialBlur

------------ util functions ------------
local function clamp(value, min, max)
    --[[
        Description: clamp value between [min, max]
    ]]
    return math.min(math.max(value, min), max)
end

local function remap(value, srcMin, srcMax, dstMin, dstMax)
    --[[
        Description: linearly remap value from [srcMin, srcMax] to [dstMin, dstMax]
    ]]
    return dstMin + (value - srcMin) * (dstMax - dstMin) / (srcMax - srcMin)
end

local function getBlurType(blurType)
    --[[
        Description: convert blurType from string to int
    ]]
    local blurTypeTable = {
        ["Straight Zoom"] = 0,  -- default
        ["Fading Zoom"] = 1,
        ["Centered Zoom"] = 2,
        ["Rotate"] = 3,
        ["Scratch"] = 4,
        ["Rotate Fading"] = 5
    }
    local flag = blurTypeTable[blurType]
    if flag == nil then flag = 0 end
    return flag
end

local function getBorderType(borderType)
    --[[
        Description: convert borderType from string to int
    ]]
    local borderTypeTable = {
        ["Black"] = 0,  -- default
        ["Normal"] = 1,
    }
    local flag = borderTypeTable[borderType]
    if flag == nil then flag = 0 end
    return flag
end

local function boolToInt(flag)
    --[[
        Description: convert flag from bool to int
    ]]
    if flag then return 1 end
    return 0
end

------------ class functions for ScriptComponent ------------
function ScriptCompRadialBlur.new(construct, ...)
    local self = setmetatable({}, ScriptCompRadialBlur)

    if construct and ScriptCompRadialBlur.constructor then ScriptCompRadialBlur.constructor(self, ...) end
    -- user parameters
    self.blurType = "Straight Zoom"
    self.amount = 0.    -- will be converted to intensity for shader
    self.quality = 0.2
    self.center = Amaz.Vector2f(0.5, 0.5)
    self.weightDecay = 0.965
    self.dither = 0.
    self.borderType = "Black"
    self.blurAlpha = true
    self.inverseGammaCorrection = false

    -- other parameters
    self.MinAmount = -250.
    self.MaxAmount = 250.
    self.NormalizationAmount = 200.
    self.MinQuality = 0.1
    self.MaxQuality = 1
    self.MinCenter = -1.
    self.MaxCenter = 2.
    self.MaxDither = 0.5
    self.Gamma = 2.2
    self.entityTable = {}   -- initialized in `onStart`

    -- finetuned parameters for some uniform variables
    self.NormalizationSample = 50.
    self.SampleScale = 8.
    self.SampleBias = 5.

    self.InputTex = nil
    self.OutputTex = nil
    return self
end

function ScriptCompRadialBlur:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value, _comp)
        if self[_key] ~= nil then
            self[_key] = _value
            if _comp and _comp.properties ~= nil then
                _comp.properties:set(_key, _value)
            end
        end
    end

    if key == "blurType" then
        local typeTable = {
            [0] = "Straight Zoom",
            [1] = "Fading Zoom",
            [2] = "Centered Zoom",
            [3] = "Rotate",
            [4] = "Scratch",
            [5] = "Rotate Fading"
        }
        local blurType = typeTable[value]
        if blurType == nil then blurType = "Straight Zoom" end
        _setEffectAttr(key, blurType, comp)
    elseif key == "borderType" then
        local typeTable = {
            [0] = "Black",
            [1] = "Normal"
        }
        local borderType = typeTable[value]
        if borderType == nil then borderType = "Black" end
        _setEffectAttr(key, borderType, comp)
    elseif key == "amount"
        or key == "quality"
        or key == "center"
        or key == "weightDecay"
        or key == "dither"
        or key == "blurAlpha"
        or key == "inverseGammaCorrection"
    then
        _setEffectAttr(key, value, comp)
    else
        _setEffectAttr(key, value, comp)
    end
end

function ScriptCompRadialBlur:onStart(comp)    
    self.entityTable["RadialBlurZoom"] = comp.entity:searchEntity("EntityRadialBlurZoom")
    self.entityTable["RadialBlurRotate"] = comp.entity:searchEntity("EntityRadialBlurRotate")
    self.camRadialBlur = comp.entity:searchEntity("CameraRadialBlur"):getComponent("Camera")
end

function ScriptCompRadialBlur:onUpdate(comp, deltaTime)
    -- prepare parameters
    self.amount = clamp(self.amount, self.MinAmount, self.MaxAmount)
    local intensity = self.amount / self.NormalizationAmount
    self.quality = clamp(self.quality, self.MinQuality, self.MaxQuality)
    self.center.x = clamp(self.center.x, self.MinCenter, self.MaxCenter)
    self.center.y = clamp(self.center.y, self.MinCenter, self.MaxCenter)
    self.weightDecay = clamp(self.weightDecay, 0., 1.)
    self.dither = clamp(self.dither, 0., 1.)
    local dither = remap(self.dither, 0., 1., 0., self.MaxDither)
    local blurType = getBlurType(self.blurType)
    local borderType = getBorderType(self.borderType)
    local blurAlpha = boolToInt(self.blurAlpha)
    local inverseGammaCorrection = boolToInt(self.inverseGammaCorrection)
    local material = nil

    local weightDecay = self.weightDecay
    if self.blurType ~= "Fading Zoom" and self.blurType ~= "Rotate Fading" then
        weightDecay = 1.
    end

    -- set visible property of entities for selecting blurType
    if blurType >= 3 then
        -- Rotate Type
        self.entityTable["RadialBlurRotate"].selfvisible = true
        self.entityTable["RadialBlurZoom"].selfvisible = false
        material = self.entityTable["RadialBlurRotate"]:getComponent("MeshRenderer").material
    else
        -- Zoom Type
        self.entityTable["RadialBlurRotate"].selfvisible = false
        self.entityTable["RadialBlurZoom"].selfvisible = true
        material = self.entityTable["RadialBlurZoom"]:getComponent("MeshRenderer").material
    end

    -- set InputTex, OutputTex
    material:setTex("u_inputTexture", self.InputTex)
    self.camRadialBlur.renderTexture = self.OutputTex

    -- set material parameters
    material:setInt("u_blurType", blurType)
    material:setFloat("u_intensity", intensity)
    material:setFloat("u_quality", self.quality*100)
    material:setVec2("u_center", self.center)
    material:setFloat("u_weightDecay", weightDecay)
    material:setFloat("u_dither", dither)
    material:setInt("u_borderType", borderType)
    material:setInt("u_blurAlpha", blurAlpha)
    material:setInt("u_inverseGammaCorrection", inverseGammaCorrection)
    material:setFloat("u_gamma", self.Gamma)
    material:setFloat("u_normalizationSample", self.NormalizationSample)
    material:setFloat("u_sampleScale", self.SampleScale)
    material:setFloat("u_sampleBias", self.SampleBias)
end

exports.ScriptCompRadialBlur = ScriptCompRadialBlur
return exports
