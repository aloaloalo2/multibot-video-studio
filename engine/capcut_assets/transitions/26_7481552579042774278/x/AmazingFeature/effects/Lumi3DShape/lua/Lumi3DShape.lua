      
local isEditor = (Amaz.Macros and Amaz.Macros.EditorSDK) and true or false
local exports = exports or {}
local Lumi3DShape = Lumi3DShape or {}
Lumi3DShape.__index = Lumi3DShape
---@class Lumi3DShape : ScriptComponent
---@field InputTex Texture
---@field OutputTex Texture
---@field fov number [UI(Range={0.0, 180.0}, Drag)]
---@field position Vector3f
---@field scale Vector3f
---@field rotate Vector3f
---@field meshSize Vector3f
---@field meshResX number [UI(Range={1, 100.0}, Drag=1)]
---@field meshResY number [UI(Range={1, 100.0}, Drag=1)]
---@field meshResZ number [UI(Range={1, 100.0}, Drag=1)]
---@field reverseUV Bool
---@field cullBack Bool
---@field translucency Bool
---@field twoSide Bool
---@field meshType string [UI(Option={"quad", "ellipse", "ring", "cube", "sphere", "cylinder", "donut"})]
---@field inputImage Texture
---@field texFillMode string [UI(Option={"stretch", "fill", "fit", "repeat&stretch", "repeat&fill"})]
---@field uvScaleX number [UI(Range={0.01, 100.0}, Drag)]
---@field uvScaleY number [UI(Range={0.01, 100.0}, Drag)]
---@field uvWrapMode string [UI(Option={"clamp", "repeat", "mirror", "black", "white", "translucent"})]
---@field enableMask Bool
---@field mask Texture
---@field maskChannel string [UI(Option={"R", "G", "B", "A"})]

function Lumi3DShape.new(construct, ...)
    local self = setmetatable({}, Lumi3DShape)

    if construct and Lumi3DShape.constructor then Lumi3DShape.constructor(self, ...) end

    self.InputTex = nil
    self.OutputTex = nil
    self.texture = nil

    -- camera
    self.fov = 60

    -- mesh
    self.position = Amaz.Vector3f(0, 0, -5)
    self.scale = Amaz.Vector3f(1, 1, 1)
    self.rotate = Amaz.Vector3f(0.0, 0.0, 0.0)
    self.meshSize = Amaz.Vector3f(2, 3, 4)
    self.meshResX = 20
    self.meshResY = 20
    self.meshResZ = 20
    self.reverseUV = false
    self.cullBack = false
    self.translucency = false
    self.twoSide = false
    self.meshType = "quad"

    -- texture
    self.inputImage = nil
    self.texFillMode = "stretch"
    self.uvScaleX = 1.0
    self.uvScaleY = 1.0
    self.uvWrapMode = "mirror"

    -- mask
    self.enableMask = false
    self.mask = nil
    self.maskChannel = "A"

    self.meshGenerator = includeRelativePath("LumiMeshGenerator").LumiMeshGenerator

    return self
end

function Lumi3DShape:constructor()
end

-- WARNING: there might be some problem on metal backend, fix it after metal gets ready @zikuan
function Lumi3DShape:instantiateMaterial(material)
    local newPass = Amaz.Pass()
    newPass.shaders = material.xshader.passes:get(0).shaders

    local semantics = Amaz.Map()
    semantics:insert("a_texcoord0", Amaz.VertexAttribType.TEXCOORD0)
    semantics:insert("a_position", Amaz.VertexAttribType.POSITION)
    newPass.semantics = semantics

    local depthStencilState = Amaz.DepthStencilState()
    depthStencilState.depthTestEnable = true
    depthStencilState.depthWriteEnable = true

    local reasteriazationState = Amaz.RasterizationState()
    reasteriazationState.cullMode = 0

    local colorBlendAttachmentState = Amaz.ColorBlendAttachmentState()
    colorBlendAttachmentState.blendEnable = true
    colorBlendAttachmentState.srcColorBlendFactor = 6 -- SRC_ALPHA
    colorBlendAttachmentState.dstColorBlendFactor = 7 -- ONE_MINUS_SRC_ALPHA
    colorBlendAttachmentState.srcAlphaBlendFactor = 1 -- ONE
    colorBlendAttachmentState.dstAlphaBlendFactor = 1 -- ONE
    colorBlendAttachmentState.ColorBlendOp = 0 -- ADD
    colorBlendAttachmentState.AlphaBlendOp = 4 -- MAX
    local colorBlendState = Amaz.ColorBlendState()
    colorBlendState:pushAttachment(colorBlendAttachmentState)

    local renderState = Amaz.RenderState()
    renderState.depthstencil = depthStencilState
    renderState.rasterization = reasteriazationState
    renderState.colorBlend = colorBlendState

    newPass.renderState = renderState

    local newShader = Amaz.XShader()
    newShader.passes:pushBack(newPass)

    local mat = Amaz.Material()
    mat.xshader = newShader

    return mat
