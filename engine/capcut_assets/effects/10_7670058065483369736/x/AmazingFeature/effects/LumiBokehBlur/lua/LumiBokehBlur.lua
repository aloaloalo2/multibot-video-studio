
local isEditor = (Amaz.Macros and Amaz.Macros.EditorSDK) and true or false

local exports = exports or {}
local LumiBokehBlur = LumiBokehBlur or {}
---@class LumiBokehBlur: ScriptComponent [UI(Display="The Circle Bokeh")]
---@field bokehMode string [UI(Option={"Circle", "Heart", "Polygon","Star","CustomMask"})]
---@field scale number [UI(Range={0, 80}, Drag)]
---@field scaleX number  [UI(Range={0, 1}, Drag)]
---@field scaleY number [UI(Range={0, 1}, Drag)]
---@field regionIns number [UI(Range={0., 1}, Drag)]
---@field lightIns number [UI(Range={0, 6}, Drag)]
---@field darkIns number [UI(Range={0, 4}, Drag)]
---@field quality number [UI(Range={0., 1}, Drag)]
---@field lineNum int [UI(Range={3, 8}, Slider)]
---@field shapeIns number [UI(Range={0.2, 1}, Drag)]
---@field angle number [UI(Range={-360, 360}, Drag)]
---@field customMaskTex Texture
---@field InputTex Texture
---@field OutputTex Texture

local BokehModeName = {
    "Circle", "Heart", "Polygon","Star","CustomMask"
}
setmetatable(BokehModeName, {__index = function(_, _) return BokehModeName[1] end})


LumiBokehBlur.__index = LumiBokehBlur
function LumiBokehBlur.new(construct, ...)
    local self = setmetatable({}, LumiBokehBlur)
    if construct and LumiBokehBlur.constructor then LumiBokehBlur.constructor(self, ...) end
    self.bokehMode = "Circle"
    self.scale = 20
    self.scaleX = 1
    self.scaleY = 1
    self.regionIns = 0.5
    self.lightIns = 1
    self.quality = 1
    self.darkIns = 0.
    self.shapeIns = 1

    -- polygon extra param
    self.angle = 0
    self.lineNum = 5
    self.customMaskTex = nil
    self.InputTex = nil
    self.OutputTex = nil

    self.MAX_SCALE = 80

    return self
end

function LumiBokehBlur:setEffectAttr(key, value, comp)
    if key == "bokehMode" then
        value = BokehModeName[value + 1]
    end
    self[key] = value
    comp.properties:set(key, value)
end

function LumiBokehBlur:onStart(comp)
    self.interface = comp.properties

    self.bufBlur0 = comp.entity:searchEntity("blur0Cam"):getComponent("Camera").renderTexture
    self.matBlur0 = comp.entity:searchEntity("blur0"):getComponent("MeshRenderer").material

    self.bufBlur1 = comp.entity:searchEntity("blur1Cam"):getComponent("Camera").renderTexture
    self.matBlur1 = comp.entity:searchEntity("blur1"):getComponent("MeshRenderer").material

    self.objCircle = comp.entity:searchEntity("circleCam")
    self.matCircle = comp.entity:searchEntity("circle"):getComponent("MeshRenderer").material

    self.objPolygon = comp.entity:searchEntity("polygonCam")
    self.matPolygon = comp.entity:searchEntity("polygon"):getComponent("MeshRenderer").material

    self.objStar = comp.entity:searchEntity("starCam")
    self.matStar = comp.entity:searchEntity("star"):getComponent("MeshRenderer").material

    self.objHeart = comp.entity:searchEntity("heartCam")
    self.matHeart = comp.entity:searchEntity("heart"):getComponent("MeshRenderer").material

    self.objMask = comp.entity:searchEntity("getminMaskTexCam")
    self.matMask = comp.entity:searchEntity("getminMaskTex"):getComponent("MeshRenderer").material

    self.objCustom = comp.entity:searchEntity("customMaskCam")
    self.matCustom = comp.entity:searchEntity("customMask"):getComponent("MeshRenderer").material

    self.bufMask = self.objMask:getComponent("Camera").renderTexture
    self.bufBokeh = self.objCircle:getComponent("Camera").renderTexture

    self.camOutput = comp.entity:searchEntity("in2outCam"):getComponent("Camera")
