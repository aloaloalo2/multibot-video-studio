local isEditor = (Amaz.Macros and Amaz.Macros.EditorSDK) and true or false
local exports = exports or {}
local GlowIter = GlowIter or {}
GlowIter.__index = GlowIter
---@class GlowIter : ScriptComponent
---@field downScale number [UI(Range={0.1, 1.0}, Drag)]
---@field stride number [UI(Range={0.001, 200.0}, Drag)]
---@field sigma number [UI(Range={0.01, 200.0}, Drag)]
---@field maxSteps int [UI(Range={1, 2000}, Drag)]
---@field steps int [UI(Range={1, 2000}, Slider)]
---@field stepsMult number [UI(Range={0.01, 10000.0}, Drag)]
---@field downSample double [UI(Range={0.5, 1.0}, Drag)]
---@field rotate int [UI(Range={0, 360}, Slider)]
---@field ratio int [UI(Range={0, 2}, Slider)]
---@field gammaCorrect Bool
---@field gammaValue number [UI(Range={1., 4.0}, Drag)]
---@field comp boolean
---@field opacity number [UI(Range={0.0, 4.0}, Drag)]
---@field blendMode int [UI(Range={0, 1}, Slider)]
---@field InputTex Texture
---@field OutputTex Texture

local AE_EFFECT_TAG = 'AE_EFFECT_TAG LumiTag'

------------ util functions for ScriptComponent ------------
local clamp = function(value, min, max)
    return math.max(math.min(value, max), min)
end

local function setRenderTexSize(rt, width, height)
    if rt.width ~= width or rt.height ~= height then
        rt.width = width
        rt.height = height
    end
end

------------ class functions for ScriptComponent ------------
function GlowIter.new(construct, ...)
    local self = setmetatable({}, GlowIter)

    if construct and GlowIter.constructor then
        GlowIter.constructor(self, ...)
    end

    self.__lumi_type = "lumi_obj"
    self.__lumi_rt_pingpong_type = "custom"

    self.downScale = 0.5
    self.radius = 0.5
    self.stride = 1.
    self.sigma = 1.
    self.stepsMult = 1
    self.downSample = 1
    self.maxSteps = 16
    self.angle = 0
    self.ratio = 1.
    self.rotate = 1.
    self.gammaCorrect = true
    self.gammaValue = 2.2
    self.comp = false
    self.opacity = 1.0
    self.mult = 1.0

    self.InputTex = nil
    self.bufferA = nil
    self.bufferB = nil
    self.OutputTex = nil

    return self
end

function GlowIter:onStart(comp)
    self.entity = comp.entity
    AE_EFFECT_TAG = AE_EFFECT_TAG .. ' ' .. self.entity.name
    Amaz.LOGI(AE_EFFECT_TAG, 'onStart')

    self.camDown = comp.entity:searchEntity("CameraDown"):getComponent("Camera")
    self.matDown = comp.entity:searchEntity("PassDown"):getComponent(
                       "MeshRenderer").material
    self.camBlurX = comp.entity:searchEntity("CameraBlurX"):getComponent(
                        "Camera")
    self.matBlurX = comp.entity:searchEntity("PassBlurX"):getComponent(
                        "MeshRenderer").material

    self.matBlurY = comp.entity:searchEntity("PassBlurY"):getComponent(
                        "MeshRenderer").material
    self.camBlurY = comp.entity:searchEntity("CameraBlurY"):getComponent(
                        "Camera")

    self.matComp = comp.entity:searchEntity("PassComp"):getComponent(
                       "MeshRenderer").material
    self.camComp = comp.entity:searchEntity("CameraComp"):getComponent("Camera")
end

function GlowIter:onUpdate(comp, detalTime)
    local width = self.OutputTex.width
    local height = self.OutputTex.height
    local downScaleW = width * self.downScale
    local downScaleH = height * self.downScale

    -- Set RT sizes
    setRenderTexSize(self.bufferA, downScaleW, downScaleH)
    setRenderTexSize(self.bufferB, downScaleW, downScaleH)

    -- Set Tex
    if self.bufferA then
        self.camDown.renderTexture = self.bufferA
        self.camBlurY.renderTexture = self.bufferA
    end
    if self.bufferB then self.camBlurX.renderTexture = self.bufferB end
    if self.OutputTex then self.camComp.renderTexture = self.OutputTex end

    self.matDown:setTex("u_inputTex", self.InputTex)
    self.matBlurX:setTex("u_inputTex", self.bufferA)
    self.matBlurY:setTex("u_inputTex", self.bufferB)

    -- Set Parms
    local ratio = clamp(self.ratio, 0, 2)
    local rotate = self.rotate
    local stepsInt = 1. / self.downSample
    local stride = self.stride / self.stepsMult
    local aspect = Amaz.Vector2f(width, height) / math.max(width, height)
    local stepsX = math.min(self.steps, self.maxSteps) * ratio
    local stepsY = math.min(self.steps, self.maxSteps) * (2.0 - ratio)

    if self.gammaCorrect then
        self.matBlurX:setFloat("u_gammaValue", self.gammaValue)
        self.matBlurY:setFloat("u_gammaValue", self.gammaValue)
        self.matComp:setFloat("u_gammaValue", self.gammaValue)
    else
        self.matBlurX:setFloat("u_gammaValue", 1)
        self.matBlurY:setFloat("u_gammaValue", 1)
        self.matComp:setFloat("u_gammaValue", 1)
    end

    self.matBlurX:setFloat("u_steps", stepsX)
    self.matBlurX:setFloat("u_stepsInt", stepsInt) -- for controlling i 
    self.matBlurX:setFloat("u_stride", stride)
    self.matBlurX:setFloat("u_sigma", self.sigma)
    self.matBlurX:setFloat("u_angle", self.angle)
    self.matBlurX:setFloat("u_rotate", rotate)
    self.matBlurX:setVec2("u_aspect", aspect)

    self.matBlurY:setFloat("u_steps", stepsY)
    self.matBlurY:setFloat("u_stepsInt", stepsInt) -- for controlling i 
    self.matBlurY:setFloat("u_stride", stride)
    self.matBlurY:setFloat("u_sigma", self.sigma)
    self.matBlurY:setFloat("u_angle", self.angle + 90)
    self.matBlurY:setFloat("u_rotate", rotate)
    self.matBlurY:setVec2("u_aspect", aspect)

    self.matComp:setTex("u_inputTex", self.InputTex)
    self.matComp:setTex("u_blurTex", self.bufferA)
    self.matComp:setFloat("u_opacity", self.opacity)
    self.matComp:setFloat("u_mult", self.mult)
    self.matComp:setInt("u_comp", self.comp and 1 or 0)
    self.matComp:setInt("u_blendMode", self.blendMode)
end
exports.GlowIter = GlowIter
return exports
