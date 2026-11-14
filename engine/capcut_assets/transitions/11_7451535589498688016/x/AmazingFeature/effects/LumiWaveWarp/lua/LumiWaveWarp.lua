local isEditor = (Amaz.Macros and Amaz.Macros.EditorSDK) and true or false
local exports = exports or {}
local LumiWaveWarp = LumiWaveWarp or {}
LumiWaveWarp.__index = LumiWaveWarp
---@class LumiWaveWarp : ScriptComponent
---@field type string [UI(Option={"Sine", "Square", "Triangle", "Sawtooth", "Circle", "Semicircular", "NonCircular", "Noise", "SmoothNoise"})]
---@field fixedType string [UI(Option={"None", "AllEdge", "Center", "LeftEdge", "TopEdge", "RightEdge", "BottomEdge", "HorizontalEdge", "VerticalEdge"})]
---@field aa string [UI(Option={"Low", "Medium", "High"})]
---@field amplitude double [UI(Display="Amplitude", Range={-2000, 2000}, Drag)]
---@field wavelength double [UI(Display="Wavelength", Range={1, 5000}, Drag)]
---@field direction double [UI(Display="Direction", Range={-360, 360}, Drag)]
---@field speed double [UI(Display="Speed", Range={-100, 100}, Drag)]
---@field phase double [UI(Display="Phase", Range={-256, 256}, Drag)]
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

function LumiWaveWarp.new(construct, ...)
    local self = setmetatable({}, LumiWaveWarp)

    self.__lumi_type = "lumi_obj"
    self.__lumi_rt_pingpong_type = "custom"

    self.InputTex = nil
    self.OutputTex = nil
    self.type = "Sine"
    self.fixedType = "None"
    self.aa = "Low"
    self.wavelength = 40
    self.amplitude = 10
    self.direction = 90
    self.phase = 0
    self.speed = 1
    self.curTime = 0

    self.TYPE_QUERY = {
        [0] = "Sine",
        "Square",
        "Triangle",
        "Sawtooth",
        "Circle",
        "Semicircular",
        "NonCircular",
        "Noise",
        "SmoothNoise",
        ["Sine"] = 0,
        ["Square"] = 1,
        ["Triangle"] = 2,
        ["Sawtooth"] = 3,
        ["Circle"] = 4,
        ["Semicircular"] = 5,
        ["NonCircular"] = 6,
        ["Noise"] = 7,
        ["SmoothNoise"] = 8
    }
    self.FIXED_QUERY = {
        [0] = "None",
        "AllEdge",
        "Center",
        "LeftEdge",
        "TopEdge",
        "RightEdge",
        "BottomEdge",
        "HorizontalEdge",
        "VerticalEdge",
        ["None"] = 0,
        ["AllEdge"] = 1,
        ["Center"] = 2,
        ["LeftEdge"] = 3,
        ["TopEdge"] = 4,
        ["RightEdge"] = 5,
        ["BottomEdge"] = 6,
        ["HorizontalEdge"] = 7,
        ["VerticalEdge"] = 8
    }
    self.AA_QUERY = {
        [0] = "Low",
        "Medium",
        "High",
        ["Low"] = 0,
        ["Medium"] = 1,
        ["High"] = 2
    }
    return self
end

function LumiWaveWarp:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value, _force)
        if _force or self[_key] ~= nil then
            self[_key] = _value
            if comp and comp.properties ~= nil then
                comp.properties:set(_key, _value)
            end
        end
    end

    if key == "type" then
        value = math.max(0, math.min(value, #self.TYPE_QUERY))
        value = self.TYPE_QUERY[value]
        _setEffectAttr(key, value)
    elseif key == "fixedType" then
        value = math.max(0, math.min(value, #self.FIXED_QUERY))
        value = self.FIXED_QUERY[value]
        _setEffectAttr(key, value)
    elseif key == "AA" then
        value = math.max(0, math.min(value, #self.AA_QUERY))
        value = self.AA_QUERY[value]
        _setEffectAttr(key, value)
    else
        _setEffectAttr(key, value)
    end
end

function LumiWaveWarp:onStart(comp)
    self.entity = comp.entity
    self.TAG = AE_EFFECT_TAG .. ' ' .. self.entity.name
    Amaz.LOGI(self.TAG, 'onStart')

    self.camera = self.entity:searchEntity("WaveCamera"):getComponent("Camera")
    self.material = self.entity:searchEntity("WavePass"):getComponent(
                        "MeshRenderer").material
end

function LumiWaveWarp:onUpdate(comp, deltaTime)
    local w = self.OutputTex.width
    local h = self.OutputTex.height
    if self.OutputTex then self.camera.renderTexture = self.OutputTex end
    self.material:setTex("u_inputTexture", self.InputTex)
    self.material:setInt("u_type", self.TYPE_QUERY[self.type])
    self.material:setInt("u_fixedType", self.FIXED_QUERY[self.fixedType])
    self.material:setInt("u_aa", self.AA_QUERY[self.aa])
    self.material:setFloat("u_wavelength", self.wavelength)
    self.material:setFloat("u_amplitude", self.amplitude)

    local dir = math.rad(self.direction - 90)
    dir = Amaz.Vector2f(math.cos(dir), math.sin(dir))
    self.material:setVec2("u_dir", dir)

    local phase = self.curTime * self.speed + self.phase / 256
    self.material:setFloat("u_phase", -phase)
end

exports.LumiWaveWarp = LumiWaveWarp
return exports
