local exports = exports or {}
local LumiDepth = LumiDepth or {}
LumiDepth.__index = LumiDepth
---@class LumiDepth: ScriptComponent
---@field opticalFlowWeight number [UI(Range={0, 1}, Drag)] 
---@field mapMode string [UI(Option={"Raw", "Gain"})]
---@field mapValueX double [UI(Range={0.0, 10.0}, Drag)]
---@field mapValueY double [UI(Range={0.0, 10.0}, Drag)]
---@field threshold Bool 
---@field minThreshold double [UI(Range={0.0, 1.0}, Drag)]
---@field maxThreshold double [UI(Range={0.0, 1.0}, Drag)]
---@field blurRadius double [UI(Range={0.0, 100.0}, Drag)]
---@field segment Bool
---@field invert Bool 
---@field quality double [UI(Range={0.0, 1.0}, Drag)]
---@field InputTex Texture
---@field OutputTex Texture
---@field lumiSharedRt Vector [UI(Type="Texture")]

local AE_EFFECT_TAG = 'AE_EFFECT_TAG LumiTag'

local EPS = 1e-5

local function createRenderTexture(width, height, useRenderTexture)
    local rt
    if useRenderTexture then
        rt = Amaz.RenderTexture()
        rt.attachment = Amaz.RenderTextureAttachment.NONE
    else
        rt = Amaz.Texture2D()
    end
    rt.depth = 1
    rt.width = width
    rt.height = height
    rt.filterMag = filterMag or Amaz.FilterMode.LINEAR
    rt.filterMin = filterMin or Amaz.FilterMode.LINEAR
    rt.filterMipmap = Amaz.FilterMipmapMode.NONE
    return rt
end

local function updateTexSize(rt, width, height)
    if rt == nil or width <= 0 or height <= 0 then return end
    if rt.width ~= width or rt.height ~= height then
        rt.width = width
        rt.height = height
    end
end

local function setRenderTexture(cam, rt) if rt then cam.renderTexture = rt end end

function LumiDepth.new(construct, ...)
    local self = setmetatable({}, LumiDepth)

    self.__lumi_type = "lumi_obj"
    self.__lumi_rt_pingpong_type = "custom"

    self.algoSlot = 0
    self.mapValueX = 1.23
    self.mapValueY = 2.0
    self.minThreshold = 0.
    self.maxThreshold = 1.

    self.threshold = false
    self.segment = false
    self.invert = false

    self.opticalFlowWeight = 0.7

    self.blurRadius = 10
    self.stride = 1.

    self.mapMode = "Raw"
    self.outputType = "Mask"

    self.MAPMODE = {[0] = "Raw", "Gain", ["Raw"] = 0, ["Gain"] = 1}

    self.quality = 0.5

    self.InputTex = nil
    self.OutputTex = nil

    return self
end

function LumiDepth:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value, _force)
        if _force or self[_key] ~= nil then
            self[_key] = _value
            if comp and comp.properties ~= nil then
                comp.properties:set(_key, _value)
            end
        end
    end

    if key == 'mapMode' then
        value = math.max(0, math.min(value, #self.MAPMODE))
        _setEffectAttr(key, self.MAPMODE[value])
    else
        _setEffectAttr(key, value)
    end
end

function LumiDepth:onStart(comp)
    self.entity = comp.entity
    self.TAG = AE_EFFECT_TAG .. ' ' .. self.entity.name
    Amaz.LOGI(self.TAG, 'onStart')

    self.camDepth = comp.entity:searchEntity("CameraDepth"):getComponent(
                        "Camera")
    self.matDepth = comp.entity:searchEntity("PassDepth"):getComponent(
                        "MeshRenderer").material
    self.matBlurX = comp.entity:searchEntity("PassBlurX"):getComponent(
                        "MeshRenderer").material
    self.camBlurX = comp.entity:searchEntity("CameraBlurX"):getComponent(
                        "Camera")
    self.matBlurY = comp.entity:searchEntity("PassBlurY"):getComponent(
                        "MeshRenderer").material
    self.camBlurY = comp.entity:searchEntity("CameraBlurY"):getComponent(
                        "Camera")

    if self.lumiSharedRt and self.lumiSharedRt:size() > 0 then
        self.depthTex = self.lumiSharedRt:get(0)
    end

    local w = self.OutputTex.width * self.quality
    local h = self.OutputTex.height * self.quality
    self.blurTex = createRenderTexture(w, h, true)
    self.depthImage = createRenderTexture(w, h, false)
    self.matDepth:setTex("u_depthTex", self.depthImage)
end

function LumiDepth:onUpdate(comp, deltaTime)
    local w = self.OutputTex.width
    local h = self.OutputTex.height
    updateTexSize(self.depthTex, w, h)
    updateTexSize(self.blurTex, w * self.quality, h * self.quality)

    -- Depth
    setRenderTexture(self.camDepth, self.depthTex)
    setRenderTexture(self.camBlurX, self.blurTex)
    setRenderTexture(self.camBlurY, self.OutputTex)

    self.matDepth:setInt('u_invert', self.invert and 1 or 0)
    self.matDepth:setInt('u_threshold', self.threshold and 1 or 0)
    self.matDepth:setInt('u_mapMode', self.MAPMODE[self.mapMode])
    self.matDepth:setVec2('u_mapVal',
                          Amaz.Vector2f(self.mapValueX, self.mapValueY))
    self.matDepth:setFloat('u_minThreshold', 1.0 - self.minThreshold)
    self.matDepth:setFloat('u_maxThreshold', 1.0 - self.maxThreshold)

    -- Algorithm
    local alg = Amaz.Algorithm.getAEAlgorithmResult()
    local graphName = self.entity.scene:getEffectName()
    local algoNodeName_depth = (self.algoSlot == 0) and 'depth_0' or 'depth_1'
    if graphName == '' then graphName = "AE2Effect" end

    if alg ~= nil then
        Amaz.Algorithm.setAlgorithmParamFloat(graphName, algoNodeName_depth,
                                              "depth_optical_flow_weight",
                                              self.opticalFlowWeight)
        local res = alg:getAlgorithmInfo(graphName, algoNodeName_depth, 'depth')
        if res then
            local rect = res:get('depthEstimation')
            if math.abs(rect.width) > EPS and math.abs(rect.height) > EPS then
                local depthTex = rect.image
                local depthMat = self.matDepth:getTex('u_depthTex')
                if depthTex and depthMat then
                    depthMat:storage(depthTex)
                end
            end
        end
    end

    -- Blur
    local steps = math.max(self.blurRadius, 1)
    local stride = 1.0
    self.matBlurX:setTex("u_inputTex", self.depthTex)
    self.matBlurX:setInt("u_steps", steps)
    self.matBlurX:setFloat("u_stride", stride)
    self.matBlurX:setFloat("u_angle", math.rad(0))
    self.matBlurY:setTex("u_inputTex", self.InputTex)
    self.matBlurY:setTex("u_depthTex", self.blurTex)
    self.matBlurY:setInt("u_steps", steps)
    self.matBlurY:setFloat("u_stride", stride)
    self.matBlurY:setFloat("u_angle", math.rad(90))
    self.matBlurY:setInt("u_segment", self.segment and 1 or 0)
end

exports.LumiDepth = LumiDepth
return exports
