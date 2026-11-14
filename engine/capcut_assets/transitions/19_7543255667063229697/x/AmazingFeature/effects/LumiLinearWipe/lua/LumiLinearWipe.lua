local isEditor = (Amaz.Macros and Amaz.Macros.EditorSDK) and true or false
local exports = exports or {}
local LumiLinearWipe = LumiLinearWipe or {}
LumiLinearWipe.__index = LumiLinearWipe
---@class LumiLinearWipe : ScriptComponent
---@field progress number [UI(Range={0.0, 1.0}, Drag)]
---@field rotation number [UI(Range={-360, 360.0}, Drag)]
---@field feather number [UI(Range={0.0, 1.0}, Drag)]
---@field InputTex Texture
---@field OutputTex Texture
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
    if rt == nil or width <= 0 or height <= 0 then return end
    if rt.width ~= width or rt.height ~= height then
        rt.width = width
        rt.height = height
    end
end

function mapProgress(x) return x * 2. - 0.5 end

function LumiLinearWipe.new(construct, ...)
    local self = setmetatable({}, LumiLinearWipe)

    self.__lumi_type = "lumi_obj"
    self.__lumi_rt_pingpong_type = "custom"

    self.progress = 0
    self.rotation = 0
    self.feather = 0

    self.InputTex = nil
    self.OutputTex = nil

    return self
end

function LumiLinearWipe:setEffectAttr(key, value, comp)
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

function LumiLinearWipe:onStart(comp)
    self.entity = comp.entity
    self.TAG = AE_EFFECT_TAG .. ' ' .. self.entity.name
    Amaz.LOGI(self.TAG, 'onStart')

    self.camera = self.entity:searchEntity("CameraLinearWipe"):getComponent(
                      "Camera")
    self.material = self.entity:searchEntity("PassLinearWipe"):getComponent(
                        "MeshRenderer").material
end

function LumiLinearWipe:onUpdate(comp, deltaTime)
    if self.OutputTex then self.camera.renderTexture = self.OutputTex end

    local progress = mapProgress(self.progress)
    self.material:setTex("u_inputTexture", self.InputTex)
    self.material:setFloat("u_progress", progress)
    self.material:setFloat("u_rotation", self.rotation)
    self.material:setFloat("u_feather", self.feather)

end

exports.LumiLinearWipe = LumiLinearWipe
return exports
