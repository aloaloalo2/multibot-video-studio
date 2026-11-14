local isEditor = (Amaz.Macros and Amaz.Macros.EditorSDK) and true or false
local exports = exports or {}
local LumiRoundCorner = LumiRoundCorner or {}
LumiRoundCorner.__index = LumiRoundCorner
---@class LumiRoundCorner : ScriptComponent
---@field fadeType string [UI(Option={"Outer", "Inner", "Both"})]
---@field radius double [UI(Display="Radius", Range={0, 256}, Drag)]
---@field fade double [UI(Display="Fade", Range={0, 256}, Drag)]
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
    if rt == nil or width <= 0 or height <= 0 then return end
    if rt.width ~= width or rt.height ~= height then
        rt.width = width
        rt.height = height
    end
end

function LumiRoundCorner.new(construct, ...)
    local self = setmetatable({}, LumiRoundCorner)

    self.__lumi_type = "lumi_obj"
    self.__lumi_rt_pingpong_type = "custom"

    self.InputTex = nil
    self.OutputTex = nil
    self.radius = 0
    self.fade = 0
    self.fadeType = "Outer"

    self.FADE_QUERY = {
        [0] = "Outer",
        "Inner",
        "Both",
        ["Outer"] = 0,
        ["Inner"] = 1,
        ["Both"] = 2
    }
    return self
end

function LumiRoundCorner:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value, _force)
        if _force or self[_key] ~= nil then
            self[_key] = _value
            if comp and comp.properties ~= nil then
                comp.properties:set(_key, _value)
            end
        end
    end

    if key == "fadeType" then
        value = math.max(0, math.min(value, #self.FADE_QUERY))
        value = self.FADE_QUERY[value]
        _setEffectAttr(key, value)
    else
        _setEffectAttr(key, value)
    end
end

function LumiRoundCorner:onStart(comp)
    self.entity = comp.entity
    self.TAG = AE_EFFECT_TAG .. ' ' .. self.entity.name
    Amaz.LOGI(self.TAG, 'onStart')

    self.camera = self.entity:searchEntity("RoundCornerCamera"):getComponent(
                      "Camera")
    self.material = self.entity:searchEntity("RoundCornerPass"):getComponent(
                        "MeshRenderer").material
end

function LumiRoundCorner:onUpdate(comp, deltaTime)
    local w = self.OutputTex.width
    local h = self.OutputTex.height
    if self.OutputTex then self.camera.renderTexture = self.OutputTex end
    self.material:setTex("u_inputTexture", self.InputTex)

    local halfMinEdge = math.min(w, h) * 0.5
    local radius = halfMinEdge * (self.radius / 256)
    self.material:setFloat("u_radius", radius)

    local fade0, fade1
    local type = self.FADE_QUERY[self.fadeType]
    if type == 2 then
        fade0 = -(halfMinEdge * 0.5 * self.fade / 256) - 0.05
        fade1 = halfMinEdge * 0.5 * self.fade / 256 + 0.05
    elseif type == 1 then
        fade0 = 0
        fade1 = halfMinEdge * self.fade / 256 + 0.1
    else
        fade0 = -(halfMinEdge * self.fade / 256) - 0.1
        fade1 = 0
    end
    self.material:setFloat("u_fade0", fade0)
    self.material:setFloat("u_fade1", fade1)
end

exports.LumiRoundCorner = LumiRoundCorner
return exports
