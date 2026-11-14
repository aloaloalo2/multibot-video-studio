      
local isEditor = (Amaz.Macros and Amaz.Macros.EditorSDK) and true or false
local exports = exports or {}
local ExtractFrame = ExtractFrame or {}
ExtractFrame.__index = ExtractFrame
---@class ExtractFrame : ScriptComponent
---@field InputTex Texture
---@field OutputTex Texture
---@field fps double [UI(Range={0.01, 60}, Drag)]

local function createRT(width, height)  
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

function ExtractFrame.new(construct, ...)
    local self = setmetatable({}, ExtractFrame)

    if construct and ExtractFrame.constructor then ExtractFrame.constructor(self, ...) end

    self.InputTex = nil
    self.OutputTex = nil

    self.fps = 30
    self.cachedRtTime = -10000
    self.startTime = 0.0
    self.endTime = 6.0
    self.curTime = 0.0

    return self
end

function ExtractFrame:onStart(comp)
    self.blitCacheEntity = comp.entity:searchEntity("BlitCacheCamera")
    self.blitCacheCamera = comp.entity:searchEntity("BlitCacheCamera"):getComponent("Camera")
    self.blitOutCamera = comp.entity:searchEntity("BlitOutCamera"):getComponent("Camera")
    self.blitCacheMaterial = comp.entity:searchEntity("BlitCachePass"):getComponent("MeshRenderer").material
    self.blitOutMaterial = comp.entity:searchEntity("BlitOutPass"):getComponent("MeshRenderer").material
    
    self.width = Amaz.BuiltinObject:getInputTextureWidth()
    self.height = Amaz.BuiltinObject:getInputTextureHeight()
    if self.OutputTex then
        self.width = self.OutputTex.width
        self.height = self.OutputTex.height
    end
    self.cachedRt = createRT(self.width, self.height)
end

function ExtractFrame:updateMaterial()
    self.blitCacheMaterial:setTex("u_InputTexture", self.InputTex)
    self.blitCacheCamera.renderTexture = self.cachedRt
    self.blitOutMaterial:setTex("u_InputTexture", self.cachedRt)
    if self.OutputTex then
        self.blitOutCamera.renderTexture = self.OutputTex
    end
end

function ExtractFrame:onUpdate(comp, deltaTime)
    self.curTime = self.curTime + deltaTime
    if math.abs(self.curTime - self.cachedRtTime) > 1.0 / self.fps
    or self.curTime == self.cachedRtTime -- for slider changed
    then
        self.blitCacheEntity.visible = true
        self.cachedRtTime = self.curTime
    else
        self.blitCacheEntity.visible = false
    end
    local w = Amaz.BuiltinObject:getInputTextureWidth()
    local h = Amaz.BuiltinObject:getInputTextureHeight()
    if self.OutputTex then
        w = self.OutputTex.width
        h = self.OutputTex.height
    end
    if self.width ~= w or self.height ~= h then 
        self.cachedRt.width = w
        self.cachedRt.height = h
        self.width = w
        self.height = h
        self.blitCacheEntity.visible = true
        self.cachedRtTime = self.curTime
    end
    self:updateMaterial()
end

exports.ExtractFrame = ExtractFrame
return exports