end

function LumiBokehBlur:onUpdate(comp, dt)
    if not self.OutputTex then return end
    self.camOutput.renderTexture = self.OutputTex

    self.canvasW = self.OutputTex.width
    self.canvasH = self.OutputTex.height
    self.designScale = math.min(self.canvasW, self.canvasH) / 720
    self.realSize = self.scale * self.designScale
    self.canvasScale = math.min(self.mix(6, 16, self.quality) / math.max(self.realSize, 1), 1)
    self.scaledCanvasW = self.canvasW * self.canvasScale
    self.scaledCanvasH = self.canvasH * self.canvasScale
    self.scaledSize = self.realSize * self.canvasScale

    --Amaz.LOGE("", string.format("scaledCanvasW: %.3f", self.scaledCanvasW))
    --Amaz.LOGE("", string.format("scaledCanvasH: %.3f", self.scaledCanvasH))
    --Amaz.LOGE("", string.format("realSize: %.3f", self.realSize))
    --Amaz.LOGE("", string.format("scaledSize: %.3f", self.scaledSize))

    self.objCircle.visible = false
    self.objHeart.visible = false
    self.objPolygon.visible = false
    self.objStar.visible = false
    self.objMask.visible = false
    self.objCustom.visible = false

    self:updateBlur()

    if self.bokehMode == 'Heart' then
        self:updateHeart()
    elseif self.bokehMode == 'Polygon' then
        self:updatePolygon()
    elseif self.bokehMode == 'Star' then
        self:updateStar()
    elseif self.bokehMode == 'CustomMask' then
        self:updateCustom()
    else
        self:updateCircle()
    end
end

function LumiBokehBlur:updateBlur()
    self.bufBlur0.width = math.ceil(self.scaledCanvasW)
    self.bufBlur0.height = math.ceil(self.scaledCanvasH)
    self.bufBlur1.width = math.ceil(self.scaledCanvasW)
    self.bufBlur1.height = math.ceil(self.scaledCanvasH)

    self.matBlur0:setTex("u_inputTex", self.InputTex)

    local intensity = self.scale / self.MAX_SCALE
    local radius = 22 * self.designScale * self.canvasScale * math.pow(intensity, 0.35) * 0.7
    local samples = math.ceil(radius)
    self.matBlur0:setInt("u_samples", samples)
    self.matBlur0:setVec2("u_screenSize", Amaz.Vector2f(self.scaledCanvasW, self.scaledCanvasH))
    self.matBlur1:setInt("u_samples", samples)
    self.matBlur1:setVec2("u_screenSize", Amaz.Vector2f(self.scaledCanvasW, self.scaledCanvasH))
    self.matBlur1:setFloat("u_intensity", intensity)
    self.matBlur1:setFloat("u_darkIns", self.darkIns)
end

function LumiBokehBlur:updateCircle()
    self.objCircle.visible = true
    self.bufBokeh.width = math.ceil(self.scaledCanvasW)
    self.bufBokeh.height = math.ceil(self.scaledCanvasH)

    local sampleScale = self.mix(2.5, 1, self.scale / self.MAX_SCALE)
    local samplesCore = math.ceil(math.pi * self.scaledSize * self.scaledSize / sampleScale * 0.80)
    local samplesEdge = math.ceil(2 * math.pi * self.scaledSize / sampleScale * 1.00)
    self.matCircle:setInt("u_samplesCore", samplesCore)
    self.matCircle:setInt("u_samplesEdge", samplesEdge)
    self.matCircle:setVec2("u_screenSize", Amaz.Vector2f(self.scaledCanvasW, self.scaledCanvasH))
    self.matCircle:setVec2("u_scale", Amaz.Vector2f(self.scaleX, self.scaleY))
    self.matCircle:setFloat("u_radius", self.scaledSize)
    self.matCircle:setFloat("u_regionIns", self.regionIns)
    self.matCircle:setFloat("u_lightIns", self.lightIns)

    --Amaz.LOGE("", string.format("samplesCore: %d", samplesCore))
    --Amaz.LOGE("", string.format("samplesEdge: %d", samplesEdge))
