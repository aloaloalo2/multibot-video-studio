---@class ScriptCompDirectionalBlurs: ScriptComponent
---@field blurIntensity number [UI(Range={0., 1000.}, Drag)]
---@field angle number
---@field directionNum int [UI(Range={1, 4}, Slider)]
---@field exposure number [UI(Range={0., 10.}, Drag)]
---@field quality number [UI(Range={0., 1.}, Drag)]
---@field spaceDither number [UI(Range={0, 1.}, Drag)]
---@field borderType string [UI(Option={"Normal", "Black", "Mirror"})]
---@field blendMode string [UI(Option={"Screen", "Add", "Mean"})]
---@field InputTex Texture
---@field OutputTex Texture


local exports = exports or {}
local ScriptCompDirectionalBlurs = ScriptCompDirectionalBlurs or {}
ScriptCompDirectionalBlurs.__index = ScriptCompDirectionalBlurs


------------ util functions ------------
local function createRenderTexture(width, height)
    local rt = Amaz.RenderTexture()
    rt.width = width
    rt.height = height
    rt.depth = 1
    rt.filterMag = Amaz.FilterMode.LINEAR
    rt.filterMin = Amaz.FilterMode.LINEAR
    rt.attachment = Amaz.RenderTextureAttachment.NONE
    return rt
end


local function clamp(value, min, max)
    --[[
        Description: clamp value between [min, max]
    ]]
    return math.min(math.max(value, min), max)
end


local function getXYScale(width, height)
    --[[
        Description: get XY scale for adjusting width/height ratio.
    ]]
    -- the following computation for baseSize is to avoid too small or too large width/height ratio.
    local size1 = math.min(width, height)
    local size2 = math.max(width, height) / 2.
    local baseSize = math.max(size1, size2)

    local xScale = baseSize / width
    local yScale = baseSize / height
    return xScale, yScale
end


local function getBorderType(borderType)
    --[[
        Description: convert borderType from string to int
    ]]
    local borderTypeTable = {
        ["Normal"] = 0, -- default
        ["Black"] = 1,
        ["Mirror"] = 2
    }
    local flag = borderTypeTable[borderType]
    if flag == nil then flag = 0 end
    return flag
end

local function getBlendMode(blendMode)
    --[[
        Description: convert blendMode from string to int
    ]]
    local blendModeTable = {
        ["Screen"] = 0, -- default
        ["Add"] = 1,
        ["Mean"] = 2
    }
    local flag = blendModeTable[blendMode]
    if flag == nil then flag = 0 end
    return flag
end


local function getSampleNum(intensity)
    --[[
        Description: get sample number and downsample scale
    ]]
    local scale = 1.
    local bias = 0.
    local s = scale
    if intensity <= 10 then
        scale = 0.8
        bias = 0.
        s = 1.0
    elseif intensity <= 50 then
        scale = 0.7
        bias = 2.
        s = 0.78
    elseif intensity <= 200 then
        scale = 0.5
        bias = 10
        s = 0.66
    elseif intensity <= 500 then
        scale = 0.25
        bias = 60.
        s = 0.7
    else
        scale = 0.125
        bias = 100.
        s = 0.8
    end

    local sampleNum = scale * intensity + bias
    sampleNum = sampleNum * s
    if sampleNum < 2. then
        sampleNum = math.floor(sampleNum + 0.5)
    end
    return sampleNum, scale
end


local function getQualityParam(quality)
    local qualityParam = quality * 2. - 1.
    if qualityParam < 0. then
        qualityParam = 10 ^ qualityParam
    else
        qualityParam = qualityParam * 2. + 1.
    end
    return qualityParam
end


------------ class functions for ScriptComponent ------------
function ScriptCompDirectionalBlurs.new(construct, ...)
    local self = setmetatable({}, ScriptCompDirectionalBlurs)

    -- user parameters
    self.blurIntensity = 0.
    self.angle = 0.
    self.directionNum = 1
    self.exposure = 1.
    self.quality = 0.5
    self.spaceDither = 0.
    self.borderType = "Normal"
    self.blendMode = "Screen"

    -- other parameters
    self.NormalizationSize = 1000.
    self.MaxIntensity = 1000.
    self.MaxExposure = 10.
    self.RadiusOverSigma = 3.
    self.MaxDirectionNum = 4
    self.Eps = 1e-5

    self.InputTex = nil
    self.OutputTex = nil

    return self
end


function ScriptCompDirectionalBlurs:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value, _comp)
        if self[_key] ~= nil then
            self[_key] = _value
            if _comp and _comp.properties ~= nil then
                _comp.properties:set(_key, _value)
            end
        end
    end

    if key == "borderType" then
        local typeTable = {"Normal", "Black", "Mirror"}
        local borderType = typeTable[value + 1]
        if borderType == nil then borderType = "Normal" end
        _setEffectAttr(key, borderType, comp)
    elseif key == "blendMode" then
        local typeTable = {"Screen", "Add", "Mean"}
        local blendMode = typeTable[value + 1]
        if blendMode == nil then blendMode = "Screen" end
        _setEffectAttr(key, blendMode, comp)
    else
        _setEffectAttr(key, value, comp)
    end
