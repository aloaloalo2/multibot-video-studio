local isEditor = (Amaz.Macros and Amaz.Macros.EditorSDK) and true or false
local exports = exports or {}
local LumiBCC_Prism = LumiBCC_Prism or {}
LumiBCC_Prism.__index = LumiBCC_Prism
---@class LumiBCC_Prism : ScriptComponent
---@field globalTransform number
---@field smoothness number [UI(Range={0, 1.0}, Drag)]
---@field weight number [UI(Range={0, 1.0}, Drag)]
---@field center vector2f
---@field scaleStart number 
---@field scaleEnd number 
---@field angleStart number
---@field angleEnd number
---@field falloff number 
---@field offsetStart vector2f
---@field offsetEnd vector2f
---@field colorStart vector3f
---@field colorMid vector3f
---@field colorEnd vector3f
---@field InputTex Texture
---@field OutputTex Texture

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
local function mix(a,b,x)
    return a*(1.0-x)+b*x
end
function LumiBCC_Prism.new(construct, ...)
    local self = setmetatable({}, LumiBCC_Prism)
    self.scaleStart = 100
    self.scaleEnd = 100
    self.angleStart = 0
    self.angleEnd = 0
    self.falloff = 0
    self.globalTransform = 100.
    self.center = Amaz.Vector2f(0.5,0.5)
    self.smoothness = 0
    self.weight = 0
    self.offsetStart = Amaz.Vector2f(0.5,0.5)
    self.offsetEnd = Amaz.Vector2f(0.5,0.5)
    self.colorStart = Amaz.Color(1,0,0,1)
    self.colorMid = Amaz.Color(0,1,0,1)
    self.colorEnd = Amaz.Color(0,0,1,1)
    self.__lumi_type = "lumi_obj"
    self.__lumi_rt_pingpong_type = "custom"

    self.InputTex = nil
    self.OutputTex = nil

    return self
end

function LumiBCC_Prism:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value, _force)
        if _force or self[_key] ~= nil then
            self[_key] = _value
            if comp and comp.properties ~= nil then
                comp.properties:set(_key, _value)
            end
        end
    end

    _setEffectAttr(key, value)
end

function LumiBCC_Prism:onStart(comp)
    self.entity = comp.entity
    self.TAG = AE_EFFECT_TAG .. ' ' .. self.entity.name
    -- Amaz.LOGI(self.TAG, 'onStart')

    -- Use entity instead of scene 
    self.camera = self.entity:searchEntity("CameraBCC_Prism"):getComponent("Camera")
    self.material = self.entity:searchEntity("BCC_Prism"):getComponent("MeshRenderer").material

end

function LumiBCC_Prism:onUpdate(comp, deltaTime)
    -- set the input and output textures to be displayed
    if self.OutputTex then
        self.camera.renderTexture = self.OutputTex
    end
    local rtSize = mix(1.,0.5,self.globalTransform/10)
    rtSize = math.max(rtSize,0.4)
    self.camera.renderTexture.pecentX = rtSize
    self.camera.renderTexture.pecentY = rtSize
    self.material:setTex("u_inputTexture", self.InputTex)
    self.material:setFloat("u_scaleStart", self.scaleStart/100.)
    self.material:setFloat("u_scaleEnd", self.scaleEnd/100)

    self.material:setFloat("u_angleStart", math.rad(self.angleStart))
    self.material:setFloat("u_angleEnd", math.rad(self.angleEnd))
    self.material:setFloat("u_fallOff", self.falloff/100)
    self.material:setVec2("u_center", self.center)

    self.material:setFloat("u_weight", math.sqrt(self.weight))
    self.material:setFloat("u_smoothness", self.smoothness)
    self.material:setFloat("u_globalTransform", self.globalTransform/100)
    self.material:setVec2("u_offsetStart", self.offsetStart)
    self.material:setVec2("u_offsetEnd",self.offsetEnd)

    self.material:setVec3("u_colorEnd", Amaz.Vector3f(self.colorEnd.r, self.colorEnd.g, self.colorEnd.b))
    self.material:setVec3("u_colorMid",  Amaz.Vector3f(self.colorMid.r, self.colorMid.g, self.colorMid.b))
    self.material:setVec3("u_colorStart",  Amaz.Vector3f(self.colorStart.r, self.colorStart.g, self.colorStart.b))
end

exports.LumiBCC_Prism = LumiBCC_Prism
return exports