end

function LumiBokehBlur.getPolygonAngle0(lineNum, angle0)
    if lineNum == 3 then
        return math.rad(angle0 - 90)
    elseif lineNum == 4 then
        return math.rad(angle0 - 90)
    elseif lineNum == 5 then
        return math.rad(angle0 - 90)
    elseif lineNum == 6 then
        return math.rad(angle0 - 90)
    elseif lineNum == 7 then
        return math.rad(angle0 - 90)
    else
        return math.rad(angle0 - 90)
    end
end
function LumiBokehBlur:updatePolygon()
    self.objPolygon.visible = true
    self.bufBokeh.width = math.ceil(self.scaledCanvasW)
    self.bufBokeh.height = math.ceil(self.scaledCanvasH)

    local sampleScale = self.mix(2.5, 1, self.scale / self.MAX_SCALE)
    local samplesCore = math.ceil(math.pi * self.scaledSize * self.scaledSize / sampleScale * 0.75)
    local samplesEdge = math.ceil(2 * math.pi * self.scaledSize / sampleScale * 1.00)
    self.matPolygon:setInt("u_samplesCore", samplesCore)
    self.matPolygon:setInt("u_samplesEdge", samplesEdge)
    self.matPolygon:setInt("u_lineNum", self.lineNum)
    self.matPolygon:setVec2("u_screenSize", Amaz.Vector2f(self.scaledCanvasW, self.scaledCanvasH))
    self.matPolygon:setVec2("u_scale", Amaz.Vector2f(self.scaleX, self.scaleY))
    self.matPolygon:setFloat("u_radius", self.scaledSize)
    self.matPolygon:setFloat("u_angle0", self.getPolygonAngle0(self.lineNum, self.angle))
    self.matPolygon:setFloat("u_regionIns", self.regionIns)
    self.matPolygon:setFloat("u_lightIns", self.lightIns)

    --Amaz.LOGE("", string.format("samplesCore: %d", samplesCore))
    --Amaz.LOGE("", string.format("samplesEdge: %d", samplesEdge))
end

function LumiBokehBlur.getStarAngle0(lineNum, angle0)
    if lineNum == 3 then
        return math.rad(angle0 + 90)
    elseif lineNum == 4 then
        return math.rad(angle0 + 90)
    elseif lineNum == 5 then
        return math.rad(angle0 + 90)
    elseif lineNum == 6 then
        return math.rad(angle0 + 60)
    elseif lineNum == 7 then
        return math.rad(angle0 + 90)
    else
        return math.rad(angle0 + 22.5)
    end
