local exports = exports or {}
local AdjustXT = AdjustXT or {}
AdjustXT.__index = AdjustXT
---@class AdjustXT: ScriptComponent
---@field brilliance number
---@field brightness number
---@field contrast number
---@field exposure number
---@field fade number
---@field highlight number
---@field lightSensation number
---@field saturation number
---@field shadow number
---@field temperature number
---@field tone number
---@field vibrance number
---@field InputTex Texture
---@field OutputTex Texture
---@field lumiSharedRt Vector [UI(Type="Texture")]

function AdjustXT.new(construct, ...)
    local self = setmetatable({}, AdjustXT)
    if construct and AdjustXT.constructor then
        AdjustXT.constructor(self, ...)
    end

    return self
end

function AdjustXT:constructor()
end

function AdjustXT:onStart(comp)
    self:start(comp)
end

function AdjustXT:start(comp)
    self.first = true
    self.camera = comp.entity:searchEntity("Camera_entity_3"):getComponent("Camera")
    self.material = comp.entity:searchEntity("map_renderer"):getComponent("MeshRenderer").material
    self.material_final = comp.entity:searchEntity("final_renderer"):getComponent("MeshRenderer").material
    self.material_splendor = comp.entity:searchEntity("splendor_renderer"):getComponent("MeshRenderer").material
    self.camera_map = comp.entity:searchEntity("Camera_entity_map"):getComponent("Camera")
    self.camera2 =  comp.entity:searchEntity("Camera_entity"):getComponent("Camera")
    self.midTex = self.lumiSharedRt:get(0)
    self.camera2.renderTexture = self.midTex
    self.material_splendor:setTex("inputImageTexture", self.camera2.renderTexture)
end

function AdjustXT:updateMaterial()
    if self.first == nil then
        return
    end

    if self.midTex.width ~= self.OutputTex.width or self.midTex.height ~= self.OutputTex.height then
        self.midTex.width = self.OutputTex.width
        self.midTex.height = self.OutputTex.height
    end

    self.camera.renderTexture = self.OutputTex
    self.camera_map.renderTexture = self.OutputTex
    self.material_final:setTex("lut", self.OutputTex)
    self.material_final:setTex("inputImage", self.InputTex)
    self.material_splendor:setFloat("ins", self.brilliance*0.5+0.5)
    self.material:setFloat("intensityBrightness", self.brightness)
    self.material:setFloat("intensityContrast", self.contrast)
    self.material:setFloat("intensityExposure", self.exposure)
    self.material:setFloat("intensityFade", self.fade)
    self.material:setFloat("intensityHighlight", self.highlight)
    self.material:setFloat("intensityLightSensation", self.lightSensation)
    self.material:setFloat("intensitySaturation", self.saturation)
    self.material:setFloat("intensityShadow", self.shadow)
    self.material:setFloat("intensityTemperature", self.temperature)
    self.material:setFloat("intensityVibrance", self.vibrance)
    self.material:setFloat("intensityTone", self.tone)
end

function AdjustXT:onUpdate(comp, detalTime)
    if self.first == nil then
        self:start(comp)
    end

    self:updateMaterial()
end

exports.AdjustXT = AdjustXT
return exports
