
local isEditor = (Amaz.Macros and Amaz.Macros.EditorSDK) and true or false

local exports = exports or {}
local LumiBokehBlur = LumiBokehBlur or {}
---@class LumiBokehBlur: ScriptComponent [UI(Display="The Circle Bokeh")]
---@field bokehMode string [UI(Option={"Circle", "Heart", "Polygon"})]
---@field sample number [UI(Range={0., 80}, Drag)]
---@field scaleX number  [UI(Range={0, 1}, Drag)]
---@field scaleY number [UI(Range={0, 1}, Drag)]
---@field regionIns number [UI(Range={0., 1}, Drag)]
---@field lightIns number [UI(Range={0, 2}, Drag)]
---@field quality number [UI(Range={0., 1}, Drag)]
---@field lineNum int   [UI(Range={3, 8}, Slider)]
---@field angle number [UI(Range={-180, 180}, Drag)]
---@field InputTex Texture
---@field OutputTex Texture
---@field lumiSharedRt Vector [UI(Type="Texture")]

local BokehModeName = {
    "Circle", "Heart", "Polygon"
}
setmetatable(BokehModeName, {__index = function(_, _) return BokehModeName[1] end})

local function mix(a, b, x)
    return a * (1 - x) + b * x
end

local function getRotPos(pos, angle)
    local s = math.sin(angle)
    local c = math.cos(angle)
    return Amaz.Vector2f(pos.x * c - pos.y * s, pos.y * c + pos.x * s)
end

local function getRotPosVec(n, angle, scaleX, scaleY)
    local posVec = Amaz.Vec2Vector()
    local pos = Amaz.Vector2f(0, 11)
    pos = getRotPos(pos, angle)
    posVec:pushBack(Amaz.Vector2f(pos.x * scaleX,pos.y * scaleY))
    for i = 1 , n - 1 do
        local tempPos = getRotPos(pos, math.pi * i / n * 2.)
        posVec:pushBack(Amaz.Vector2f(tempPos.x * scaleX, tempPos.y * scaleY))
    end
    posVec:pushBack(Amaz.Vector2f(pos.x * scaleX, pos.y * scaleY))
    return posVec
end

LumiBokehBlur.__index = LumiBokehBlur
function LumiBokehBlur.new(construct, ...)
    local self = setmetatable({}, LumiBokehBlur)
    if construct and LumiBokehBlur.constructor then LumiBokehBlur.constructor(self, ...) end
    self.bokehMode = "Circle"
    self.size = 0.7
    self.scaleX = 1
    self.scaleY = 1
    self.regionIns = 0.5
    self.lightIns = 1
    self.quality = 1
    self.sample = 79

    -- polygon extra param
    self.angle = 0
    self.lineNum = 5
    self.lastLineNum = -1
    self.lastScaleX = -1
    self.lastScaleY = -1
    self.lastAngle = -1
    self.first = true

    return self
end

function LumiBokehBlur:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value)
        if self[_key] ~= nil then
            self[_key] = _value
            if comp and comp.properties ~= nil then
                comp.properties:set(_key, _value)
            end
        end
    end

    if key == 'bokehMode' then
        local bokehMode = BokehModeName[value + 1]
        _setEffectAttr(key, bokehMode)
    else
        _setEffectAttr(key, value)
    end
end

function LumiBokehBlur:onStart(comp)
    self.blur0Material = comp.entity:searchEntity("blur0"):getComponent("MeshRenderer").material
    self.blur1Material = comp.entity:searchEntity("blur1"):getComponent("MeshRenderer").material
    self.in2outMaterial = comp.entity:searchEntity("in2out"):getComponent("MeshRenderer").material

    self.circleEntity = comp.entity:searchEntity("circleCam")
    self.heartEntity = comp.entity:searchEntity("heartCam")
    self.polygonEntity = comp.entity:searchEntity("polygonCam")
    self.circleMaterial = self.circleEntity:searchEntity("circle"):getComponent("MeshRenderer").material
    self.heartMaterial = self.heartEntity:searchEntity("heart"):getComponent("MeshRenderer").material
    self.polygonMaterial = self.polygonEntity:searchEntity("polygon"):getComponent("MeshRenderer").material
    self.circleCamera = self.circleEntity:getComponent("Camera")
    self.heartCamera = self.heartEntity:getComponent("Camera")
    self.polygonCamera = self.polygonEntity:getComponent("Camera")

    self.outCamera = comp.entity:searchEntity("in2outCam"):getComponent("Camera")
    self.blur0Camera = comp.entity:searchEntity("blur0Cam"):getComponent("Camera")
    self.midCamera = comp.entity:searchEntity("blur1Cam"):getComponent("Camera")

    if self.lumiSharedRt and self.lumiSharedRt:size() > 0 then
        self.midTex = self.lumiSharedRt:get(0)
    end
