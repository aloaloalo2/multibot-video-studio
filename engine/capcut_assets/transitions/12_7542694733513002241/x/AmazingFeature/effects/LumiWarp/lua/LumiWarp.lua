---@class LumiWarp : ScriptComponent
---@field warpStyle string [UI(Option={"Arc","Arc Lower","Arc Upper","Arch","Bulge","Shell Lower","Shell Upper","Flag","Wave","Fish","Rise","FishEye","Inflate","Twist","Squeeze"})]
---@field warpAxis string [UI(Option={"Horizontal","Vertical"})]
---@field bend number [UI(Range={-100, 100}, Drag)]
---@field horizontalBend number [UI(Range={-1., 1.}, Drag)]
---@field verticalBend number [UI(Range={-1., 1.}, Drag)]
---@field InputTex Texture
---@field OutputTex Texture
local WarpStyles = {
    "Arc", "Arc Lower", "Arc Upper", "Arch", "Bulge", "Shell Lower",
    "Shell Upper", "Flag", "Wave", "Fish", "Rise", "FishEye", "Inflate",
    "Twist", "Squeeze"
}
setmetatable(WarpStyles, {__index = function(_, _) return WarpStyles[1] end})
local WarpStyleIndex = {}
for index, value in ipairs(WarpStyles) do WarpStyleIndex[value] = index - 1 end

local exports = exports or {}
local LumiWarp = LumiWarp or {}
LumiWarp.__index = LumiWarp

------------ class functions for ScriptComponent ------------
function LumiWarp.new(construct, ...)
    local self = setmetatable({}, LumiWarp)

    if construct and LumiWarp.constructor then
        LumiWarp.constructor(self, ...)
    end

    self.__lumi_type = "lumi_effect"
    self.__lumi_rt_pingpong_type = "custom"

    self.warpStyle = "Arc"
    self.warpAxis = "Horizontal"

    self.bend = 0.
    self.horizontalBend = 0.
    self.verticalBend = 0.

    self.InputTex = nil
    self.OutputTex = nil

    return self
end

function LumiWarp:onStart(comp)
    self.matWarp = comp.entity:searchEntity("PassWarp"):getComponent("MeshRenderer").material
    self.camWarp = comp.entity:searchEntity("CameraWarp"):getComponent("Camera")
end

function LumiWarp:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value)
        if self[_key] ~= nil then
            self[_key] = _value
            if comp and comp.properties ~= nil then
                comp.properties:set(_key, _value)
            end
        end
    end

    if key == "warpStyle" then
        local style = WarpStyles[value + 1]

        _setEffectAttr(key, style)
    elseif key == "warpAxis" then
        local axis = "Horizontal"
        if value == 1 then axis = "Vertical" end
        _setEffectAttr(key, axis)
    else
        _setEffectAttr(key, value)
    end
end

function LumiWarp:onUpdate(comp, detalTime)
    self.matWarp:setTex("u_inputTex", self.InputTex)
    if self.OutputTex then self.camWarp.renderTexture = self.OutputTex end

    local bend = self.bend / 100
    self.matWarp:setFloat("u_bend", bend)

    if self.warpAxis == "Horizontal" then
        self.matWarp:setInt("u_axisFrag", 0)
        self.matWarp:setInt("u_axisVert", 0)
    else
        self.matWarp:setInt("u_axisFrag", 1)
        self.matWarp:setInt("u_axisVert", 1)
    end

    self.matWarp:setInt("u_warpStyleVert", WarpStyleIndex[self.warpStyle])
    self.matWarp:setInt("u_warpStyleFrag", WarpStyleIndex[self.warpStyle])

end

exports.LumiWarp = LumiWarp
return exports
