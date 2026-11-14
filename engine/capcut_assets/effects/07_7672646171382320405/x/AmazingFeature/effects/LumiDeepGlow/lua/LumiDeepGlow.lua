local isEditor = (Amaz.Macros and Amaz.Macros.EditorSDK) and true or false
local exports = exports or {}
local LumiDeepGlow = LumiDeepGlow or {}
LumiDeepGlow.__index = LumiDeepGlow
---@class LumiDeepGlow : ScriptComponent
---@field threshold number [UI(Range={0.0, 2.0}, Drag)]
---@field thresholdSmooth number [UI(Range={0.0, 1.0}, Drag)]
---@field greyScale number [UI(Range={0.0, 1.0}, Drag)]
---@field radius number [UI(Range={0, 2000}, Drag)]
---@field exposure number [UI(Range={0.0, 5.0}, Drag)]
---@field ratio number [UI(Range={0, 2}, Drag)]
---@field rotate number 
---@field view string [UI(Option={"Glow Input","Final Render"})]
---@field blendMode string [UI(Option={"Add","Screen"})]
---@field ca bool 
---@field redOffset number [UI(Range={-.1, 0.1}, Drag)]
---@field greenOffset number [UI(Range={-0.1, 0.1}, Drag)]
---@field blueOffset number [UI(Range={-0.1, 0.1}, Drag)]
---@field tint bool
---@field tintColor Color [UI(NoAlpha)] 
---@field tintMode string [UI(Option={"Multiply","Overlay", "Softlight"})]
---@field tintMix number [UI(Range={0.0, 1.0}, Drag)]
---@field sourceOpacity number [UI(Range={0., 1.}, Drag)]
---@field unmult Bool
---@field gammaCorrect Bool
---@field gammaValue number [UI(Range={1., 4.}, Drag)]
---@field glowIter int [UI(Range={1, 8}, Slider)]
---@field stepsMult number [UI(Range={0.1, 10.0}, Drag)]
---@field downSample number [UI(Range={0.5, 1.0}, Drag)]
---@field quality number [UI(Range={0.5, 1.0}, Drag)]
---@field InputTex Texture
---@field OutputTex Texture
---@field lumiSharedRt Vector [UI(Type="Texture")]

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

local function setRenderTexSize(rt, width, height)
    if rt == nil or width <= 0 or height <= 0 then
        return
    end
    if rt.width ~= width or rt.height ~= height then
        rt.width = width
        rt.height = height
    end
end

local function goldenRatio(n)
    local sequence = {1, 1}
    for i = 2, n - 1 do sequence[i + 1] = sequence[i] + sequence[i - 1] end
    return sequence
end

local function inverseSqrFalloff(distance, radius)
    local maxDistance = radius
    local falloffFactor = 0.05
    local attenuation = math.pow(falloffFactor, distance / maxDistance)
    return attenuation
end

local function mapRadiusToStepsMult(radius)
    local minRadius = 500
    local maxRadius = 2000
    local minStepsMult = 1.0
    local maxStepsMult = 2.5

    if radius < minRadius then
        return minStepsMult
    end

    local t = (radius - minRadius) / (maxRadius - minRadius)
    local stepsMult = minStepsMult + (maxStepsMult - minStepsMult) * t

    return stepsMult
end


function LumiDeepGlow.new(construct, ...)
    local self = setmetatable({}, LumiDeepGlow)

    self.__lumi_type = "lumi_effect"
    self.__lumi_rt_pingpong_type = "custom"

    self.threshold = 0.
    self.thresholdSmooth = 0.
    self.greyScale = 0.
    self.radius = 1.
    self.exposure = 1.
    self.rotate = 0.
    self.ratio = 1.

    self.view = "Final Render"
    self.blendMode = "Screen"
    self.sourceOpacity = 0.

    self.ca = false
    self.redOffset = 0.01
    self.greenOffset = -0.01
    self.blueOffset = 0.

    self.tint = true
    self.tintColor = Amaz.Color(1., 0., 0.)
    self.tintMode = "Multiply"
    self.tintMix = 1.

    self.unmult = false
    self.gammaCorrect = true
    self.gammaValue = 2.2

    self.glowIter = 8
    self.stepsMult = 1.
    self.downSample = 1.
    self.quality = 1.

    self.InputTex = nil
    self.thresholdTex = nil
    self.blurTex = nil
    self.blurTex1 = nil
    self.bufferA = nil
    self.bufferB = nil
    self.OutputTex = nil

    return self