end

function Lumi3DShape:onStart(comp)
    self.materialTemplate = comp.entity.scene.assetMgr:SyncLoad("effects/Lumi3DShape/material/3Dshape.material")

    self.camera = comp.entity:searchEntity("BlitCamera"):getComponent("Camera")
    self.meshrenderer = comp.entity:searchEntity("BlitPass"):getComponent("MeshRenderer")
    self.meshTransform = comp.entity:searchEntity("BlitPass"):getComponent("Transform")
    self.material = self:instantiateMaterial(self.materialTemplate)
    self.meshrenderer.material = self.material

    self.translucencyEntity = comp.entity:searchEntity("BlitPass_2")
    self.meshrenderer2 = self.translucencyEntity:getComponent("MeshRenderer")
    self.meshTransform2 = self.translucencyEntity:getComponent("Transform")
    self.material2 = self:instantiateMaterial(self.materialTemplate)
    self.meshrenderer2.material = self.material2

    self.whiteTex = comp.entity.scene.assetMgr:SyncLoad("effects/Lumi3DShape/image/white.jpg")
end

function Lumi3DShape:updateMat(material)
    -- update cull mode
    if material.xshader then
        local passes = material.xshader.passes
        if self.cullBack or self.twoSide then
            passes:get(0).renderState.rasterization.cullMode = 2
        else
            passes:get(0).renderState.rasterization.cullMode = 0
        end
    end

    material:setTex("u_inputTexture", self.texture)
    if self.mask == nil or self.enableMask == false then
        material:setTex("u_mask", self.whiteTex)
    else
        material:setTex("u_mask", self.mask)
    end
    if self.maskChannel == "R" then
        material:setInt("u_maskChannel", 0)
    elseif self.maskChannel == "G" then
        material:setInt("u_maskChannel", 1)
    elseif self.maskChannel == "B" then
        material:setInt("u_maskChannel", 2)
    elseif self.maskChannel == "A" then
        material:setInt("u_maskChannel", 3)
    end

    local uvScaleX = 1.0
    local uvScaleY = 1.0
    local inputTexRatio = self.texture.height / self.texture.width
    local uvRatio = self.meshGenerator.uvRatio
    if self.texFillMode == "fill" then
        local scale = uvRatio / inputTexRatio
        if scale < 1 then
            uvScaleX = 1.0
            uvScaleY = scale
        else
            uvScaleX = 1.0 / scale
            uvScaleY = 1.0
        end
    elseif self.texFillMode == "fit" then
        local scale = uvRatio / inputTexRatio
        if scale > 1 then
            uvScaleX = 1.0
            uvScaleY = scale
        else
            uvScaleX = 1.0 / scale
            uvScaleY = 1.0
        end
    elseif self.texFillMode == "repeat&stretch" then
        uvScaleX = 1.0 / self.uvScaleX
        uvScaleY = 1.0 / self.uvScaleY
    elseif self.texFillMode == "repeat&fill" then
        uvScaleX = 1.0 / self.uvScaleX
        uvScaleY = uvScaleX / inputTexRatio
    else -- stretch
    end
    material:setVec2("u_uvScale", Amaz.Vector2f(uvScaleX, uvScaleY))
    if self.uvWrapMode == "clamp" then
        material:setInt("u_uvWrapMode", 0)
    elseif self.uvWrapMode == "repeat" then
        material:setInt("u_uvWrapMode", 1)
    elseif self.uvWrapMode == "mirror" then
        material:setInt("u_uvWrapMode", 2)
    elseif self.uvWrapMode == "black" then
        material:setInt("u_uvWrapMode", 3)
    elseif self.uvWrapMode == "white" then
        material:setInt("u_uvWrapMode", 4)
    elseif self.uvWrapMode == "translucent" then
        material:setInt("u_uvWrapMode", 5)
    end
end