end


function ScriptCompDirectionalBlurs:onStart(comp)
    self.camDownScale = comp.entity:searchEntity("CameraDownScale"):getComponent("Camera")
    self.camBlend = comp.entity:searchEntity("CameraBlend"):getComponent("Camera")
    self.matBlend = comp.entity:searchEntity("EntityBlend"):getComponent("MeshRenderer").material

    self.camBlurs = {}
    for i = 1, self.MaxDirectionNum, 1 do
        self.camBlurs[i] = comp.entity:searchEntity("CameraDirectionalBlurs_" .. i):getComponent("Camera")
    end

    self.matBlurs = {}
    for i = 1, self.MaxDirectionNum, 1 do
        self.matBlurs[i] = comp.entity:searchEntity("EntityDirectionalBlurs_" .. i):getComponent("MeshRenderer").material
    end

    self.downsampleTex = createRenderTexture(1, 1)
    self.textures = {}
    for i = 1, self.MaxDirectionNum, 1 do
        self.textures[i] = createRenderTexture(1, 1)
    end
end


function ScriptCompDirectionalBlurs:onUpdate(comp, deltaTime)
    local textureWidth = self.OutputTex.width
    local textureHeight = self.OutputTex.height

    -- compute intensity. intensityX/Y are the only factors that affect blur intensity
    self.blurIntensity = clamp(self.blurIntensity, 0., self.MaxIntensity)
    local startAngle = (-self.angle - 90.) * math.pi / 180.
    self.directionNum = clamp(self.directionNum, 1, self.MaxDirectionNum)
    local directionNum = math.floor(self.directionNum)
    local deltaAngle = math.pi / directionNum
    self.exposure = clamp(self.exposure, 0., self.MaxExposure)
    local sampleNum, downScale = getSampleNum(self.blurIntensity)
    self.quality = clamp(self.quality, 0., 1.)
    local qualityParam = getQualityParam(self.quality)
    local borderType = getBorderType(self.borderType)
    local blendMode = getBlendMode(self.blendMode)
    self.spaceDither = clamp(self.spaceDither, 0., 1.)

    self.downsampleTex.width = textureWidth * downScale
    self.downsampleTex.height = textureHeight * downScale

    -- set texture size
    for i = 1, self.MaxDirectionNum, 1 do
        if i <= directionNum then
            self.textures[i].width = textureWidth * downScale
            self.textures[i].height = textureHeight * downScale
        else
            self.textures[i].width = 1
            self.textures[i].height = 1
        end
    end

    -- compute sigma, sample, dx/y.
    local xScale, yScale = getXYScale(textureWidth, textureHeight)
    local radius = self.blurIntensity / self.NormalizationSize
    local sigma = radius / self.RadiusOverSigma
    local sample = sampleNum * qualityParam
    local ds = radius / math.max(sample, self.Eps)

    -- set Textures
    self.camDownScale.inputTexture = self.InputTex
    self.camDownScale.renderTexture = self.downsampleTex

    for i = 1, self.MaxDirectionNum, 1 do
        self.matBlurs[i]:setTex("u_inputTexture", self.downsampleTex)
        self.camBlurs[i].renderTexture = self.textures[i]
        if i <= directionNum then
            self.camBlurs[i].entity.visible = true
        else
            self.camBlurs[i].entity.visible = false
        end
    end

    if directionNum == 1 then
        self.camBlend.entity.visible = false
        self.camBlurs[1].renderTexture = self.OutputTex
    else
        self.camBlend.entity.visible = true
        self.camBlurs[1].renderTexture = self.textures[1]
    end

    -- set parameters for materials
    for i = 1, self.MaxDirectionNum, 1 do
        local angle = startAngle + (i - 1) * deltaAngle
        local dx = ds * math.cos(angle) * xScale
        local dy = ds * math.sin(angle) * yScale

        self.matBlurs[i]:setFloat("u_sample", sample)
        self.matBlurs[i]:setFloat("u_sigma", sigma)
        self.matBlurs[i]:setFloat("u_stepX", dx)
        self.matBlurs[i]:setFloat("u_stepY", dy)
        self.matBlurs[1]:setFloat("u_spaceDither", self.spaceDither)
        self.matBlurs[1]:setInt("u_borderType", borderType)
    end
    self.matBlurs[1]:setFloat("u_exposure", self.exposure)
    self.matBlurs[1]:setInt("u_directionNum", directionNum)

    self.matBlend:setFloat("u_exposure", self.exposure)
    self.matBlend:setInt("u_directionNum", directionNum)
    self.matBlend:setInt("u_blendMode", blendMode)
    for i = 1, directionNum, 1 do
        self.matBlend:setTex("u_tex" .. i, self.textures[i])
    end
end


exports.ScriptCompDirectionalBlurs = ScriptCompDirectionalBlurs
return exports