end

function LumiDeepGlow:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value)
        if self[_key] ~= nil then
            self[_key] = _value
            if comp and comp.properties ~= nil then
                comp.properties:set(_key, _value)
            end
        end
    end

    if key == "view" then
        local view = "Final Render"
        if value == 0 then view = "Glow Input" end
        _setEffectAttr(key, view)
    elseif key == "tintMode" then
        local tintMode = "Multiply"
        if value == 1 then
            tintMode = "Overlay"
        elseif value == 2 then
            tintMode = "Softlight"
        end
        _setEffectAttr(key, tintMode)
    elseif key == "blendMode" then
        local blendMode = "Add"
        if value == 1 then blendMode = "Screen" end
        _setEffectAttr(key, blendMode)
    else
        _setEffectAttr(key, value)
    end
end

function LumiDeepGlow:onStart(comp)
    self.entity = comp.entity
    self.TAG = AE_EFFECT_TAG .. ' ' .. self.entity.name
    Amaz.LOGI(self.TAG, 'onStart')

    self.matPreprocess = comp.entity:searchEntity("PassPreprocess")
                             :getComponent("MeshRenderer").material
    self.camPreprocess = comp.entity:searchEntity("CameraPreprocess")
                             :getComponent("Camera")

    local numLayers = 8 
    self.GlowIters = {}
    for i = 1, numLayers do
        local name = "GlowIter_" .. i
        self.GlowIters[i] = comp.entity:searchEntity(name):getComponent(
                                "ScriptComponent")
    end

    self.matPostprocess = comp.entity:searchEntity("PassPostprocess")
                              :getComponent("MeshRenderer").material
    self.camPostprocess = comp.entity:searchEntity("CameraPostprocess")
                              :getComponent("Camera")

    if self.lumiSharedRt and self.lumiSharedRt:size() > 0 then
        self.blurTex = self.lumiSharedRt:get(0)
        self.blurTex1 = self.lumiSharedRt:get(1)
    end

    local width = self.OutputTex.width
    local height = self.OutputTex.height

    self.thresholdTex = createRenderTexture(width, height)
    self.bufferA = createRenderTexture(width, height)
    self.bufferB = createRenderTexture(width, height)
end

