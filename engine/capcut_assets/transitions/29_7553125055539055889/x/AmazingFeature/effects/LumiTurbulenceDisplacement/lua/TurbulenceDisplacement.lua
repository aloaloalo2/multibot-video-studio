local exports = exports or {}
local TurbulenceDisplacement = TurbulenceDisplacement or {}
TurbulenceDisplacement.__index = TurbulenceDisplacement
---@class TurbulenceDisplacement : ScriptComponent
---@field size number
---@field quantity number
---@field complexity number
---@field evolution number
---@field cycle int [UI(Range={1, 100}, Slider)]
---@field offset_x number
---@field offset_y number
---@field type number
---@field fix_type number
---@field picture_scale number
---@field motion_tile_type number
---@field qualityType string [UI(Option={"Ultimate", "High", "Medium", "Low"})]
---@field InputTex Texture
---@field OutputTex Texture

function TurbulenceDisplacement.new(construct, ...)
    local self = setmetatable({}, TurbulenceDisplacement)
    if construct and TurbulenceDisplacement.constructor then
        TurbulenceDisplacement.constructor(self, ...)
    end

    self.InputTex = nil
    self.OutputTex = nil

    self.size = 0
    self.quantity = 2
    self.complexity = 1
    self.evolution = 0
    self.cycle = 100
    self.offset_x = 0
    self.offset_y = 0
    self.type = 0
    self.fix_type = 0
    self.qualityType = "Low"
    self.motion_tile_type = 0
    self.picture_scale = 1

    return self
end

function TurbulenceDisplacement:constructor()
end

function TurbulenceDisplacement:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value)
        if self[_key] ~= nil then
            self[_key] = _value
            if comp and comp.properties ~= nil then
                comp.properties:set(_key, _value)
            end
        end
    end

    if "qualityType" == key then
        local qualityType = "Low"
        if value == 0 then qualityType = "Ultimate" end
        if value == 1 then qualityType = "High" end
        if value == 2 then qualityType = "Medium" end
        _setEffectAttr(key, qualityType)
    else
        _setEffectAttr(key, value)
    end
end

function TurbulenceDisplacement:onUpdate(comp, detalTime)
    if self.first == nil then
        self:start(comp)
    end
    self.camera.renderTexture = self.OutputTex

    local noiseTexSize = 1.0
    if self.qualityType == "Ultimate" then 
        noiseTexSize = 1.0
    elseif self.qualityType == "High" then 
        noiseTexSize = 0.75
    elseif self.qualityType == "Medium" then 
        noiseTexSize = 0.5
    elseif self.qualityType == "Low" then 
        noiseTexSize = 0.25
    end
    self.noiseCamera.renderTexture.width = noiseTexSize * self.OutputTex.width
    self.noiseCamera.renderTexture.height = noiseTexSize * self.OutputTex.height

    self.noiseMaterial:setVec2("u_Scale", Amaz.Vector2f(self.quantity, self.quantity));
    self.noiseMaterial:setFloat("u_Complexity", self.complexity);
    self.noiseMaterial:setFloat("u_Evolution", math.abs(self.evolution) / 90.0);
    self.noiseMaterial:setFloat("u_Cycle", math.max(2, math.floor(self.cycle*3.0 + 0.5)));
    self.noiseMaterial:setVec2("u_Offset", Amaz.Vector2f(self.offset_x, self.offset_y))
    self.noiseMaterial:setFloat("u_type", self.type);
    self.noiseMaterial:setFloat("picture_scale", self.picture_scale)
    
    self.material:setTex("inputImageTexture", self.InputTex)
    self.material:setFloat("u_Contrast", self.size);
    self.material:setVec2("u_Scale", Amaz.Vector2f(self.quantity, self.quantity));
    self.material:setFloat("u_type", self.type);
    self.material:setFloat("u_fix_type", self.fix_type)
    self.material:setFloat("motion_tile_type", self.motion_tile_type)
    self.material:setFloat("picture_scale", self.picture_scale)
end

function TurbulenceDisplacement:onStart(comp)
    self:start(comp)
end

function TurbulenceDisplacement:start(comp)
    self.first = true
    self.camera = comp.entity:searchEntity("cam_Displacement"):getComponent("Camera")
    self.material = comp.entity:searchEntity("Displacement"):getComponent("MeshRenderer").material
    self.noiseCamera = comp.entity:searchEntity("cam_Noise"):getComponent("Camera")
    self.noiseMaterial = comp.entity:searchEntity("Noise"):getComponent("MeshRenderer").material
end

exports.TurbulenceDisplacement = TurbulenceDisplacement
return exports
