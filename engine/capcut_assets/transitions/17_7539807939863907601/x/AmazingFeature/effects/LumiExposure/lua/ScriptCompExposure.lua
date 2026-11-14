---@class ScriptCompExposure: ScriptComponent
---@field channelType string [UI(Option={"Main Channels", "Single Channel"})]
---@field exposure number [UI(Range={-10., 10.}, Drag)]
---@field offset number [UI(Range={-2., 2.}, Drag)]
---@field grayscaleCorrection number [UI(Range={0.1, 10.}, Drag)]
---@field redExposure number [UI(Range={-10., 10.}, Drag)]
---@field redOffset number [UI(Range={-2., 2.}, Drag)]
---@field redGrayscaleCorrection number [UI(Range={0.1, 10.}, Drag)]
---@field greenExposure number [UI(Range={-10., 10.}, Drag)]
---@field greenOffset number [UI(Range={-2., 2.}, Drag)]
---@field greenGrayscaleCorrection number [UI(Range={0.1, 10.}, Drag)]
---@field blueExposure number [UI(Range={-10., 10.}, Drag)]
---@field blueOffset number [UI(Range={-2., 2.}, Drag)]
---@field blueGrayscaleCorrection number [UI(Range={0.1, 10.}, Drag)]
---@field noUseLinearLight boolean
---@field InputTex Texture
---@field OutputTex Texture

local exports = exports or {}
local ScriptCompExposure = ScriptCompExposure or {}
ScriptCompExposure.__index = ScriptCompExposure

------------ util functions ------------
local function clamp(value, min, max)
    --[[
        Description: clamp value between [min, max]
    ]]
    return math.min(math.max(value, min), max)
end

local function boolToInt(flag)
    --[[
        Description: convert flag from bool to int
    ]]
    if flag then return 1 end
    return 0
end

------------ class functions for ScriptComponent ------------
function ScriptCompExposure.new(construct, ...)
    local self = setmetatable({}, ScriptCompExposure)

    if construct and ScriptCompExposure.constructor then ScriptCompExposure.constructor(self, ...) end
    -- user parameters
    -- user parameters
    self.channelType = "Main Channels"
    self.exposure = 0.
    self.offset = 0.
    self.grayscaleCorrection = 1.

    self.redExposure = 0.
    self.redOffset = 0.
    self.redGrayscaleCorrection = 1.

    self.greenExposure = 0.
    self.greenOffset = 0.
    self.greenGrayscaleCorrection = 1.

    self.blueExposure = 0.
    self.blueOffset = 0.
    self.blueGrayscaleCorrection = 1.

    self.noUseLinearLight = false   -- use linear space by applying inverse gamma correction

    -- other parameters
    self.first = nil
    self.MinExposure = -10.
    self.MaxExposure = 10.
    self.MinOffset = -2.
    self.MaxOffset = 2.
    self.MinGrayscaleCorrection = 0.1
    self.MaxGrayscaleCorrection = 10.
    self.Gamma = 2.2

    return self
end

function ScriptCompExposure:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value, _comp)
        if self[_key] ~= nil then
            self[_key] = _value
            if _comp and _comp.properties ~= nil then
                _comp.properties:set(_key, _value)
            end
        end
    end

    if key == "channelType" then
        local typeTable = {
            [0] = "Main Channels",
            [1] = "Single Channel",
        }
        local channelType = typeTable[value]
        if channelType == nil then channelType = "Main Channels" end
        _setEffectAttr(key, channelType, comp)
    elseif key == "exposure"
        or key == "offset"
        or key == "grayscaleCorrection"
        or key == "redExposure"
        or key == "redOffset"
        or key == "redGrayscaleCorrection"
        or key == "greenExposure"
        or key == "greenOffset"
        or key == "greenGrayscaleCorrection"
        or key == "blueExposure"
        or key == "blueOffset"
        or key == "blueGrayscaleCorrection"
        or key == "noUseLinearLight"
    then
        _setEffectAttr(key, value, comp)
    else
        _setEffectAttr(key, value, comp)
    end
