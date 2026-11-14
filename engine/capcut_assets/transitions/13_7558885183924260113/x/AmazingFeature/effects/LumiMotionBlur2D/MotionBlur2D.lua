local exports = exports or {}
local MotionBlur2D = MotionBlur2D or {}
MotionBlur2D.__index = MotionBlur2D
---@class MotionBlur2D: ScriptComponent
---@field currRotate double [UI(Range={0, 360}, Slider)]
---@field currAnchor Vector2f [UI(Drag=0.01)]
---@field currPosition Vector2f [UI(Drag=0.01)]
---@field unifiedScale boolean
---@field currScale Vector2f [UI(Drag=0.01)]
---@field vIntensity double [UI(Range={0, 2}, Slider)]
---@field vCenter double [UI(Range={-1, 1}, Slider)]
---@field minSamples double [UI(Range={0, 256}, Slider)]
---@field maxSamples double [UI(Range={0, 256}, Slider)]
---@field dither double [UI(Range={0, 1}, Slider)]
---@field mirrorEdge boolean
---@field InputTex Texture
---@field OutputTex Texture

function MotionBlur2D.new(construct, ...)
    local self = setmetatable({}, MotionBlur2D)
    if construct and MotionBlur2D.constructor then
        MotionBlur2D.constructor(self, ...)
    end
    self.startTime = 0.0
    self.endTime = 1.0
    self.curTime = 0.0
    self.firstSeek = true
    
    self.prevRotate = 0
    self.prevPosition = Amaz.Vector2f(0., 0.)
    self.prevScale = Amaz.Vector2f(1, 1)
    self.prevAnchor = Amaz.Vector2f(0., 0.)
    self.currRotate = 0
    self.currPosition = Amaz.Vector2f(0., 0.)
    self.currScale = Amaz.Vector2f(1, 1)
    self.currAnchor = Amaz.Vector2f(0., 0.)
    self.positionVec2Vector = Amaz.Vec2Vector()

    self.vIntensity = 1.0
    self.vCenter = 0.0
    self.minSamples = 2.0
    self.maxSamples = 24.0
    self.dither = 1.0
    self.mirrorEdge = false
    self.unifiedScale = false
    
    self.InputTex = nil
    self.OutputTex = nil
    return self
end

function MotionBlur2D:constructor()
end

function MotionBlur2D:onUpdate(comp, detalTime)
    self:seekToTime(comp, detalTime)

    self.material:setTex("u_inputImageTexture", self.InputTex)
    self.cam.renderTexture = self.OutputTex
end

function MotionBlur2D:start(comp)
    self.first = true
    self.material = comp.entity:searchEntity("motion_blur_2d"):getComponent("MeshRenderer").material
    self.cam = comp.entity:searchEntity("cam"):getComponent("Camera")
end

function MotionBlur2D:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value)
        if self[_key] ~= nil then
            self[_key] = _value
            if comp and comp.properties ~= nil then
                comp.properties:set(_key, _value)
            end
        end
    end

    if key == "maxSamples" or key == "minSamples" then
        _setEffectAttr(key, math.floor(value * 100))
    elseif key == "rotate" then
        _setEffectAttr("currRotate", value)
    elseif key == "ae_pre_rotate" then
        _setEffectAttr("prevRotate", value)
    elseif key == "scale_x" or key == "scale_y" then
        local currScale = self["currScale"]
        if currScale then
            if math.abs(value)<0.001 then value = 0.001 end
            if key == "scale_x" then
                currScale.x = value
            else
                currScale.y = value
            end
            _setEffectAttr("currScale", currScale)
        end
    elseif key == "position" then
        local currPosition = self["currPosition"]
        if currPosition then
            currPosition.x = value.x - 0.5
            currPosition.y = value.y - 0.5
            _setEffectAttr("currPosition", currPosition)
        end
    elseif key == "ae_pre_position" then
        local prevPosition = self["prevPosition"]
        if prevPosition then
            prevPosition.x = value.x - 0.5
            prevPosition.y = value.y - 0.5
            _setEffectAttr("prevPosition", prevPosition)
        end
    elseif key == "anchor" then
        local currAnchor = self["currAnchor"]
        if currAnchor then
            currAnchor.x = value.x - 0.5
            currAnchor.y = value.y - 0.5
            _setEffectAttr("currAnchor", currAnchor)
        end
    elseif key == "ae_pre_anchor" then
        local prevAnchor = self["prevAnchor"]
        if prevAnchor then
            prevAnchor.x = value.x - 0.5
            prevAnchor.y = value.y - 0.5
            _setEffectAttr("prevAnchor", prevAnchor)
        end
    elseif key == "ae_pre_scale_x" or key == "ae_pre_scale_y" then
        local prevScale = self["prevScale"]
        if prevScale then
            if math.abs(value)<0.001 then value = 0.001 end
            if key == "ae_pre_scale_x" then
                prevScale.x = value
            else
                prevScale.y = value
            end
            _setEffectAttr("prevScale", prevScale)
        end
    else
        _setEffectAttr(key, value)
    end

end

function MotionBlur2D:seekToTime(comp, time)
    if self.first == nil then
        self:start(comp)
    end

    self.curTime = (self.curTime + time)%(self.endTime - self.startTime)

    local pointSize = 5;
    local pivotVec2Vector = Amaz.Vec2Vector()
    local positionVec2Vector = Amaz.Vec2Vector()
    local scaleVec2Vector = Amaz.Vec2Vector()
    local rotationFloatVector = Amaz.FloatVector()
    for i=0,pointSize,1 do
        local w = (self.vIntensity * (i/pointSize) + self.vCenter + 1.0);
        -- Offset keyframe with curve
        -- local frameTime = 1./ 90.0
        -- local AEprogress = progress + frameTime*(w-1.0)
        -- positionVec2Vector:pushBack(self:getOffset(AEprogress))
        local pivot = self.prevAnchor * (1.0-w) + self.currAnchor * w;
        local position = self.prevPosition * (1.0-w) + self.currPosition * w;
        local scale = self.prevScale * (1.0-w) + self.currScale * w;
        if self.unifiedScale then
            scale.y = scale.x
        end
        local rotation = self.prevRotate * (1.0-w) + self.currRotate * w;
        pivotVec2Vector:pushBack(pivot)
        positionVec2Vector:pushBack(position)
        scaleVec2Vector:pushBack(scale)
        rotationFloatVector:pushBack(rotation)
    end
    self.material:setVec2Vector("u_pivotVec2Vector", pivotVec2Vector)
    if self.positionVec2Vector:empty() then
        self.material:setVec2Vector("u_positionVec2Vector", positionVec2Vector)
    else
        self.material:setVec2Vector("u_positionVec2Vector", self.positionVec2Vector)
    end
    self.material:setVec2Vector("u_scaleVec2Vector", scaleVec2Vector)
    self.material:setFloatVector("u_rotationFloatVector", rotationFloatVector)

    self.material:setFloat("u_minSamples", self.minSamples);
    self.material:setFloat("u_maxSamples", self.maxSamples);
    self.material:setFloat("u_dither", self.dither);
    self.material:setFloat("u_mirrorEdge", self.mirrorEdge and 1 or 0)
    if math.abs(self.vIntensity) < 0.001 then 
        self.material:setInt("u_skipSample", 1)
    else
        self.material:setInt("u_skipSample", 0)
    end
end

function MotionBlur2D:onLateUpdate(comp, detalTime)

end

local function clamp(val, min, max)
    return math.max(math.min(val, max), min)
end

exports.MotionBlur2D = MotionBlur2D
return exports
