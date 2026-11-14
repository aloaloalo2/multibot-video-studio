      
local isEditor = (Amaz.Macros and Amaz.Macros.EditorSDK) and true or false
local exports = exports or {}
local LumiTritone = LumiTritone or {}
LumiTritone.__index = LumiTritone
---@class LumiTritone : ScriptComponent
---@field InputTex Texture
---@field OutputTex Texture
---@field highlightColor Color [UI(NoAlpha)]
---@field middleColor Color [UI(NoAlpha)]
---@field shadowColor Color [UI(NoAlpha)]
---@field oriAlpha double [UI(Range={0, 1}, Drag)]

function LumiTritone.new(construct, ...)
    local self = setmetatable({}, LumiTritone)

    if construct and LumiTritone.constructor then LumiTritone.constructor(self, ...) end

    self.InputTex = nil
    self.OutputTex = nil

    self.highlightColor = Amaz.Color(1., 1., 1.)
    self.middleColor = Amaz.Color(0.5, 0.4, 0.3)
    self.shadowColor = Amaz.Color(0., 0., 0.)
    self.oriAlpha = 0.0

    return self
end

function LumiTritone:constructor()
end

function LumiTritone:onStart(comp)
    self.camera = comp.entity:searchEntity("BlitCamera"):getComponent("Camera")
    self.material = comp.entity:searchEntity("BlitPass"):getComponent("MeshRenderer").material
end

function LumiTritone:onUpdate(comp, deltaTime)
    if self.OutputTex then
        self.camera.renderTexture = self.OutputTex
    end
    self.material:setTex("u_InputTexture", self.InputTex)

    self.material:setFloat('u_oriAlpha', self.oriAlpha)
    self.material:setVec4("u_shadowColor", Amaz.Vector4f(self.shadowColor.r, self.shadowColor.g, self.shadowColor.b, 1.0))
    self.material:setVec4("u_middleColor", Amaz.Vector4f(self.middleColor.r, self.middleColor.g, self.middleColor.b, 1.0))
    self.material:setVec4("u_highlightColor", Amaz.Vector4f(self.highlightColor.r, self.highlightColor.g, self.highlightColor.b, 1.0))
end

exports.LumiTritone = LumiTritone
return exports