end
function LumiBokehBlur:updateStar()
    self.objStar.visible = true
    self.bufBokeh.width = math.ceil(self.scaledCanvasW)
    self.bufBokeh.height = math.ceil(self.scaledCanvasH)

    local sampleScale = self.mix(2.5, 1, self.scale / self.MAX_SCALE)
    local samplesCore = math.ceil(math.pi * self.scaledSize * self.scaledSize / sampleScale * 0.80)
    local samplesEdge = math.ceil(2 * math.pi * self.scaledSize / sampleScale * 4.00)
    self.matStar:setInt("u_samplesCore", samplesCore)
    self.matStar:setInt("u_samplesEdge", samplesEdge)
    self.matStar:setInt("u_lineNum", self.lineNum)
    self.matStar:setVec2("u_screenSize", Amaz.Vector2f(self.scaledCanvasW, self.scaledCanvasH))
    self.matStar:setVec2("u_scale", Amaz.Vector2f(self.scaleX, self.scaleY))
    self.matStar:setFloat("u_radius", self.scaledSize)
    self.matStar:setFloat("u_angle0", self.getStarAngle0(self.lineNum, self.angle))
    self.matStar:setFloat("u_regionIns", self.regionIns)
    self.matStar:setFloat("u_lightIns", self.lightIns)
    self.matStar:setFloat('u_shapeIns', self.shapeIns)

    --Amaz.LOGE("", string.format("samplesCore: %d", samplesCore))
    --Amaz.LOGE("", string.format("samplesEdge: %d", samplesEdge))
end

function LumiBokehBlur:updateHeart()
    self.objHeart.visible = true
    self.bufBokeh.width = math.ceil(self.scaledCanvasW)
    self.bufBokeh.height = math.ceil(self.scaledCanvasH)

    local sampleScale = self.mix(2.5, 1, self.scale / self.MAX_SCALE)
    local samplesCore = math.ceil(math.pi * self.scaledSize * self.scaledSize / sampleScale * 0.80)
    local samplesEdge = self.mix(90, 360, self.quality)--math.ceil(2 * math.pi * self.scaledSize / sampleScale * 4.00)
    self.matHeart:setInt("u_samplesCore", samplesCore)
    self.matHeart:setInt("u_samplesEdge", samplesEdge)
    self.matHeart:setVec2("u_screenSize", Amaz.Vector2f(self.scaledCanvasW, self.scaledCanvasH))
    self.matHeart:setVec2("u_scale", Amaz.Vector2f(self.scaleX, self.scaleY * 0.8))
    self.matHeart:setFloat("u_radius", self.scaledSize)
    self.matHeart:setFloat("u_regionIns", self.regionIns)
    self.matHeart:setFloat("u_lightIns", self.lightIns)
    self.matHeart:setFloat("u_shapeIns", self.shapeIns)
    self.matHeart:setFloat("u_angle0", math.rad(self.angle + 180))

    --Amaz.LOGE("", string.format("samplesCore: %d", samplesCore))
    --Amaz.LOGE("", string.format("samplesEdge: %d", samplesEdge))
end

function LumiBokehBlur:updateCustom()
    self.objMask.visible = true
    self.objCustom.visible = true
    self.bufBokeh.width = math.ceil(self.scaledCanvasW)
    self.bufBokeh.height = math.ceil(self.scaledCanvasH)

    local maskSize = self.mix(self.scaledSize, self.scale, self.quality) * 2
    local maskSizeI = math.max(math.ceil(maskSize), 8)
    if self.customMaskTex then
        self.bufMask.width = self.MAX_SCALE * 2
        self.bufMask.height = self.MAX_SCALE * 2
        self.interface:set("maskSize", maskSizeI)
        self.matMask:setTex("u_maskTex", self.customMaskTex)
    end

    self.matCustom:setVec2("u_screenSize", Amaz.Vector2f(self.scaledCanvasW, self.scaledCanvasH))
    self.matCustom:setVec2("u_scale", Amaz.Vector2f(self.scaleX, self.scaleY))
    self.matCustom:setInt("u_samples", math.ceil(self.scaledSize * 0.7))
    self.matCustom:setFloat("u_radius", self.scaledSize)
    self.matCustom:setFloat("u_regionIns", self.regionIns)
    self.matCustom:setFloat("u_lightIns", self.lightIns)
    self.matCustom:setFloat("u_angle0", math.rad(self.angle + 180))

    --Amaz.LOGE("", string.format("maskSize: %d", maskSizeI))
end

function LumiBokehBlur.mix(a, b, t)
    return a + (b - a) * t
end

exports.LumiBokehBlur = LumiBokehBlur
return exports
