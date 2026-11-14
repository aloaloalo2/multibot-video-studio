      
local isEditor = (Amaz.Macros and Amaz.Macros.EditorSDK) and true or false
local exports = exports or {}
local MotionBlur3D = MotionBlur3D or {}
MotionBlur3D.__index = MotionBlur3D
---@class MotionBlur3D : ScriptComponent
---@field active_cam_fovx number
---@field vIntensity number
---@field vCenter number
---@field samples number
---@field dither double [UI(Range={0, 1}, Slider)]
---@field pivot Vector3f
---@field position Vector3f
---@field unifiedScale boolean
---@field scale Vector3f
---@field direction Vector3f
---@field rotation Vector3f
---@field alpha number [UI(Range={0, 1}, Slider)]
---@field mirrorEdge boolean
---@field InputTex Texture
---@field OutputTex Texture

function MotionBlur3D.new(construct, ...)
    local self = setmetatable({}, MotionBlur3D)

    self.vCenter = 0.0
    self.vIntensity = 1.0
    self.samples = 50
    self.dither = 1.0

    self.active_cam_fovx = 39.6

    self.pivot = Amaz.Vector3f(0,0,0)
    self.position = Amaz.Vector3f(0,0,0)
    self.scale = Amaz.Vector3f(1,1,1)
    self.direction = Amaz.Vector3f(0,0,0)
    self.rotation = Amaz.Vector3f(0,0,0)
    self.alpha = 1

    self.prePivot = Amaz.Vector3f(0,0,0)
    self.prePosition = Amaz.Vector3f(0,0,0)
    self.preScale = Amaz.Vector3f(1,1,1)
    self.preDirection = Amaz.Vector3f(0,0,0)
    self.preRotation = Amaz.Vector3f(0,0,0)
    self.mirrorEdge = false
    self.unifiedScale = false
    
    self.InputTex = nil
    self.OutputTex = nil

    self.first = true
    if construct and MotionBlur3D.constructor then MotionBlur3D.constructor(self, ...) end
    return self
end

function MotionBlur3D:onStart(comp)
    self.entity = comp.entity
    self.ae_cam = self.entity:searchEntity("cam_ae_transform"):getComponent("Camera")
    self.father_trans = self.entity:searchEntity("father_trans"):getComponent("Transform")
    self.child_trans = self.entity:searchEntity("child_trans"):getComponent("Transform")

    self.child_renderer = self.child_trans.entity:getComponent("MeshRenderer")
    self.child_mat = self.child_trans.entity:getComponent("MeshRenderer").material
end

function MotionBlur3D:_rotateByAEAxis(_trans, _direction, _euler_angle)
    -- ae xyz, editor yxz
    local right   = Amaz.Vector3f(1.0, 0.0, 0.0)
    local up      = Amaz.Vector3f(0.0, 1.0, 0.0)
    local forward = Amaz.Vector3f(0.0, 0.0, 1.0)

    local cur_orientation = Amaz.Quaternionf.axisAngleToQuaternion(right,    math.rad(_direction.x))
                          * Amaz.Quaternionf.axisAngleToQuaternion(up,      -math.rad(_direction.y))
                          * Amaz.Quaternionf.axisAngleToQuaternion(forward, -math.rad(_direction.z))

    up      = Amaz.Quaternionf.rotateVectorByQuat(cur_orientation, up)
    right   = Amaz.Quaternionf.rotateVectorByQuat(cur_orientation, right)
    forward = Amaz.Quaternionf.rotateVectorByQuat(cur_orientation, forward)

    cur_orientation = Amaz.Quaternionf.axisAngleToQuaternion(right,    math.rad(_euler_angle.x))
                    * Amaz.Quaternionf.axisAngleToQuaternion(up,      -math.rad(_euler_angle.y))
                    * Amaz.Quaternionf.axisAngleToQuaternion(forward, -math.rad(_euler_angle.z))
                    * cur_orientation
    
    _trans.localOrientation = cur_orientation
end

