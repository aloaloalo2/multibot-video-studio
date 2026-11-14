local exports = exports or {}
local PixelSort = PixelSort or {}
PixelSort.__index = PixelSort
---@class PixelSort: ScriptComponent
---@field threshold number
---@field rotate number
---@field randomly number
---@field reverseSort Bool
---@field triggerType number
---@field sortType number
---@field affectType number
---@field outputType number
---@field featherStart number
---@field featherEnd number
---@field length number
---@field offset number
---@field offsetRandom number
---@field cycle number
---@field randomSeed number
---@field blockSize number
---@field blurSize number
---@field InputTex Texture
---@field OutputTex Texture

function PixelSort.new(construct, ...)
    local self = setmetatable({}, PixelSort)
    if construct and PixelSort.constructor then
        PixelSort.constructor(self, ...)
    end

    self.InputTex = nil
    self.OutputTex = nil

    return self
end

function PixelSort:constructor()
end

function PixelSort:onUpdate(comp, detalTime)
    self:seekToTime(comp, detalTime)
end

function PixelSort:onStart(comp)
    self:start(comp)
end

function PixelSort:start(comp)
    self.first = true
    self.w = self.OutputTex.width
    self.h = self.OutputTex.height
    self.material_mask = comp.entity:searchEntity("renderer_mask"):getComponent("MeshRenderer").material
    self.material_mask_refine = comp.entity:searchEntity("renderer_mask_refine"):getComponent("MeshRenderer").material
    self.material_info = comp.entity:searchEntity("renderer_info"):getComponent("MeshRenderer").material
    self.material_sort = comp.entity:searchEntity("renderer_sort"):getComponent("MeshRenderer").material
    self.material_rotate = comp.entity:searchEntity("renderer_rotate"):getComponent("MeshRenderer").material
    self.material_scale = comp.entity:searchEntity("renderer_scale"):getComponent("MeshRenderer").material

    self.rt0 = comp.entity:searchEntity("Camera_rotate"):getComponent("Camera").renderTexture
    self.rt1 = comp.entity:searchEntity("Camera_mask_refine"):getComponent("Camera").renderTexture
    self.rt2 = comp.entity:searchEntity("Camera_info"):getComponent("Camera").renderTexture
    self.scale_camera = comp.entity:searchEntity("Camera_scale"):getComponent("Camera")
    -- self.pass0Material = comp.entity:searchEntity("strong_sharp_strongSharp_Chro"):searchEntity("renderer_info"):getComponent("MeshRenderer").material

    self:layout(self.w, self.h)
end

function PixelSort:layout (w, h)
    local size = 256
    self.rt0.width = size
    self.rt0.height = h
    self.rt1.width = size
    self.rt1.height = h
    self.rt2.width = size
    self.rt2.height = h
end

function PixelSort:seekToTime(comp, time)
    if self.first == nil then
        self:start(comp)
    end

    local w = self.OutputTex.width
    local h = self.OutputTex.height

    if w ~= self.w or h ~= self.h then
        self.w = w
        self.h = h
        self:layout(w, h)
    end

    self.scale_camera.renderTexture = self.OutputTex
    self.material_rotate:setTex("inputImageTexture", self.InputTex)
    self.material_scale:setTex("inputImageTexture", self.InputTex)
-- Amaz.LOGI('zglog', 'reverseSort '..(self.reverseSort and 1 or 0))
    self.material_rotate:setFloat("rotate", 90 - self.rotate);
    self.material_mask:setFloat("randomly", self.randomly);
    self.material_mask:setFloat("threshold", self.threshold);
    self.material_mask:setFloat("sortType", self.sortType);
    self.material_mask:setFloat("affectType", self.affectType);
    self.material_mask:setFloat("triggerType", self.triggerType);
    self.material_mask:setFloat("randomSeed", self.randomSeed);
    self.material_mask:setFloat("blockSize", self.blockSize*50);
    self.material_mask_refine:setFloat("offset", self.offset);
    self.material_mask_refine:setFloat("offsetRandom", self.offsetRandom);
    self.material_mask_refine:setFloat("randomSeed", self.randomSeed);
    self.material_mask_refine:setFloat("maxLength", self.length);
    self.material_sort:setFloat("reverseSort",  self.reverseSort and 1 or 0);
    self.material_sort:setFloat("cycle", self.cycle);
    self.material_scale:setFloat("rotate", 90 - self.rotate);
    self.material_scale:setFloat("featherStart", self.featherStart);
    self.material_scale:setFloat("featherEnd", self.featherEnd);
    self.material_scale:setFloat("blurSize", self.blurSize * 20);
    self.material_scale:setFloat("outputType", self.outputType);
    self.material_scale:setFloat("reverseSort", self.reverseSort and 1 or 0);
    self.material_scale:setFloat("cycle", self.cycle);
end

exports.PixelSort = PixelSort
return exports
