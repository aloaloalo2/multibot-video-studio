local exports = exports or {}
local Grain = Grain or {}
Grain.__index = Grain
---@class Grain: ScriptComponent
---@field combine string [UI(Option={"Screen", "Add", "Mult", "Overlay", "Film", "Difference"})]
---@field brightness double [UI(Range={-1, 1}, Drag)]
---@field contrast double [UI(Range={-1, 1}, Drag)]
---@field saturation double [UI(Range={0, 1}, Drag)]
---@field grainIntensity double [UI(Range={0, 10}, Drag)]
---@field intensityR double [UI(Range={0, 10}, Drag)]
---@field intensityG double [UI(Range={0, 10}, Drag)]
---@field intensityB double [UI(Range={0, 10}, Drag)]
---@field scale double [UI(Range={0.22, 1}, Drag)]
---@field scaleR double [UI(Range={0.2, 1}, Drag)]
---@field scaleG double [UI(Range={0.2, 1}, Drag)]
---@field scaleB double [UI(Range={0.2, 1}, Drag)]
---@field interval double [UI(Range={0, 1}, Drag)]
---@field monochrome Bool
---@field speed double [UI(Range={0, 1}, Drag)]
---@field quality double [UI(Range={0, 1}, Drag)]
---@field InputTex Texture
---@field OutputTex Texture

local Combine = {
    Screen = 0, Add = 1, Mult = 2, Overlay = 3, Film = 4, Difference = 5
}

local function remap(value, min, max, newMin, newMax)
    return (value - min) / (max - min) * (newMax - newMin) + newMin
end

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

function Grain.new(construct, ...)
    local self = setmetatable({}, Grain)

    if construct and Grain.constructor then Grain.constructor(self, ...) end

    self.InputTex = nil
    self.OutputTex = nil

    self.combine = 'Film'
    self.grainIntensity = 1.0
    self.intensityR = 1.0
    self.intensityG = 1.0
    self.intensityB = 1.0
    self.scale = 0.3
    self.scaleR = 1
    self.scaleG = 1
    self.scaleB = 1
    self.monochrome = false
    self.curTime = 0.0
    self.interval = 0
    self.speed = 0.1
    self.quality = 1

    return self
end

function Grain:onStart(comp)
    self.noiseMat = comp.entity:searchEntity('NoisePass'):getComponent('MeshRenderer').material
    self.noiseCam = comp.entity:searchEntity('NoiseCamera'):getComponent('Camera')
    self.blitEntity = comp.entity:searchEntity('BlitCamera')
    self.blitCam = self.blitEntity:getComponent('Camera')
    self.blitMat = self.blitEntity:searchEntity('BlitPass'):getComponent('MeshRenderer').material
end

local function clamp(val, min, max)
    return math.max(math.min(val, max), min)
end

function Grain:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value)
        if self[_key] ~= nil then
            self[_key] = _value
            if comp and comp.properties ~= nil then
                comp.properties:set(_key, _value)
            end
        end
    end

    if key == "combine" then
        local combine = "Screen"
        if     value == 1 then combine = "Add"
        elseif value == 2 then combine = "Mult"
        elseif value == 3 then combine = "Overlay"
        elseif value == 4 then combine = "Film"
        end
        _setEffectAttr(key, combine)
    else
        _setEffectAttr(key, value)
    end
end

function Grain:onUpdate(comp, deltaTime)
    local props = comp.properties
    
    local speed = self.curTime * (self.speed / 10)
    if self.lastTime then
        if self.curTime - self.lastTime >= self.interval
        or self.curTime < self.lastTime
        then
            self.seed = speed
            self.lastTime = self.curTime
        end
    else
        self.lastTime = self.curTime
        self.seed = speed
    end

    self.noiseMat:setFloat('u_seed', self.seed)

    if self.quality < 1 and self.OutputTex.width > 360 then
        self.blitEntity.visible = true
        local w = self.OutputTex.width
        local h = self.OutputTex.height

        local scale = remap(self.quality, 0, 1, 360 / w, 1)
        w = math.floor(w * scale)
        h = math.floor(h * scale)
        if self.midTex == nil
        or self.midTex.width ~= w
        or self.midTex.height ~= h
        then
            self.midTex = createRenderTexture(w, h)
        end
        self.noiseCam.renderTexture = self.midTex
        self.noiseMat:setInt('u_onlyNoise', 1)
        self.blitCam.renderTexture = self.OutputTex
        self.blitMat:setTex('u_noiseTexture', self.midTex)
        self.blitMat:setTex('u_inputTexture', self.InputTex)
        self.blitMat:setFloat('u_intensity', self.grainIntensity / 10)
        self.blitMat:setFloat('u_intensityR', self.intensityR / 10)
        self.blitMat:setFloat('u_intensityG', self.intensityG / 10)
        self.blitMat:setFloat('u_intensityB', self.intensityB / 10)
        self.blitMat:setInt('u_combine', Combine[self.combine])
    else
        self.blitEntity.visible = false
        if self.midTex ~= nil then
            self.midTex.width = 1
            self.midTex.height = 1
            self.midTex = nil
        end
        self.noiseMat:setTex('u_InputTexture', self.InputTex)
        self.noiseMat:setInt('u_onlyNoise', 0)
        self.noiseCam.renderTexture = self.OutputTex

        self.noiseMat:setFloat('u_intensity', self.grainIntensity / 10)
        self.noiseMat:setFloat('u_intensityR', self.intensityR / 10)
        self.noiseMat:setFloat('u_intensityG', self.intensityG / 10)
        self.noiseMat:setFloat('u_intensityB', self.intensityB / 10)
        self.noiseMat:setInt('u_combine', Combine[self.combine])
    end
    -- Amaz.LOGS("tqh-log", "w: ".. self.noiseCam.renderTexture.width .. ", h: ".. self.noiseCam.renderTexture.height)

    self.noiseMat:setFloat('u_scale', self.scale)
    self.noiseMat:setFloat('u_scaleR', self.scaleR)
    self.noiseMat:setFloat('u_scaleG', self.scaleG)
    self.noiseMat:setFloat('u_scaleB', self.scaleB)
    self.noiseMat:setInt('u_monochrome', (self.monochrome and {1} or {0})[1])
    self.noiseMat:setFloat('u_Brightness', self.brightness)
    self.noiseMat:setFloat('u_Contrast', self.contrast)
    self.noiseMat:setFloat('u_Saturation', self.saturation)
end

exports.Grain = Grain
return exports
