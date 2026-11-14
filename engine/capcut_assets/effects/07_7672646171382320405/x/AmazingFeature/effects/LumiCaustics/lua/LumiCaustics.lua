local isEditor = (Amaz.Macros and Amaz.Macros.EditorSDK) and true or false
local exports = exports or {}
local LumiCaustics = LumiCaustics or {}
LumiCaustics.__index = LumiCaustics
---@class LumiCaustics : ScriptComponent
---@field bottomTex Texture
---@field bottomEdgeMode string [UI(Option={"Clamp", "Repeat", "Mirror", "Transparent", "Stretch"})]
---@field bottomScale number [UI(Range={0.1, 10}, Drag)]
---@field bottomBlur number [UI(Range={0, 1}, Drag)]
---@field surfaceTex Texture
---@field surfaceEdgeMode string [UI(Option={"Clamp", "Repeat", "Mirror", "Transparent", "Stretch"})]
---@field surfaceScale number [UI(Range={0.1, 10}, Drag)]
---@field surfaceChannel string [UI(Option={"R", "G", "B", "A", "Luminance", "Lightness"})]
---@field surfaceHeight number [UI(Range={0, 1}, Drag)]
---@field surfaceSmooth number [UI(Range={1, 50}, Drag)]
---@field surfaceHeight0 number [UI(Range={0, 1}, Drag)]
---@field surfaceRefract number [UI(Range={1, 2}, Drag)]
---@field surfaceColor Color [UI(NoAlpha)]
---@field surfaceOpacity number [UI(Range={0, 1}, Drag)]
---@field surfaceCausticsSize number [UI(Range={0, 2}, Drag)]
---@field surfaceCausticsIntensity number [UI(Range={0, 5}, Drag)]
---@field skyTex Texture
---@field skyEdgeMode string [UI(Option={"Clamp", "Repeat", "Mirror", "Transparent", "Stretch"})]
---@field skyScale number [UI(Range={0.1, 10}, Drag)]
---@field skyIntensity number [UI(Range={0, 2}, Drag)]
---@field skyReflect number [UI(Range={0, 10}, Drag)]
---@field lightMode string [UI(Option={"Distant", "Point"})]
---@field lightIntensity number [UI(Range={0, 2}, Drag)]
---@field lightColor Color [UI(NoAlpha)]
---@field lightPosition Vector2f
---@field lightHeight number [UI(Range={-10, 10}, Drag)]
---@field lightDiffuse boolean
---@field materialDiffuse number [UI(Range={0, 2}, Drag)]
---@field materialSpecular number [UI(Range={0, 2}, Drag)]
---@field materialSpecularSharpness number [UI(Range={0.025, 100}, Drag)]
---@field quality number [UI(Range={0, 1}, Drag)]
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
    if rt == nil or width <= 0 or height <= 0 then
        return
    end
    if rt.width ~= width or rt.height ~= height then
        rt.width = width
        rt.height = height
    end
end

local function setRenderTexture(camera, rt)
    if rt then
        camera.renderTexture = rt
    end
end

function LumiCaustics.new(construct, ...)
    local self = setmetatable({}, LumiCaustics)

    self.__lumi_type = "lumi_obj"
    self.__lumi_rt_pingpong_type = "custom"

    self.ChannelQuery = {
        [0] = "R",
        "G",
        "B",
        "A",
        "Luminance",
        "Lightness",
        ["R"] = 0,
        ["G"] = 1,
        ["B"] = 2,
        ["A"] = 3,
        ["Luminance"] = 4,
        ["Lightness"] = 5
    }
    self.EdgeModeQuery = {
        [0] = "Clamp",
        "Repeat",
        "Mirror",
        "Transparent",
        "Stretch",
        ["Clamp"] = 0,
        ["Repeat"] = 1,
        ["Mirror"] = 2,
        ["Transparent"] = 3,
        ["Stretch"] = 4
    }
    self.LightModeQuery = {
        [0] = "Distant",
        "Point",
        ["Distant"] = 0,
        ["Point"] = 1
    }

    self.bottomTex = nil
    self.bottomEdgeMode = "Mirror"
    self.bottomScale = 1
    self.bottomBlur = 0 -- ***

    self.surfaceTex = nil
    self.surfaceEdgeMode = "Mirror"
    self.surfaceScale = 1
    self.surfaceChannel = "Luminance"
    self.surfaceHeight = 0.2
    self.surfaceSmooth = 5
    self.surfaceHeight0 = 0.1
    self.surfaceRefract = 1.33
    self.surfaceColor = Amaz.Color(0, 0.5, 1)
    self.surfaceOpacity = 0.3
    self.surfaceCausticsSize = 0.5
    self.surfaceCausticsIntensity = 0

    self.skyTex = nil
    self.skyEdgeMode = "Mirror"
    self.skyScale = 1
    self.skyIntensity = 0.3
    self.skyReflect = 0.2

    self.lightMode = "Distant"
    self.lightIntensity = 1
    self.lightColor = Amaz.Color(1, 1, 1)
    self.lightPosition = Amaz.Vector2f(0.5, 0.5)
    self.lightHeight = 1
    self.lightDiffuse = true
    self.materialDiffuse = 1.0
    self.materialSpecular = 0.3
    self.materialSpecularSharpness = 10

    self.quality = 1.0
    self.InputTex = nil
    self.OutputTex = nil

    return self
