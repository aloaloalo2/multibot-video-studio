local isEditor = (Amaz.Macros and Amaz.Macros.EditorSDK) and true or false
local exports = exports or {}
local LumiDropShadow = LumiDropShadow or {}
LumiDropShadow.__index = LumiDropShadow
---@class LumiDropShadow : ScriptComponent
---@field shadowColor Color [UI(NoAlpha)]
---@field shadowOpacity double [UI(Range={0, 1}, Drag)]
---@field shadowAngle double [UI(Range={-360, 360}, Drag)]
---@field shadowDistance double [UI(Range={0, 10000}, Drag)]
---@field width double [UI(Display="Width",Range={0, 10000}, Drag)]
---@field onlyShadow boolean
---@field InputTex Texture
---@field OutputTex Texture
---@field maskTex Texture
---@field defaultMaskTex Texture
---@field lumiSharedRt Vector [UI(Type="Texture")]

local AE_EFFECT_TAG = 'AE_EFFECT_TAG LumiTag'

local function createRenderTexture(width, height, filterMag, filterMin)
    local rt = Amaz.RenderTexture()
    rt.width = width
    rt.height = height
    rt.depth = 1
    rt.filterMag = filterMag or Amaz.FilterMode.LINEAR
    rt.filterMin = filterMin or Amaz.FilterMode.LINEAR
    rt.filterMipmap = Amaz.FilterMipmapMode.NONE
    rt.attachment = Amaz.RenderTextureAttachment.NONE
    return rt
end

local function updateTexSize(rt, width, height)
    if rt == nil or width <= 0 or height <= 0 then
        return
    end
    if rt.width ~= width or rt.height ~= height then
        rt.width = width
        rt.height = height
    end
end

function LumiDropShadow.new(construct, ...)
    local self = setmetatable({}, LumiDropShadow)

    self.__lumi_type = "lumi_obj"
    self.__lumi_rt_pingpong_type = "custom"

    self.shadowColor = Amaz.Color(1, 0, 0, 1)
    self.shadowOpacity = 1.0
    self.shadowAngle = 135
    self.shadowDistance = 5
    self.scale = 1
    self.width = 0
    self.onlyShadow = false

    self.InputTex = nil
    self.OutputTex = nil
    self.maskTex = nil
    self.defaultMaskTex = nil
    self.SIGMA = 2.5
    self.MAX_SOFT = 20
    return self
end

function LumiDropShadow:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value, _force)
        if _force or self[_key] ~= nil then
            self[_key] = _value
            if comp and comp.properties ~= nil then
                comp.properties:set(_key, _value)
            end
        end
    end

    if key == "maskTex" then
        _setEffectAttr(key, value, true)
    end

    if key == "upperBlendMode" or key == "lowerBlendMode" then
        value = math.max(0, math.min(value, #self.BLEND_QUERY))
        value = self.BLEND_QUERY[value]
        _setEffectAttr(key, value)
    else
        _setEffectAttr(key, value)
    end
end

function LumiDropShadow:onStart(comp)
    self.entity = comp.entity
    self.TAG = AE_EFFECT_TAG .. ' ' .. self.entity.name
    Amaz.LOGI(self.TAG, 'onStart')

    -- Use entity instead of scene
    self.camInput = self.entity:searchEntity("CameraInput"):getComponent("Camera")
    self.camBlurX = self.entity:searchEntity("CameraBlurX"):getComponent("Camera")
    self.camBlurY = self.entity:searchEntity("CameraBlurY"):getComponent("Camera")
    self.camLight = self.entity:searchEntity("CameraLight"):getComponent("Camera")
    self.matInput = self.entity:searchEntity("PassInput"):getComponent("MeshRenderer").material
    self.matBlurX = self.entity:searchEntity("PassBlurX"):getComponent("MeshRenderer").material
    self.matBlurY = self.entity:searchEntity("PassBlurY"):getComponent("MeshRenderer").material
    self.matLight = self.entity:searchEntity("PassLight"):getComponent("MeshRenderer").material
end

function LumiDropShadow:onUpdate(comp, deltaTime)
    -- set the input and output textures to be displayed
    if self.OutputTex then
        local midTex = self.lumiSharedRt and self.lumiSharedRt:get(0)
        if midTex then
            midTex.width = self.OutputTex.width
            midTex.height = self.OutputTex.height
        end
        self.matInput:setTex("u_inputTexture", self.InputTex)
        self.camInput.renderTexture = midTex
        self.matBlurX:setTex("u_inputTexture", midTex)
        self.camBlurX.renderTexture = self.OutputTex
        self.matBlurY:setTex("u_inputTexture", self.OutputTex)
        self.camBlurY.renderTexture = midTex
        self.matLight:setTex("u_inputTexture", self.InputTex)
        self.matLight:setTex("u_shadowTexture", midTex)
        self.matLight:setTex("u_depthTexture", midTex)

        local maskTex = self.maskTex
        if maskTex == nil then
            maskTex = self.defaultMaskTex
        end
        self.matLight:setTex("u_shadowMaskTexture", maskTex)

        self.camLight.renderTexture = self.OutputTex
        local screenScale = 1080 / math.min(midTex.width, midTex.height)
        self.screenWidth = midTex.width * screenScale
        self.screenHeight = midTex.height * screenScale
    end

    self.scale = self.screenWidth / (self.screenWidth + self.width * 2)
    self.matInput:setFloat("u_scale", self.scale)
    local radius = self.width * self.scale
    self.matBlurX:setFloat("u_radius", radius)
    self.matBlurX:setFloat("u_sigma", radius / self.SIGMA)
    self.matBlurX:setFloat("u_step", 1)
    self.matBlurY:setFloat("u_radius", radius)
    self.matBlurY:setFloat("u_sigma", radius / self.SIGMA)
    self.matBlurY:setFloat("u_step", 1)

    self.matLight:setFloat("u_scale", self.scale)
    self.matLight:setVec4("u_color", Amaz.Vector4f(self.shadowColor.r, self.shadowColor.g, self.shadowColor.b, 1.0))
    self.matLight:setFloat("u_opacity", self.shadowOpacity)
    self.matLight:setFloat("u_angle", self.shadowAngle)
    self.matLight:setFloat("u_distance",
        (self.shadowDistance / 1080) * math.min(self.OutputTex.width, self.OutputTex.height))
    self.matLight:setVec2("u_screenSize", Amaz.Vector2f(self.screenWidth, self.screenHeight))

    if self.onlyShadow then
        self.matLight:setFloat("u_inputOpacity", 0)
    else
        self.matLight:setFloat("u_inputOpacity", 1)
    end
end

exports.LumiDropShadow = LumiDropShadow
return exports
