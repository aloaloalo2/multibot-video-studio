local exports = exports or {}
local GlitchSignal = GlitchSignal or {}
GlitchSignal.__index = GlitchSignal
---@class GlitchSignal: ScriptComponent
---@field lowQuality number
---@field filterIntensity number
---@field sharpen number
---@field sharpenSize int [UI(Range={0, 20}, Slider)]
---@field chromaNoise number
---@field hueNoise number
---@field chromaloss number
---@field randomSeed number
---@field destruction Bool
---@field signalStrength number
---@field moireNoise number
---@field moireSize number
---@field moireSpeed number
---@field d2dIntensity number
---@field InputTex Texture
---@field OutputTex Texture
---@field tmpTex0 Texture
---@field tmpTex1 Texture
---@field tmpTex2 Texture

local AE_EFFECT_TAG = 'AE_EFFECT_TAG LumiTag'

function GlitchSignal.new(construct, ...)
    local self = setmetatable({}, GlitchSignal)

    self.lowQuality = 1
    self.filterIntensity = 1.5
    self.sharpen = 0
    self.sharpenSize = 10
    self.chromaNoise = 0
    self.hueNoise = 0
    self.chromaloss = 0
    self.randomSeed = 0
    self.destruction = false
    self.signalStrength = 1
    self.moireNoise = 0
    self.moireSize = 1.0
    self.moireSpeed = 1.0
    self.d2dIntensity = 0
    self.startTime = 0.0
    self.endTime = 6.0
    self.curTime = 0.0
    self.InputTex = nil
    self.OutputTex = nil
    return self
end

function GlitchSignal:onStart(comp)
    self.entity = comp.entity
    self.TAG = AE_EFFECT_TAG .. ' ' .. self.entity.name

    self:start(comp)
end

function GlitchSignal:start(comp)
    self.first = true
    self.properties = comp.properties
    self.materialSharpen0 = comp.entity:searchEntity("renderer_sharpen0"):getComponent("MeshRenderer").material
    self.materialSharpen1 = comp.entity:searchEntity("renderer_sharpen1"):getComponent("MeshRenderer").material
    self.materialNoise = comp.entity:searchEntity("renderer_noise"):getComponent("MeshRenderer").material
    self.materialD2d = comp.entity:searchEntity("renderer_d2d"):getComponent("MeshRenderer").material
    self.materialblur1 = comp.entity:searchEntity("renderer_blur_x1"):getComponent("MeshRenderer").material
    self.camBlit = comp.entity:searchEntity("Camera_entity_bilt"):getComponent("Camera")
end

function GlitchSignal:updateMaterial(comp, time)
    if self.first == nil then
        return
    end

    local w = self.OutputTex.width * 0.5
    local h = self.OutputTex.height * 0.5
    if self.tmpTex0.width ~= w or self.tmpTex0.height ~= h then
        self.tmpTex0.width = w
        self.tmpTex0.height = h
        self.tmpTex1.width = w
        self.tmpTex1.height = h
        self.tmpTex2.width = w
        self.tmpTex2.height = h
    end

    self.materialSharpen0:setTex("inputImageTexture", self.InputTex);
    self.camBlit.renderTexture = self.OutputTex;

    self.materialblur1:setFloat("signalStrength", self.signalStrength);
    self.materialSharpen0:setFloat("lowQuality", self.lowQuality);
    self.materialSharpen0:setFloat("filterIntensity", self.filterIntensity);
    self.materialSharpen1:setFloat("lowQuality", self.lowQuality);
    self.materialSharpen1:setFloat("sharpenIntensity", self.sharpen);
    self.materialSharpen1:setFloat("sharpenSize", math.floor(self.sharpenSize+0.5));
    self.materialSharpen1:setFloat("destruction", self.destruction and 1 or 0);
    self.materialSharpen1:setFloat("signalStrength", self.signalStrength);
    self.materialNoise:setFloat("destruction", self.destruction and 1 or 0);
    -- self.materialNoise:setFloat("chromaNoiseRotate", self.chromaNoiseRotate);
    self.materialNoise:setFloat("chromaNoise", self.chromaNoise);
    self.materialNoise:setFloat("hueNoise", self.hueNoise);
    self.materialNoise:setFloat("chromaloss", self.chromaloss);
    self.materialNoise:setFloat("randomSeed", self.randomSeed);
    self.materialNoise:setFloat("moireNoise", self.moireNoise);
    self.materialNoise:setFloat("moireSize", self.moireSize);
    self.materialNoise:setFloat("time", self.curTime);
    self.materialNoise:setFloat("moireSpeed", self.moireSpeed);
    self.materialD2d:setFloat("d2dIntensity", self.d2dIntensity);
end

function GlitchSignal:onUpdate(comp, detalTime)
    if self.first == nil then
        self:start(comp)
    end
end

exports.GlitchSignal = GlitchSignal
return exports