end

function LumiBokehBlur:onUpdate(comp, detalTime)
    self.outCamera.renderTexture = self.OutputTex
    self.blur0Camera.renderTexture = self.OutputTex
    if self.midTex.width ~= self.OutputTex.width
    or self.midTex.height ~= self.OutputTex.height
    then
        self.midTex.width = self.OutputTex.width
        self.midTex.height = self.OutputTex.height
    end

    self.midCamera.renderTexture = self.midTex
    
    if self.bokehMode == 'Heart' then
        self.circleEntity.visible = false
        self.heartEntity.visible = true
        self.polygonEntity.visible = false
        self.cameraRT = self.heartCamera.renderTexture
        self.bokehMaterial = self.heartMaterial
    elseif self.bokehMode == 'Polygon' then
        self.circleEntity.visible = false
        self.heartEntity.visible = false
        self.polygonEntity.visible = true
        self.cameraRT = self.polygonCamera.renderTexture
        self.bokehMaterial = self.polygonMaterial

        if self.lineNum ~= self.lastLineNum
        or self.lastAngle ~= self.angle
        or self.scaleX ~= self.lastScaleX
        or self.scaleY ~= self.lastScaleY
        or self.first == true then
            local posVec = getRotPosVec(self.lineNum, math.rad(-self.angle), self.scaleX, self.scaleY)
            self.polygonMaterial:setVec2Vector("u_posVec", posVec)
            self.polygonMaterial:setInt('u_lineNum', self.lineNum)
            self.lastLineNum = self.lineNum
            self.lastAngle = self.angle
            self.lastScaleX = self.scaleX
            self.lastScaleY = self.scaleY
            self.first = false
        end
    else
        self.circleEntity.visible = true
        self.heartEntity.visible = false
        self.polygonEntity.visible = false
        self.cameraRT = self.circleCamera.renderTexture
        self.bokehMaterial = self.circleMaterial
    end

    self:updateMatrial()
end

function LumiBokehBlur:updateMatrial()
    self.blur0Material:setTex("u_inputTex", self.InputTex)
    self.blur1Material:setTex("u_inputTex", self.blur0Camera.renderTexture)
    self.bokehMaterial:setTex("u_inputTex", self.midTex)
    
    local w = self.OutputTex.width
    local h = self.OutputTex.height

    local intensity = self.sample / 79
    local blur_intensity = math.pow(intensity, 0.35)

    self.cameraRT.width  = w * mix(1.0, mix(0.3, 0.4, self.quality), blur_intensity)
    self.cameraRT.height = h * mix(1.0, mix(0.3, 0.4, self.quality), blur_intensity)

    self.blur0Material:setFloat("u_sample", 22. * blur_intensity * self.size)
    self.blur1Material:setFloat("u_sample", 22. * blur_intensity * self.size)
    self.blur0Material:setFloat("u_baseTexWidth", w)
    self.blur0Material:setFloat("u_baseTexHeight", h)
    self.blur1Material:setFloat("u_baseTexWidth", w)
    self.blur1Material:setFloat("u_baseTexHeight", h)
    self.in2outMaterial:setFloat("u_baseTexWidth", w)
    self.in2outMaterial:setFloat("u_baseTexHeight", h)
    self.bokehMaterial:setFloat("u_baseTexWidth", w)
    self.bokehMaterial:setFloat("u_baseTexHeight", h)
    self.bokehMaterial:setFloat("u_blurSize", 7.5 * intensity * self.size)
    self.bokehMaterial:setFloat("u_scaleX", self.scaleX)
    self.bokehMaterial:setFloat("u_scaleY", self.scaleY)
    self.bokehMaterial:setFloat("u_intensity", blur_intensity)
    self.bokehMaterial:setFloat("u_regionIns", self.regionIns)
    self.bokehMaterial:setFloat("u_lightIns", self.lightIns)
    self.bokehMaterial:setFloat("u_quality", self.quality)
    self.bokehMaterial:setFloat("u_angle", math.rad(-self.angle))
end

exports.LumiBokehBlur = LumiBokehBlur
return exports
