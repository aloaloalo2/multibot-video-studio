---@class ScriptCompOpticsCompensation: ScriptComponent
---@field fov number [UI(Range={0., 180.}, Drag)]
---@field fovOrientation string [UI(Option={"Horizontal", "Vertival", "Diagonal"})]
---@field center Vector2f
---@field inverseLensDistortion boolean
---@field antiAliasing boolean
---@field fillBorders boolean
---@field InputTex Texture
---@field OutputTex Texture
---@field lumiSharedRt Vector [UI(Type="Texture")]

local exports = exports or {}
local ScriptCompOpticsCompensation = ScriptCompOpticsCompensation or {}
ScriptCompOpticsCompensation.__index = ScriptCompOpticsCompensation

------------ util functions ------------
local function clamp(value, min, max)
    --[[
        Description: clamp value between [min, max]
    ]]
    return math.min(math.max(value, min), max)
end

local function getFovXYScale(width, height, fovOrientation)
    --[[
        Description: get XY scale for adjusting distortion scale.
    ]]
    local size = 1.
    if fovOrientation == "Horizontal" then
        size = width
    elseif fovOrientation == "Vertival" then
        size = height
    else
        size = math.sqrt(width * width + height * height)
    end

    local xScale = width / size
    local yScale = height / size
    return xScale, yScale
end

local function getBarrelDistortParam(fovIntensity)
    --[[
        Description: mapping from fovIntensity to two distort parameters for barrel distortion.
            fovIntensity is between [0, 1].
    ]]
    local k1 = 0.
    local k2 = 0.
    if fovIntensity <= 0.5 then
        k2 = 22.759 * fovIntensity ^ 3.167 + 0.431 * fovIntensity
    elseif fovIntensity <= 0.9 then
        k2 = (1.6583124 + 9.085 * (fovIntensity - 0.5) + 1914.57 * (fovIntensity - 0.5) ^ 6.15) ^ 2.0
    else
        k1 = (67 * (fovIntensity - 0.9)) ^ 4.0
        k2 = (1.6583124 + 9.085 * 0.4 + 1914.57 * 0.4 ^ 6.15) ^ 2.0
        if math.abs(fovIntensity - 1.0) < 1e-5 then
            k1 = 5000.0
        end
    end
    return k1, k2
end

local function getPincushionDistortParam(fovIntensity)
    --[[
        Description: mapping from fovIntensity to two distort parameters for pincushion distortion.
            fovIntensity is between [0, 1].
    ]]
    local k1 = 0.
    local k2 = 0.
    local x2 = 150. / 180.
    local x3 = 178. / 180.
    local x4 = 179.9 / 180.

    k1 = 14.77 * fovIntensity ^ 10.0 + 2.7 * fovIntensity ^ 3.0
    k2 = 3.82 * fovIntensity ^ 2.54 + 0.529 * fovIntensity
    if fovIntensity > x2 then
        if fovIntensity < x3 then
            k1 = 218.48 * fovIntensity ^ 73.79 - 54.266 + 69.83 * fovIntensity
        elseif fovIntensity < x4 then
            k1 = (658.399 * (fovIntensity - x3)) ^ 4.0 + 110.58
        else
            k1 = (33162 * (fovIntensity - x4)) ^ 4.0 + 2443.4
        end
    end

    return k1, k2
end

local function boolToInt(flag)
    --[[
        Description: convert flag from bool to int
    ]]
    if flag then
        return 1
    end
    return 0
end

------------ class functions for ScriptComponent ------------
function ScriptCompOpticsCompensation.new(construct, ...)
    local self = setmetatable({}, ScriptCompOpticsCompensation)

    if construct and ScriptCompOpticsCompensation.constructor then
        ScriptCompOpticsCompensation.constructor(self, ...)
    end
    -- user parameters
    self.fov = 0.
    self.fovOrientation = "Horizontal"
    self.center = Amaz.Vector2f(0.5, 0.5)
    self.inverseLensDistortion = false
    self.antiAliasing = true
    self.fillBorders = false

    -- other parameters
    self.MinFov = 0.
    self.MaxFov = 180.

    self.InputTex = nil
    self.OutputTex = nil
    return self
end

function ScriptCompOpticsCompensation:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value, _comp)
        if self[_key] ~= nil then
            self[_key] = _value
            if _comp and _comp.properties ~= nil then
                _comp.properties:set(_key, _value)
            end
        end
    end

    if key == "fovOrientation" then
        local typeTable = {"Horizontal", "Vertival", "Diagonal"}
        local fovOrientation = typeTable[value + 1]
        if fovOrientation == nil then
            fovOrientation = "Horizontal"
        end
        _setEffectAttr(key, fovOrientation, comp)
    else
        _setEffectAttr(key, value, comp)
    end
end

function ScriptCompOpticsCompensation:onStart(comp)
    self.matOpticsCompensation = comp.entity:searchEntity("EntityOpticsCompensation"):getComponent("MeshRenderer").material
    self.matAntiAliasing = comp.entity:searchEntity("EntityAntiAliasing"):getComponent("MeshRenderer").material

    self.camOpticsCompensation = comp.entity:searchEntity("CameraOpticsCompensation"):getComponent("Camera")
    self.camAntiAliasing = comp.entity:searchEntity("CameraAntiAliasing"):getComponent("Camera")

    self.MidTex = self.lumiSharedRt:get(0)
end

function ScriptCompOpticsCompensation:onUpdate(comp, deltaTime)
    -- prepare parameters
    local textureWidth = self.OutputTex.width
    local textureHeight = self.OutputTex.height
    if self.MidTex.width ~= textureWidth or self.MidTex.height ~= textureHeight then
        self.MidTex.width = textureWidth
        self.MidTex.height = textureHeight
    end
    local fovXScale, fovYScale = getFovXYScale(textureWidth, textureHeight, self.fovOrientation)

    self.fov = clamp(self.fov, self.MinFov, self.MaxFov)
    local inverseLensDistortion = boolToInt(self.inverseLensDistortion)
    local fillBorders = boolToInt(self.fillBorders)

    local k1 = 0.
    local k2 = 0.
    local fovIntensity = self.fov / 180.
    if self.inverseLensDistortion then
        k1, k2 = getPincushionDistortParam(fovIntensity)
    else
        k1, k2 = getBarrelDistortParam(fovIntensity)
    end

    -- set InputTex and OutputTex
    self.matOpticsCompensation:setTex("u_inputTexture", self.InputTex)
    if self.antiAliasing then
        self.camAntiAliasing.entity.visible = true
        self.camOpticsCompensation.renderTexture = self.MidTex
        self.matAntiAliasing:setTex("u_inputTexture", self.MidTex)
        self.camAntiAliasing.renderTexture = self.OutputTex
    else
        self.camAntiAliasing.entity.visible = false
        self.camOpticsCompensation.renderTexture = self.OutputTex
    end

    -- set material parameters
    self.matOpticsCompensation:setFloat("u_distortParam1", k1)
    self.matOpticsCompensation:setFloat("u_distortParam2", k2)

    self.matOpticsCompensation:setInt("u_inverseLensDistortion", inverseLensDistortion)
    self.matOpticsCompensation:setVec2("u_center", self.center)
    self.matOpticsCompensation:setFloat("u_fovXScale", fovXScale)
    self.matOpticsCompensation:setFloat("u_fovYScale", fovYScale)
    self.matOpticsCompensation:setInt("u_fillBorders", fillBorders)
end

exports.ScriptCompOpticsCompensation = ScriptCompOpticsCompensation
return exports