function Lumi3DShape:rotateByAEAxis(eulerAngle)
    -- ae xyz, editor yxz
    local left = Amaz.Vector3f(1.0, 0.0, 0.0)
    local up = Amaz.Vector3f(0.0, 1.0, 0.0)
    local forward = Amaz.Vector3f(0.0, 0.0, 1.0)

    local xAngle = math.rad(eulerAngle.x)
    local yAngle = math.rad(eulerAngle.y)
    local zAngle = math.rad(eulerAngle.z)

    return Amaz.Quaternionf.axisAngleToQuaternion(left, xAngle) * 
            Amaz.Quaternionf.axisAngleToQuaternion(up, yAngle) * 
            Amaz.Quaternionf.axisAngleToQuaternion(forward, zAngle)
end
function Lumi3DShape:onUpdate(comp, deltaTime)
    if self.inputImage == nil then
        self.texture = self.InputTex
    else
        self.texture = self.inputImage
    end
    local fovy = self.fov
    local fovx = math.deg(math.atan(math.tan(math.rad(self.fov * 0.5)) * self.texture.height / self.texture.width) * 2)
    self.camera.fovy = math.min(fovx, fovy)

    if self.OutputTex then
        self.camera.inputTexture = nil
        self.camera.renderTexture = self.OutputTex
    end
    self.meshrenderer.mesh = self.meshGenerator:getMesh(self.meshType, Amaz.Vector3f(self.meshSize.x, self.meshSize.y, self.meshSize.z), 
        Amaz.Vector3f(math.floor(self.meshResX), math.floor(self.meshResY), math.floor(self.meshResZ)), self.reverseUV, self.twoSide)
    self.meshrenderer2.mesh = self.meshGenerator:getMesh(self.meshType, Amaz.Vector3f(self.meshSize.x, self.meshSize.y, self.meshSize.z), 
        Amaz.Vector3f(math.floor(self.meshResX), math.floor(self.meshResY), math.floor(self.meshResZ)), self.reverseUV, self.twoSide)
    self.meshTransform:setWorldPosition(self.position)
    self.meshTransform2:setWorldPosition(self.position)
    self.meshTransform:setWorldScale(self.scale)
    self.meshTransform2:setWorldScale(self.scale)
    local rotateQuat = self:rotateByAEAxis(self.rotate)
    self.meshTransform.localOrientation = rotateQuat
    self.meshTransform2.localOrientation = rotateQuat

    self.translucencyEntity.visible = self.translucency
    -- update depth test
    if self.material.xshader then
        local passes = self.material.xshader.passes
        if self.translucency then
            passes:get(0).renderState.depthstencil.depthTestEnable = true
            passes:get(0).renderState.depthstencil.depthWriteEnable = false
        else
            passes:get(0).renderState.depthstencil.depthTestEnable = true
            passes:get(0).renderState.depthstencil.depthWriteEnable = true
        end
    end

    self:updateMat(self.material)
    self:updateMat(self.material2)
end

function Lumi3DShape:setEffectAttr(key, value, comp)
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
        Position_x = {"position", "x"}, Position_y = {"position", "y"}, Position_z = {"position", "z"},
        Scale_x = {"scale", "x"}, Scale_y = {"scale", "y"}, Scale_z = {"scale", "z"},
        Rotate_x = {"rotate", "x"}, Rotate_y = {"rotate", "y"}, Rotate_z = {"rotate", "z"},
        meshSize_x = {"meshSize", "x"}, meshSize_y = {"meshSize", "y"}, meshSize_z = {"meshSize", "z"},
    }

    local meshType_params = {
        "quad",
        "ellipse", 
        "ring", 
        "cube", 
        "sphere", 
        "cylinder", 
        "donut"
    }
    local texFillMode_params = {
        "stretch", "fill", "fit", "repeat&stretch", "repeat&fill"
    }
    local uvWrapMode_params = {
        "clamp", "repeat", "mirror", "black", "white", "translucent"
    }
    local maskChannel_params = {
        "R", "G", "B", "A"
    }

    if vectorNf_params[key] then
        local paramKey = vectorNf_params[key][1]
        local channel = vectorNf_params[key][2]
        setParamVectorNf(paramKey, channel, value)
    elseif key == "mask" then
        self.mask = value
    elseif key == "inputImage" then
        self.inputImage = value
    elseif key == "meshType" then
        _setEffectAttr(key, meshType_params[value + 1])
    elseif key == "uvWrapMode" then
        _setEffectAttr(key, uvWrapMode_params[value + 1])
    elseif key == "maskChannel" then
        _setEffectAttr(key, maskChannel_params[value + 1])
    elseif key == "texFillMode" then
        _setEffectAttr(key, texFillMode_params[value + 1])
    else
        _setEffectAttr(key, value)
    end
end

exports.Lumi3DShape = Lumi3DShape
return exports
