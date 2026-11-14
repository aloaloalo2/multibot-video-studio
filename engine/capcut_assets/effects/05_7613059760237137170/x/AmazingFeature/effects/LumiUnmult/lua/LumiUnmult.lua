---@class LumiUnmult : ScriptComponent
---@field unmult boolean
---@field InputTex Texture
---@field OutputTex Texture
local exports = exports or {}
local LumiUnmult = LumiUnmult or {}
LumiUnmult.__index = LumiUnmult

------------ class functions for ScriptComponent ------------
function LumiUnmult.new(construct, ...)
    local self = setmetatable({}, LumiUnmult)

    if construct and LumiUnmult.constructor then LumiUnmult.constructor(self, ...) end

    self.__lumi_type = "lumi_effect"
    self.__lumi_rt_pingpong_type = "custom"

    self.unmult = true

    self.InputTex = nil
    self.OutputTex = nil

    return self
end

function LumiUnmult:onStart(comp)
    self.matUnmult = comp.entity:searchEntity("PassUnmult"):getComponent("MeshRenderer").material
    self.camUnmult = comp.entity:searchEntity("CameraUnmult"):getComponent("Camera")
end

function LumiUnmult:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value, _comp)
        if self[_key] ~= nil then
            self[_key] = _value
            if _comp and _comp.properties ~= nil then
                _comp.properties:set(_key, _value)
            end
        end
    end

    _setEffectAttr(key, value, comp)
end

function LumiUnmult:onUpdate(comp, detalTime)

    self.matUnmult:setTex("u_inputTex", self.InputTex)
    if self.OutputTex then self.camUnmult.renderTexture = self.OutputTex end
    self.matUnmult:setInt("u_unmult", self.unmult and 1 or 0)
end

exports.LumiUnmult = LumiUnmult
return exports