end

function ScriptCompExposure:onStart(comp)
    self.matExposure = comp.entity:searchEntity("EntityExposure"):getComponent("MeshRenderer").material
    self.camExposure = comp.entity:searchEntity("CameraExposure"):getComponent("Camera")
end

function ScriptCompExposure:onUpdate(comp, deltaTime)
    -- prepare parameters
    local noUseLinearLight = boolToInt(self.noUseLinearLight)
    self.exposure = clamp(self.exposure, self.MinExposure, self.MaxExposure)
    self.offset = clamp(self.offset, self.MinOffset, self.MaxOffset)
    self.grayscaleCorrection = clamp(self.grayscaleCorrection, self.MinGrayscaleCorrection, self.MaxGrayscaleCorrection)

    self.redExposure = clamp(self.redExposure, self.MinExposure, self.MaxExposure)
    self.redOffset = clamp(self.redOffset, self.MinOffset, self.MaxOffset)
    self.redGrayscaleCorrection = clamp(self.redGrayscaleCorrection, self.MinGrayscaleCorrection, self.MaxGrayscaleCorrection)

    self.greenExposure = clamp(self.greenExposure, self.MinExposure, self.MaxExposure)
    self.greenOffset = clamp(self.greenOffset, self.MinOffset, self.MaxOffset)
    self.greenGrayscaleCorrection = clamp(self.greenGrayscaleCorrection, self.MinGrayscaleCorrection, self.MaxGrayscaleCorrection)

    self.blueExposure = clamp(self.blueExposure, self.MinExposure, self.MaxExposure)
    self.blueOffset = clamp(self.blueOffset, self.MinOffset, self.MaxOffset)
    self.blueGrayscaleCorrection = clamp(self.blueGrayscaleCorrection, self.MinGrayscaleCorrection, self.MaxGrayscaleCorrection)

    -- set InputTex, OutputTex
    self.camExposure.renderTexture = self.OutputTex
    self.matExposure:setTex("u_inputTexture", self.InputTex)

    -- set parameters for materials (according to channelType)
    if self.channelType == "Main Channels" then
        self.matExposure:setFloat("u_redExposure", self.exposure)
        self.matExposure:setFloat("u_redOffset", self.offset)
        self.matExposure:setFloat("u_redGrayscaleCorrection", self.grayscaleCorrection)

        self.matExposure:setFloat("u_greenExposure", self.exposure)
        self.matExposure:setFloat("u_greenOffset", self.offset)
        self.matExposure:setFloat("u_greenGrayscaleCorrection", self.grayscaleCorrection)

        self.matExposure:setFloat("u_blueExposure", self.exposure)
        self.matExposure:setFloat("u_blueOffset", self.offset)
        self.matExposure:setFloat("u_blueGrayscaleCorrection", self.grayscaleCorrection)
    else
        self.matExposure:setFloat("u_redExposure", self.redExposure)
        self.matExposure:setFloat("u_redOffset", self.redOffset)
        self.matExposure:setFloat("u_redGrayscaleCorrection", self.redGrayscaleCorrection)

        self.matExposure:setFloat("u_greenExposure", self.greenExposure)
        self.matExposure:setFloat("u_greenOffset", self.greenOffset)
        self.matExposure:setFloat("u_greenGrayscaleCorrection", self.greenGrayscaleCorrection)

        self.matExposure:setFloat("u_blueExposure", self.blueExposure)
        self.matExposure:setFloat("u_blueOffset", self.blueOffset)
        self.matExposure:setFloat("u_blueGrayscaleCorrection", self.blueGrayscaleCorrection)
    end

    self.matExposure:setFloat("u_gamma", self.Gamma)
    self.matExposure:setInt("u_noUseLinearLight", noUseLinearLight)
end

exports.ScriptCompExposure = ScriptCompExposure
return exports
