local isEditor = (Amaz.Macros and Amaz.Macros.EditorSDK) and true or false
local exports = exports or {}
local LumiFlicker = LumiFlicker or {}
LumiFlicker.__index = LumiFlicker
---@class LumiFlicker : ScriptComponent
---@field amp0 double [UI(Display="Global Amp", Range={0, 10}, Drag)]
---@field ampRL double [UI(Display="Rand Luma Amp", Range={0, 100}, Drag)]
---@field ampRC double [UI(Display="Rand Color Amp", Range={0, 100}, Drag)]
---@field frqR double [UI(Display="Rand Freq", Range={0, 60}, Drag)]
---@field ampW double [UI(Display="Wave Amp", Range={0, 100}, Drag)]
---@field frqW double [UI(Display="Wave Freq", Range={0, 60}, Drag)]
---@field phaseR double [UI(Display="Wave Phase R", Range={-1, 1}, Drag)]
---@field phaseG double [UI(Display="Wave Phase G", Range={-1, 1}, Drag)]
---@field phaseB double [UI(Display="Wave Phase B", Range={-1, 1}, Drag)]
---@field ampR double [UI(Display="Amp R", Range={0, 100}, Drag)]
---@field ampG double [UI(Display="Amp G", Range={0, 100}, Drag)]
---@field ampB double [UI(Display="Amp B", Range={0, 100}, Drag)]
---@field brightness double [UI(Display="Brightness", Range={0, 100}, Drag)]
---@field seed double [UI(Display="Rand Seed", Range={0, 5}, Drag)]
---@field InputTex Texture
---@field OutputTex Texture

local AE_EFFECT_TAG = 'AE_EFFECT_TAG LumiTag'

function LumiFlicker.new(construct, ...)
    local self = setmetatable({}, LumiFlicker)

    self.__lumi_type = "lumi_obj"
    self.__lumi_rt_pingpong_type = "custom"

    self.InputTex = nil
    self.OutputTex = nil

    self.amp0 = 0.2
    self.ampRL = 1
    self.ampRC = 0
    self.frqR = 30
    self.ampW = 0
    self.frqW = 5
    self.phaseR = 0
    self.phaseG = 0
    self.phaseB = 0
    self.ampR = 1
    self.ampG = 1
    self.ampB = 1
    self.brightness = 1
    self.seed = 1

    self.curTime = 0
    return self
end

function LumiFlicker:setEffectAttr(key, value, comp)
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

function LumiFlicker:onStart(comp)
    self.entity = comp.entity
    self.TAG = AE_EFFECT_TAG .. ' ' .. self.entity.name
    Amaz.LOGI(self.TAG, 'onStart')

    -- Use entity instead of scene
    self.cam = self.entity:searchEntity("CameraFlicker"):getComponent("Camera")
    self.mat = self.entity:searchEntity("PassFlicker"):getComponent("MeshRenderer").material
end

function LumiFlicker:onUpdate(comp, deltaTime)
    self.mat:setTex("u_inputTexture", self.InputTex)
    self.cam.renderTexture = self.OutputTex

    self.mat:setFloat("u_amp0", self.amp0)
    self.mat:setFloat("u_ampR", self.ampR)
    self.mat:setFloat("u_ampG", self.ampG)
    self.mat:setFloat("u_ampB", self.ampB)
    self.mat:setFloat("u_brightness", self.brightness)

    self.mat:setFloat("u_ampRL", self.ampRL)
    self.mat:setFloat("u_ampRC", self.ampRC)
    self.mat:setFloat("u_frqR", self.frqR)
    self.mat:setFloat("u_seed", self.seed)

    self.mat:setFloat("u_ampW", self.ampW)
    self.mat:setFloat("u_frqW", self.frqW)
    self.mat:setFloat("u_phaseR", self.phaseR)
    self.mat:setFloat("u_phaseG", self.phaseG)
    self.mat:setFloat("u_phaseB", self.phaseB)

    if Editor then
        self.aeTime = self.curTime
    end
    self.mat:setFloat("u_time", self.curTime)
end

exports.LumiFlicker = LumiFlicker
return exports