end

function LumiCaustics:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value, _force)
        if _force or self[_key] ~= nil then
            self[_key] = _value
            if comp and comp.properties ~= nil then
                comp.properties:set(_key, _value)
            end
        end
    end

    if key == "bottomEdgeMode" or key == "surfaceEdgeMode" or key == "skyEdgeMode" then
        value = math.max(0, math.min(value, #self.EdgeModeQuery))
        value = self.EdgeModeQuery[value]
        _setEffectAttr(key, value)
    elseif key == "surfaceChannel" then
        value = math.max(0, math.min(value, #self.ChannelQuery))
        value = self.ChannelQuery[value]
        _setEffectAttr(key, value)
    elseif key == "lightMode" then
        value = math.max(0, math.min(value, #self.LightModeQuery))
        value = self.LightModeQuery[value]
        _setEffectAttr(key, value)
    elseif key == "bottomTex" or key == "surfaceTex" or key == "skyTex" then
        _setEffectAttr(key, value, true)
    else
        _setEffectAttr(key, value)
    end
end

function LumiCaustics:onStart(comp)
    self.entity = comp.entity
    self.TAG = AE_EFFECT_TAG .. ' ' .. self.entity.name
    Amaz.LOGI(self.TAG, 'onStart')

    self.camHeight, self.matHeight = self:initializeComponents("Height")
    self.camBlurX, self.matBlurX = self:initializeComponents("BlurX")
    self.camBlurY, self.matBlurY = self:initializeComponents("BlurY")
    self.camBlurX2, self.matBlurX2 = self:initializeComponents("BlurX_2")
    self.camBlurY2, self.matBlurY2 = self:initializeComponents("BlurY_2")
    self.camNormal, self.matNormal = self:initializeComponents("Normal")
    self.camLight, self.matLight = self:initializeComponents("Light")

    local ow = self.OutputTex.width
    local oh = self.OutputTex.height
    self.heightTex = createRenderTexture(ow, oh)
    local scaledW = ow * self.quality
    local scaledH = oh * self.quality
    self.normalTex = createRenderTexture(scaledW, scaledH)
    self.tmpTex0 = createRenderTexture(scaledW, scaledH)
    self.tmpTex1 = createRenderTexture(scaledW, scaledH)
end

function LumiCaustics:onUpdate(comp, deltaTime)

    if not self.OutputTex or not self.InputTex then
        return
    end

    local ow = self.OutputTex.width
    local oh = self.OutputTex.height
    local scaledW = ow * self.quality * math.min(10.0 / self.surfaceSmooth, 1.0)
    local scaledH = oh * self.quality * math.min(10.0 / self.surfaceSmooth, 1.0)
    local minEdge = math.min(ow, oh)

    updateTexSize(self.heightTex, ow, oh)
    updateTexSize(self.normalTex, scaledW, scaledH)
    updateTexSize(self.tmpTex0, scaledW, scaledH)
    updateTexSize(self.tmpTex1, scaledW, scaledH)

    local bottomTex = self.bottomTex or self.OutputTex
    local bottomW = self.bottomEdgeMode == "Stretch" and ow or bottomTex.width
    local bottomH = self.bottomEdgeMode == "Stretch" and oh or bottomTex.height

    local surfaceTex = self.surfaceTex or self.OutputTex
    local surfaceW = self.surfaceEdgeMode == "Stretch" and ow or surfaceTex.width
    local surfaceH = self.surfaceEdgeMode == "Stretch" and oh or surfaceTex.height

    local skyTex = self.skyTex
    local skyW = (self.skyEdgeMode == "Stretch" or not skyTex) and ow or skyTex.width
    local skyH = (self.skyEdgeMode == "Stretch" or not skyTex) and oh or skyTex.height

    -- Texture Settings
    setRenderTexture(self.camHeight, self.heightTex)
    setRenderTexture(self.camBlurX, self.tmpTex0)
    setRenderTexture(self.camBlurY, self.tmpTex1)
    setRenderTexture(self.camBlurX2, self.tmpTex0)
    setRenderTexture(self.camBlurY2, self.tmpTex1)
    setRenderTexture(self.camNormal, self.normalTex)
    setRenderTexture(self.camLight, self.OutputTex)
    -- Material Settings
    self.matHeight:setTex("u_inputTexture", self.surfaceTex or self.InputTex)
    self.matBlurX:setTex("u_inputTexture", self.heightTex)
    self.matBlurY:setTex("u_inputTexture", self.tmpTex0)
    self.matBlurX2:setTex("u_inputTexture", self.tmpTex1)
    self.matBlurY2:setTex("u_inputTexture", self.tmpTex0)
    -- self.matNormal:setTex("u_inputTexture", self.heightTex)
    self.matNormal:setTex("u_inputTexture", self.tmpTex1)
    self.matLight:setTex("u_bottomTexture", self.bottomTex or self.InputTex)
    self.matLight:setTex("u_heightTexture", self.tmpTex1)
    self.matLight:setTex("u_normalTexture", self.normalTex)
    self.matLight:setTex("u_skyTexture", self.skyTex)
    -- Height Settings
    self.matHeight:setInt("u_property", self.ChannelQuery[self.surfaceChannel])
    self.matHeight:setInt("u_edgeMode", self.EdgeModeQuery[self.surfaceEdgeMode])
    self.matHeight:setVec2("u_inputSize", Amaz.Vector2f(surfaceW * self.surfaceScale, surfaceH * self.surfaceScale))
    -- Blur Settings
    local steps = math.max(self.surfaceSmooth * 5, 1)
    local stride = 0.3
    local angle0 = math.rad(0)
    local angle90 = math.rad(90)
    self.matBlurX:setInt("u_steps", steps)
    self.matBlurX:setFloat("u_stride", stride)
    self.matBlurX:setFloat("u_angle", angle0)
    self.matBlurY:setInt("u_steps", steps)
    self.matBlurY:setFloat("u_stride", stride)
    self.matBlurY:setFloat("u_angle", angle90)

    self.matBlurX2:setInt("u_steps", steps)
    self.matBlurX2:setFloat("u_stride", stride)
    self.matBlurX2:setFloat("u_angle", angle0)
    self.matBlurY2:setInt("u_steps", steps)
    self.matBlurY2:setFloat("u_stride", stride)
    self.matBlurY2:setFloat("u_angle", angle90)
    -- Normal Settings
    local waveHeight = (minEdge / 20) * self.surfaceHeight
    self.matNormal:setFloat("u_height", waveHeight)
    self.matNormal:setFloat("u_causticsSize", self.surfaceCausticsSize * 10)
    self.matNormal:setInt("u_enable", self.surfaceCausticsIntensity > 0.02 and 1 or 0)
    -- Light Settings
    local baseHeight = (minEdge / 20) * self.surfaceHeight0
    self.matLight:setFloat("u_height", waveHeight)
    self.matLight:setFloat("u_height0", baseHeight)
    self.matLight:setFloat("u_refract", (self.surfaceRefract - 1) * 5)
    self.matLight:setVec3("u_waterColor", Amaz.Vector3f(self.surfaceColor.r, self.surfaceColor.g, self.surfaceColor.b))
    self.matLight:setFloat("u_waterOpacity", self.surfaceOpacity)
    self.matLight:setFloat("u_causticsIntensity", self.surfaceHeight * self.surfaceCausticsIntensity)

    self.matLight:setInt("u_bottomEdgeMode", self.EdgeModeQuery[self.bottomEdgeMode])
    self.matLight:setVec2("u_bottomSize", Amaz.Vector2f(bottomW * self.bottomScale, bottomH * self.bottomScale))

    self.matLight:setInt("u_skyEdgeMode", self.EdgeModeQuery[self.skyEdgeMode])
    self.matLight:setVec2("u_skySize", Amaz.Vector2f(skyW * self.skyScale, skyH * self.skyScale))
    self.matLight:setFloat("u_skyIntensity", skyTex and self.skyIntensity or 0)
    self.matLight:setFloat("u_skyReflect", self.skyReflect)

    self:setLightDir(ow, oh, minEdge)
    self.matLight:setInt("u_lightMode", self.LightModeQuery[self.lightMode])
    self.matLight:setVec3("u_lightColor", Amaz.Vector3f(self.lightColor.r, self.lightColor.g, self.lightColor.b))
    self.matLight:setInt("u_lightDiffuse", self.lightDiffuse and 1 or 0)
    self.matLight:setFloat("u_lightIntensity", self.lightIntensity)
    self.matLight:setFloat("u_diffuse", self.materialDiffuse)
    self.matLight:setFloat("u_specular", self.materialSpecular)
    self.matLight:setFloat("u_specularExp", self.materialSpecularSharpness)
end

function LumiCaustics:initializeComponents(name)
    local cameraEntityName = "Cam" .. name
    local meshEntityName = "Pass" .. name
    local camera = self.entity:searchEntity(cameraEntityName):getComponent("Camera")
    local meshRenderer = self.entity:searchEntity(meshEntityName):getComponent("MeshRenderer")
    return camera, meshRenderer and meshRenderer.material
end

function LumiCaustics:setLightDir(w, h, minEdge)
    local x = self.lightPosition.x * w
    local y = self.lightPosition.y * h
    local z = self.lightHeight * minEdge
    local res = Amaz.Vector3f(x - w / 2, y - h / 2, z)
    if self.lightMode == "Distant" then
        res = Amaz.Vector3f.normalize(res)
    end
    self.matLight:setVec3("u_lightDirOrPos", res)
end

exports.LumiCaustics = LumiCaustics
return exports