function LumiDeepGlow:onUpdate(comp, deltaTime)
    if self.thresholdTex then
        self.camPreprocess.renderTexture = self.thresholdTex
    end
    if self.OutputTex then self.camPostprocess.renderTexture = self.OutputTex end

    local width = self.OutputTex.width
    local height = self.OutputTex.height

    setRenderTexSize(self.thresholdTex, width, height)
    setRenderTexSize(self.blurTex, width, height)
    setRenderTexSize(self.blurTex1, width, height)

    --- Preprocess
    self.matPreprocess:setTex("u_inputTex", self.InputTex)
    self.matPreprocess:setFloat("u_threshold", self.threshold)
    self.matPreprocess:setFloat("u_thresholdSmooth", self.thresholdSmooth)
    self.matPreprocess:setFloat("u_greyScale", self.greyScale)
    self.matPreprocess:setInt("u_gamma", self.gammaCorrect and 1 or 0)
    self.matPreprocess:setFloat("u_gammaValue", self.gammaValue)
    self.matPreprocess:setInt("u_ca", self.ca and 1 or 0)
    self.matPreprocess:setFloat("u_redOffset", self.redOffset)
    self.matPreprocess:setFloat("u_greenOffset", self.greenOffset)
    self.matPreprocess:setFloat("u_blueOffset", self.blueOffset)

    -- Glow Iter Parameters
    local numLayers = 8
    local radius = self.radius * 5
    local radiusFactor = radius / 500
    local quality = self.quality
    local exposure = self.exposure
    local stepsMult = self.stepsMult * mapRadiusToStepsMult(radius)
    local glowIter = math.floor(self.glowIter)

    local GlowIters = {}
    for i = 1, numLayers do
        GlowIters[i] = Amaz.ScriptUtils.getLuaObj(self.GlowIters[i]:getScript())
    end

    local downScale = {}
    downScale[1] = 0.5 * quality
    downScale[self.glowIter] = 0.5 * quality
    for i = 2, self.glowIter - 1 do downScale[i] = 0.25 * quality end

    local stride = {}
    local maxSteps = {}
    local steps = {}
    local goldenRatioSequence = goldenRatio(numLayers)
    for i = 1, numLayers do
        maxSteps[i] = math.min(i * radiusFactor, i * 6)
        stride[i] = radiusFactor * i / math.max(width, height)
        steps[i] = radiusFactor * goldenRatioSequence[i]
    end

    local inputTex = {}
    local outputTex = {}
    for i = 1, numLayers do
        table.insert(inputTex, i % 2 == 0 and self.blurTex or self.blurTex1)
        table.insert(outputTex, i % 2 == 1 and self.blurTex or self.blurTex1)
    end
    inputTex[1] = self.thresholdTex

    for i = 1, numLayers do
        if i > glowIter then
            GlowIters[i].entity.visible = false
        else
            GlowIters[i].entity.visible = true

            GlowIters[i].InputTex = inputTex[i]
            GlowIters[i].OutputTex = outputTex[i]
            GlowIters[i].bufferA = self.bufferA
            GlowIters[i].bufferB = self.bufferB

            GlowIters[i].downScale = downScale[i]
            GlowIters[i].steps = steps[i]
            GlowIters[i].stride = stride[i]
            GlowIters[i].maxSteps = maxSteps[i]
            GlowIters[i].sigma = 4.

            GlowIters[i].stepsMult = stepsMult
            GlowIters[i].downSample = self.downSample
            GlowIters[i].ratio = self.ratio
            GlowIters[i].rotate = self.rotate

            local distance = i / numLayers
            local falloff = inverseSqrFalloff(distance, i)

            GlowIters[i].opacity = self.gammaValue / i * falloff
            GlowIters[i].mult = exposure
            GlowIters[i].gammaValue = self.gammaValue
            GlowIters[i].comp = true
            GlowIters[i].blendMode = self.blendMode == "Screen" and 0 or 1
        end
    end

    -- Modes
    local viewMode = (self.view == "Final Render") and 1 or 0
    self.matPreprocess:setInt("u_view", viewMode)
    self.matPostprocess:setInt("u_view", viewMode)

    local tintModes = {["Multiply"] = 1, ["Overlay"] = 2}
    self.matPostprocess:setInt("u_tintMode", tintModes[self.tintMode] or 0)

    -- Post Process
    if (glowIter % 2 == 0) then
        self.matPostprocess:setTex("u_blurTex", self.blurTex1)
    else
        self.matPostprocess:setTex("u_blurTex", self.blurTex)
    end

    self.matPostprocess:setTex("u_inputTex", self.InputTex)
    self.matPostprocess:setTex("u_thresholdTex", self.thresholdTex)
    self.matPostprocess:setTex("u_blurTex", self.blurTex)
    self.matPostprocess:setInt("u_gammaCorrect", self.gammaCorrect and 1 or 0)
    self.matPostprocess:setFloat("u_gammaValue", self.gammaValue)
    self.matPostprocess:setInt("u_unmult", self.unmult and 1 or 0)
    self.matPostprocess:setInt("u_tint", self.tint and 1 or 0)
    self.matPostprocess:setVec3("u_tintColor", Amaz.Vector3f(self.tintColor.r,
                                                             self.tintColor.g,
                                                             self.tintColor.b))
    self.matPostprocess:setFloat("u_tintMix", self.tintMix)
    self.matPostprocess:setFloat("u_srcOpacity", self.sourceOpacity)
end

exports.LumiDeepGlow = LumiDeepGlow
return exports
