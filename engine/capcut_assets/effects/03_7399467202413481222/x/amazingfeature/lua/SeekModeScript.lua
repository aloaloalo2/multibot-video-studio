--@input float curTime = 0.0{"widget":"slider","min":0,"max":1}

local exports = exports or {}
local SeekModeScript = SeekModeScript or {}
SeekModeScript.__index = SeekModeScript
function SeekModeScript.new(construct, ...)
    local self = setmetatable({}, SeekModeScript)
    if construct and SeekModeScript.constructor then SeekModeScript.constructor(self, ...) end
    self.startTime = 0.0
    self.endTime = 3.0
    self.curTime = 0.0
    self.width = 0
    self.height = 0
    return self
end

function SeekModeScript:constructor()

end

function SeekModeScript:onUpdate(comp, detalTime)
    --ccc
    --local props = comp.entity:getComponent("ScriptComponent").properties
    --if props:has("curTime") then
        --self:seekToTime(comp, props:get("curTime"))
    --end
    --ccc
    self:seekToTime(comp, self.curTime - self.startTime)
end

function SeekModeScript:onStart(comp)
    self.material = comp.entity:getComponent("MeshRenderer").material
    self.material:setFloat("sizeFactor", 1.0) 
end

function SeekModeScript:seekToTime(comp, time)

    --self.material:setFloat("timer", time)
    
    local w = Amaz.BuiltinObject:getInputTextureWidth()
    local h = Amaz.BuiltinObject:getInputTextureHeight()
    if w ~= self.width or h ~= self.height then
        self.width = w
        self.height = h
        self.material:setInt("baseTexWidth", self.width)
        self.material:setInt("baseTexHeight", self.height)
    end
end

function SeekModeScript:onEvent(sys, event)
    if "effects_adjust_texture" == event.args:get(0) then
        local intensity = event.args:get(1)
        self.material:setFloat("alphaFactor", intensity+0.01) 
    end
    if "effects_adjust_size" == event.args:get(0) then
        local intensity = event.args:get(1)
        self.material:setFloat("sizeFactor", 1.0-0.5*intensity) 
    end
end

exports.SeekModeScript = SeekModeScript
return exports