function MotionBlur3D:cauleMVP(position, direction, rotation, pivot, scale)
    self.width = Amaz.BuiltinObject:getInputTextureWidth()
    self.height = Amaz.BuiltinObject:getInputTextureHeight()
    if self.OutputTex then
        self.width = self.OutputTex.width
        self.height = self.OutputTex.height
    end
    local ratio = self.width / self.height
    local pos_z0 = ratio / math.tan(math.rad(self.active_cam_fovx * 0.5))
    self.ae_cam.fovy = 2 * math.deg(math.atan(1 / pos_z0))
    self:_rotateByAEAxis(self.father_trans, direction, rotation)
    self.father_trans.localPosition = Amaz.Vector3f(
        (position.x - 0.5) * 2 * ratio,
        (position.y - 0.5) * 2,
        -pos_z0 - position.z * 2
    )
    self.child_trans.localPosition = Amaz.Vector3f(
        -(pivot.x - 0.5) * 2 * ratio,
        -(pivot.y - 0.5) * 2,
        pivot.z * 2
    )
    self.child_trans.localEulerAngle = Amaz.Vector3f(0, 0, 0)

    self.father_trans.localScale = Amaz.Vector3f(scale.x, scale.y, scale.z)
    self.child_trans.localScale = Amaz.Vector3f(ratio,1,1)

    local u_M = self.child_trans:getWorldMatrix()
    local u_V = self.ae_cam:getWorldToCameraMatrix()
    local u_P = self.ae_cam.projectionMatrix
    if self.child_renderer.useCustomProjectMatrix then
        u_P = self.child_renderer.customProjectMatrix
    end

    -- local mvp = u_P * u_V * u_M

    return {u_V * u_M, u_P:invert_Full()}
end

function MotionBlur3D:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value)
        if self[_key] ~= nil then
            self[_key] = _value
            if comp and comp.properties ~= nil then
                comp.properties:set(_key, _value)
            end
        end
    end

    local function setParamVectorNf(paramKey, channel, paramValue)
        local pamam =self[paramKey]
        if pamam then
            pamam[channel] = paramValue
            _setEffectAttr(paramKey, pamam)
        end
    end

    local vectorNf_params = {
        scale_x = {"scale", "x"}, scale_y = {"scale", "y"}, scale_z = {"scale", "z"},
        direction_x = {"direction", "x"}, direction_y = {"direction", "y"}, direction_z = {"direction", "z"},
        rotation_x = {"rotation", "x"}, rotation_y = {"rotation", "y"}, rotation_z = {"rotation", "z"},
        ae_pre_scale_x = {"preScale", "x"}, ae_pre_scale_y = {"preScale", "y"}, ae_pre_scale_z = {"preScale", "z"},
        ae_pre_direction_x = {"preDirection", "x"}, ae_pre_direction_y = {"preDirection", "y"}, ae_pre_direction_z = {"preDirection", "z"},
        ae_pre_rotation_x = {"preRotation", "x"}, ae_pre_rotation_y = {"preRotation", "y"}, ae_pre_rotation_z = {"preRotation", "z"},
    }

    if vectorNf_params[key] then
        local paramKey = vectorNf_params[key][1]
        local channel = vectorNf_params[key][2]
        setParamVectorNf(paramKey, channel, value)
    elseif key == 'ae_pre_pivot' then
        _setEffectAttr('prePivot', value)
    elseif key == 'ae_pre_position' then
        _setEffectAttr('prePosition', value)
    else
        _setEffectAttr(key, value)
    end
end

function MotionBlur3D:onUpdate(comp, deltaTime)
    self.child_mat:setTex('u_inputTex', self.InputTex)
    self.ae_cam.renderTexture = self.OutputTex

    local size = 5;
    for i=0,size,1 do
        local w = (self.vIntensity * (i/size) + self.vCenter + 1.0);
        
        local pivot = self.prePivot * (1.0-w) + self.pivot * w;
        local position = self.prePosition * (1.0-w) + self.position * w;
        local scale = self.preScale * (1.0-w) + self.scale * w;
        if self.unifiedScale then
            scale.y = scale.x
            scale.z = scale.x
        end
        local direction = self.preDirection * (1.0-w) + self.direction * w;
        local rotation = self.preRotation * (1.0-w) + self.rotation * w;

        local mvp = self:cauleMVP(position, direction, rotation, pivot, scale)
        self.child_mat:setMat4('u_mvMat' .. i, mvp[1])
        self.child_mat:setMat4('u_pMat' .. i, mvp[2])
    end

    self.child_mat:setFloat('u_alpha', self.alpha)
    self.child_mat:setFloat('u_center', self.vCenter)
    self.child_mat:setFloat('u_samples', self.samples)
    self.child_mat:setFloat('u_dither', self.dither)
    self.child_mat:setFloat('u_mirrorEdge', self.mirrorEdge and 1 or 0)
    self.child_mat:setInt('u_skipSample', math.abs(self.vIntensity) < 0.001 and 1 or 0)
end

exports.MotionBlur3D = MotionBlur3D
return exports
