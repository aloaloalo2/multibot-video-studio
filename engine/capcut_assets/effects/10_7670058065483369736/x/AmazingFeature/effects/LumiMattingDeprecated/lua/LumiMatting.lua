local exports = exports or {}
local LumiMatting = LumiMatting or {}
LumiMatting.__index = LumiMatting
---@class LumiMatting: ScriptComponent
---@field outputType string [UI(Option={"Mask", "Segment", "Edge"})]
---@field maskColor Color
---@field coreWidth double [UI(Range={0, 100}, Drag)]
---@field dilateWidth int [UI(Range={0, 20}, Slider)]
---@field startY double [UI(Range={0, 1}, Drag)]
---@field endY double [UI(Range={0, 1}, Drag)]
---@field featherStart double [UI(Range={0, 1}, Drag)]
---@field featherEnd double [UI(Range={0, 1}, Drag)]
---@field maskAlpha Bool
---@field lineType string [UI(Option={"Point", "Line"})]
---@field InputTex Texture
---@field OutputTex Texture

local AE_EFFECT_TAG = 'AE_EFFECT_TAG LumiTag'

local EPS = 1e-5

local OutputType = {
    "Mask", "Segment", "Edge"
}
setmetatable(OutputType, {__index = function(_, _) return OutputType[1] end})

local OutputTypeIndex = {}
for index, value in ipairs(OutputType) do OutputTypeIndex[value] = index - 1 end
setmetatable(OutputTypeIndex, {
    __index = function(_, key)
        Amaz.LOGE(AE_EFFECT_TAG, "Unsupported output type: " .. key)
        return 0
    end
})

local LineType = {
    "Point", "Line"
}
setmetatable(LineType, {__index = function(_, _) return LineType[1] end})

local LineTypeIndex = {}
for index, value in ipairs(LineType) do LineTypeIndex[value] = index - 1 end
setmetatable(LineTypeIndex, {
    __index = function(_, key)
        Amaz.LOGE(AE_EFFECT_TAG, "Unsupported line type: " .. key)
        return 0
    end
})

function LumiMatting.createRT(width, height)  
    local rt = Amaz.RenderTexture()
    rt.width = width
    rt.height = height
    rt.depth = 1
    rt.filterMag = Amaz.FilterMode.LINEAR
    rt.filterMin = Amaz.FilterMode.LINEAR
    rt.filterMipmap = Amaz.FilterMipmapMode.NONE
    rt.attachment = Amaz.RenderTextureAttachment.NONE
    return rt
end

function LumiMatting.new(construct, ...)
    local self = setmetatable({}, LumiMatting)
    if construct and LumiMatting.constructor then
        LumiMatting.constructor(self, ...)
    end

    self.InputTex = nil
    self.OutputTex = nil

    self.algoSlot = 0

    return self
end

function LumiMatting:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value, _force)
        if _force or self[_key] ~= nil then
            self[_key] = _value
            if comp and comp.properties ~= nil then
                comp.properties:set(_key, _value)
            end
        end
    end

    if key == 'outputType' then
        local outputType = OutputType[value + 1]
        _setEffectAttr(key, outputType)
    elseif key == 'lineType' then
        local lineType = LineType[value + 1]
        _setEffectAttr(key, lineType)
    else
        _setEffectAttr(key, value)
    end
end

function LumiMatting:onStart(comp)
    self.entity = comp.entity
    self.TAG = AE_EFFECT_TAG .. ' ' .. self.entity.name
    self:start(comp)
end

function LumiMatting:start(comp)
    self.first = true
    self.properties = comp.properties
    self.camera = comp.entity:searchEntity("Camera_entity_matting"):getComponent("Camera")
    self.contourCamera = comp.entity:searchEntity("Camera_entity_contour"):getComponent("Camera")
    self.meshEntity = comp.entity:searchEntity("contour_renderer"):getComponent("MeshRenderer")
    self.material = comp.entity:searchEntity("matting_renderer"):getComponent("MeshRenderer").material
    self.contourMaterial = self.meshEntity.material
    self.contourRT = nil
    self.properties:set('algoSlot', self.algoSlot)
end

function LumiMatting:updateMaterial()
    if self.first == nil then
        return
    end
    self.camera.renderTexture = self.OutputTex
    self.material:setTex("u_albedo", self.InputTex)
    self.material:setInt('u_outputType', OutputTypeIndex[self.outputType]);
    self.material:setInt('u_maskAlpha', self.maskAlpha and 1 or 0);
    self.material:setVec3('u_maskColor', Amaz.Vector3f(self.maskColor.r, self.maskColor.g, self.maskColor.b));

    local hasBgMask = false
    local alg = Amaz.Algorithm.getAEAlgorithmResult()
    local algoNodeName = (self.algoSlot == 0) and 'matting_0' or 'matting_1'
    local graphName = self.entity.scene:getEffectName()
    if graphName == '' then
        graphName = 'AE2Effect_20260804113334164'
    end
    local res = alg:getAlgorithmInfo(graphName, algoNodeName, 'matting')
    if res then
        local rect = res:get('resultRect')
        if math.abs(rect.width) > EPS and math.abs(rect.height) > EPS then
            local bgMask = res:get('bg_mask').image
            local maskTex = self.material:getTex('u_mask')
            if bgMask and maskTex then
                maskTex:storage(bgMask)
                hasBgMask = true
            end
        end
    end
    self.material:setInt('u_hasBgMask', hasBgMask and 1 or 0)

    self.contourMaterial:setInt('u_lineType', LineTypeIndex[self.lineType]);
    self.contourMaterial:setTex('u_inputTex', self.InputTex)
    if self.outputType ~= 'Edge' then
        if self.contourRT ~= nil then
            self.contourRT.width = 1
            self.contourRT.height = 1
            self.contourRT = nil
        end
        self.contourCamera.entity.visible = false
    else
        if self.contourRT == nil then
            self.contourRT = self.createRT(self.OutputTex.width, self.OutputTex.height)
        end
        if self.contourRT.width ~= self.OutputTex.width or self.contourRT.height ~= self.OutputTex.height then
            self.contourRT.width = self.OutputTex.width
            self.contourRT.height = self.OutputTex.height
        end
        self.contourCamera.renderTexture = self.contourRT
        self.material:setTex("u_contour", self.contourRT)
        self.contourCamera.entity.visible = true
    end
end

function LumiMatting:onUpdate(comp, detalTime)
    if self.first == nil then
        self:start(comp)
    end
    self.properties = comp.properties
    self:updateMaterial()
end

exports.LumiMatting = LumiMatting
return exports
