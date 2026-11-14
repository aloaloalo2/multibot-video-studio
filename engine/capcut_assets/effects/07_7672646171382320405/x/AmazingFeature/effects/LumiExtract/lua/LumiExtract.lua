      
local isEditor = (Amaz.Macros and Amaz.Macros.EditorSDK) and true or false
local exports = exports or {}
local LumiExtract = LumiExtract or {}
LumiExtract.__index = LumiExtract
---@class LumiExtract : ScriptComponent
---@field InputTex Texture
---@field OutputTex Texture
---@field blackField double [UI(Range={0, 255}, Drag)]
---@field blackSoft double [UI(Range={0, 255}, Drag)]
---@field whiteField double [UI(Range={0, 255}, Drag)]
---@field whiteSoft double [UI(Range={0, 255}, Drag)]
---@field reverse Bool

function LumiExtract.new(construct, ...)
    local self = setmetatable({}, LumiExtract)

    if construct and LumiExtract.constructor then LumiExtract.constructor(self, ...) end

    self.InputTex = nil
    self.OutputTex = nil

    self.blackField = 0.0
    self.blackSoft = 0.0
    self.whiteField = 1.0
    self.whiteSoft = 0.0
    self.reverse = false

    return self
end

function LumiExtract:constructor()
end

function LumiExtract:onStart(comp)
    self.camera = comp.entity:searchEntity("BlitCamera"):getComponent("Camera")
    self.material = comp.entity:searchEntity("BlitPass"):getComponent("MeshRenderer").material
end

function LumiExtract:onUpdate(comp, deltaTime)
    if self.OutputTex then
        self.camera.renderTexture = self.OutputTex
    end
    self.material:setTex("u_InputTexture", self.InputTex)

    self.material:setFloat('u_BlackField', self.blackField/255.)
    self.material:setFloat('u_BlackSoft', self.blackSoft/255.)
    self.material:setFloat('u_WhiteField', self.whiteField/255.)
    self.material:setFloat('u_WhiteSoft', self.whiteSoft/255.)
    self.material:setFloat('u_Reverse', self.reverse and 1 or 0)
end

exports.LumiExtract = LumiExtract
return exports
