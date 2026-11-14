local isEditor = not not (Amaz.Macros and Amaz.Macros.EditorSDK)
local exports = exports or {}

---@class LumiCube : ScriptComponent
---@field InputTex Texture
---@field OutputTex Texture
---@field AEDesignSize Vector2f

---@field fov double [UI(Range={0.0, 180.0}, Drag)]
---@field position Vector3f
---@field scale double [UI(Range={0, 10}, Drag)]
---@field rotateX double [UI(Range={-360, 360}, Drag)]
---@field rotateY double [UI(Range={-360, 360}, Drag)]
---@field rotateZ double [UI(Range={-360, 360}, Drag)]
---@field meshSize Vector3f
---@field meshRound double [UI(Range={0, 1}, Drag)]
---@field meshCount double [UI(Range={2, 20}, Drag)]

---@field imageFDefault Texture
---@field fillModeFDefault number [UI(Range={0, 2})]
---@field wrapModeFDefault number [UI(Range={0, 4})]
---@field uvCenterFDefault Vector2f
---@field uvScaleFDefault Vector2f
---@field uvRotateFDefault double [UI(Range={-360, 360}, Drag)]
---@field imageBDefault Texture
---@field fillModeBDefault number [UI(Range={0, 2})]
---@field wrapModeBDefault number [UI(Range={0, 4})]
---@field uvCenterBDefault Vector2f
---@field uvScaleBDefault Vector2f
---@field uvRotateBDefault double [UI(Range={-360, 360}, Drag)]

---@field translateFront Vector3f
---@field scaleFront Vector3f
---@field rotateFront Vector3f
---@field imageFFront Texture
---@field fillModeFFront number [UI(Range={0, 2})]
---@field wrapModeFFront number [UI(Range={0, 4})]
---@field uvCenterFFront Vector2f
---@field uvScaleFFront Vector2f
---@field uvRotateFFront double [UI(Range={-360, 360}, Drag)]
---@field imageBFront Texture
---@field fillModeBFront number [UI(Range={0, 2})]
---@field wrapModeBFront number [UI(Range={0, 4})]
---@field uvCenterBFront Vector2f
---@field uvScaleBFront Vector2f
---@field uvRotateBFront double [UI(Range={-360, 360}, Drag)]

---@field translateBack Vector3f
---@field scaleBack Vector3f
---@field rotateBack Vector3f
---@field imageFBack Texture
---@field fillModeFBack number [UI(Range={0, 2})]
---@field wrapModeFBack number [UI(Range={0, 4})]
---@field uvCenterFBack Vector2f
---@field uvScaleFBack Vector2f
---@field uvRotateFBack double [UI(Range={-360, 360}, Drag)]
---@field imageBBack Texture
---@field fillModeBBack number [UI(Range={0, 2})]
---@field wrapModeBBack number [UI(Range={0, 4})]
---@field uvCenterBBack Vector2f
---@field uvScaleBBack Vector2f
---@field uvRotateBBack double [UI(Range={-360, 360}, Drag)]

---@field translateTop Vector3f
---@field scaleTop Vector3f
---@field rotateTop Vector3f
---@field imageFTop Texture
---@field fillModeFTop number [UI(Range={0, 2})]
---@field wrapModeFTop number [UI(Range={0, 4})]
---@field uvCenterFTop Vector2f
---@field uvScaleFTop Vector2f
---@field uvRotateFTop double [UI(Range={-360, 360}, Drag)]
---@field imageBTop Texture
---@field fillModeBTop number [UI(Range={0, 2})]
---@field wrapModeBTop number [UI(Range={0, 4})]
---@field uvCenterBTop Vector2f
---@field uvScaleBTop Vector2f
---@field uvRotateBTop double [UI(Range={-360, 360}, Drag)]

---@field translateBottom Vector3f
---@field scaleBottom Vector3f
---@field rotateBottom Vector3f
---@field imageFBottom Texture
---@field fillModeFBottom number [UI(Range={0, 2})]
---@field wrapModeFBottom number [UI(Range={0, 4})]
---@field uvCenterFBottom Vector2f
---@field uvScaleFBottom Vector2f
---@field uvRotateFBottom double [UI(Range={-360, 360}, Drag)]
---@field imageBBottom Texture
---@field fillModeBBottom number [UI(Range={0, 2})]
---@field wrapModeBBottom number [UI(Range={0, 4})]
---@field uvCenterBBottom Vector2f
---@field uvScaleBBottom Vector2f
---@field uvRotateBBottom double [UI(Range={-360, 360}, Drag)]

---@field translateLeft Vector3f
---@field scaleLeft Vector3f
---@field rotateLeft Vector3f
---@field imageFLeft Texture
---@field fillModeFLeft number [UI(Range={0, 2})]
---@field wrapModeFLeft number [UI(Range={0, 4})]
---@field uvCenterFLeft Vector2f
---@field uvScaleFLeft Vector2f
---@field uvRotateFLeft double [UI(Range={-360, 360}, Drag)]
---@field imageBLeft Texture
---@field fillModeBLeft number [UI(Range={0, 2})]
---@field wrapModeBLeft number [UI(Range={0, 4})]
---@field uvCenterBLeft Vector2f
---@field uvScaleBLeft Vector2f
---@field uvRotateBLeft double [UI(Range={-360, 360}, Drag)]

---@field translateRight Vector3f
---@field scaleRight Vector3f
---@field rotateRight Vector3f
---@field imageFRight Texture
---@field fillModeFRight number [UI(Range={0, 2})]
---@field wrapModeFRight number [UI(Range={0, 4})]
---@field uvCenterFRight Vector2f
---@field uvScaleFRight Vector2f
---@field uvRotateFRight double [UI(Range={-360, 360}, Drag)]
---@field imageBRight Texture
---@field fillModeBRight number [UI(Range={0, 2})]
---@field wrapModeBRight number [UI(Range={0, 4})]
---@field uvCenterBRight Vector2f
---@field uvScaleBRight Vector2f
---@field uvRotateBRight double [UI(Range={-360, 360}, Drag)]

---@field twoSide Bool
---@field cullBack Bool
---@field translucency Bool
---@field mask Texture
---@field maskChannel number [UI(Range={0, 3})]
---@field separateSurface Bool
---@field multiRatio number [UI(Range={0, 1})]
local LumiCube = LumiCube or {}

LumiCube.__index = LumiCube
LumiCube.FillMode = {
    Fit = 0,
    Fill = 1,
    Stretch = 2
}
LumiCube.WrapMode = {
    Clamp = 0,
    Repeat = 1,
    Mirror = 2,
    Black = 3,
    White = 4
}
LumiCube.MaskChannel = {
    R = 0,
    G = 1,
    B = 2,
    A = 3
}
LumiCube.MultiRatio = {
    LongEdge = 0,
    ShortEdge = 1
}

LumiCube.Surfaces = {{
    name = "Front",
    sizeShuffle = function(x, y, z)
        return Amaz.Vector3f(x, y, z)
    end,
    preRotate = {}
}, {
    name = "Back",
    sizeShuffle = function(x, y, z)
        return Amaz.Vector3f(x, y, z)
    end,
    preRotate = {
        ry = -180
    }
}, {
    name = "Top",
    sizeShuffle = function(x, y, z)
        return Amaz.Vector3f(x, z, y)
    end,
    preRotate = {
        rx = -90
    }
}, {
    name = "Bottom",
    sizeShuffle = function(x, y, z)
        return Amaz.Vector3f(x, z, y)
    end,
    preRotate = {
        rx = 90
    }
}, {
    name = "Left",
    sizeShuffle = function(x, y, z)
        return Amaz.Vector3f(z, y, x)
    end,
    preRotate = {
        ry = 90
    }
}, {
    name = "Right",
    sizeShuffle = function(x, y, z)
        return Amaz.Vector3f(z, y, x)
    end,
    preRotate = {
        ry = -90
    }
}}

function LumiCube.new(construct, ...)
    local self = setmetatable({}, LumiCube)

    if construct and LumiCube.constructor then
        LumiCube.constructor(self, ...)
    end

    self.InputTex = nil
    self.OutputTex = nil
    self.AEDesignSize = Amaz.Vector2f(1000, 1000)

    -- global
    self.enableMask = false
    self.mask = nil
    self.maskChannel = 3
    self.cullBack = false
    self.translucency = false
    self.twoSide = true
    self.separateSurface = false
    self.multiRatio = LumiCube.MultiRatio.LongEdge

    -- 3d
    self.fov = 60
    self.position = Amaz.Vector3f(0.5, 0.5, 0)
    self.scale = Amaz.Vector3f(0.1, 0.9, 0.1)
    self.rotateX = 0
    self.rotateY = 0
    self.rotateZ = 0
    self.meshSize = Amaz.Vector3f(1.0, 0.0, 1.0)
    self.meshRound = 0
    self.meshCount = 2

    -- surface default
    for i = 0, #LumiCube.Surfaces do
        local option = LumiCube.Surfaces[i]
        local suffix = option and option.name or "Default"
        if option then
            self["translate" .. suffix] = Amaz.Vector3f(0, 1, 0)
            self["scale" .. suffix] = Amaz.Vector3f(0.1, 0.9, 0.1)
            self["rotate" .. suffix] = Amaz.Vector3f(0, 1, 0)
        end
        self["imageF" .. suffix] = nil
        self["fillModeF" .. suffix] = LumiCube.FillMode.Fit
        self["wrapModeF" .. suffix] = LumiCube.WrapMode.Mirror
        self["uvCenterF" .. suffix] = Amaz.Vector2f(0, 1)
        self["uvScaleF" .. suffix] = Amaz.Vector2f(0.1, 0.9)
        self["uvRotateF" .. suffix] = 0
        self["imageB" .. suffix] = nil
        self["fillModeB" .. suffix] = LumiCube.FillMode.Fit
        self["wrapModeB" .. suffix] = LumiCube.WrapMode.Mirror
        self["uvCenterB" .. suffix] = Amaz.Vector2f(0, 1)
        self["uvScaleB" .. suffix] = Amaz.Vector2f(0.1, 0.9)
        self["uvRotateB" .. suffix] = 0
    end
    return self
end

function LumiCube:constructor()
end

function LumiCube:onStart(comp)
    self.material0 = comp.entity.scene.assetMgr:SyncLoad("effects/LumiCube/material/Cube.material")

    self.camera = comp.entity:searchEntity("Camera"):getComponent("Camera")
    self.camera.zNear = 10
    self.camera.zFar = 100000
    self.cameraTransform = comp.entity:searchEntity("Camera"):getComponent("Transform")

    self.renderer1 = comp.entity:searchEntity("Renderer1"):getComponent("MeshRenderer")
    self.transform1 = comp.entity:searchEntity("Renderer1"):getComponent("Transform")
    self.material1 = self.instantiateMaterial(self.material0)
    self.renderer1.material = self.material1
    self.renderer1.useFrustumCulling = false

    self.renderer2 = comp.entity:searchEntity("Renderer2"):getComponent("MeshRenderer")
    self.transform2 = comp.entity:searchEntity("Renderer2"):getComponent("Transform")
    self.material2 = self.instantiateMaterial(self.material0)
    self.renderer2.material = self.material2
    self.renderer2.useFrustumCulling = false
end

function LumiCube:updateMaterial(comp, dt)
    if not self.InputTex or not self.OutputTex then
        return
    end

    self.meshDataComputed = false
    self.vtMatrixComputed = false
    self.uvMatrixComputed = false
    self.wrapModeComputed = false
    self.texturesComputed = false

    local ow = self.OutputTex.width
    local oh = self.OutputTex.height
    local designSize = self.AEDesignSize

    if self.multiRatio == LumiCube.MultiRatio.ShortEdge then
        self:setupBaseOnShort(ow, oh, designSize)
    else
        self:setupBaseOnLong(ow, oh, designSize)
    end

    local px = (self.position.x - 0.5) * designSize.x
    local py = (self.position.y - 0.5) * designSize.y
    local pz = (self.position.z) * designSize.y - (self.focalLength + self.benchmarks * 0.5)
    local position0 = Amaz.Vector3f(px, py, pz)
    self.transform1.localPosition = position0
    self.transform2.localPosition = position0
    local sx = self.scale.x * designSize.x * 0.01
    local sy = (1 - self.scale.y) * designSize.y * 0.01
    local sz = self.scale.z * designSize.y * 0.01
    local scale0 = Amaz.Vector3f(sx, sy, sz)
    self.transform1.localScale = scale0
    self.transform2.localScale = scale0
    local rotate0 = self.rotateByAEAxis(self.rotateX, self.rotateY, self.rotateZ)
    self.transform1.localOrientation = rotate0
    self.transform2.localOrientation = rotate0

    local halfSizeX = self.meshSize.x * designSize.x * 0.5
    local halfSizeY = (1 - self.meshSize.y) * designSize.y * 0.5
    local halfSizeZ = self.meshSize.z * designSize.y * 0.5

    if not self.meshDataComputed then
        local minHalfSize = math.min(halfSizeX, halfSizeY, halfSizeZ)
        local roundRadius = self.meshRound * minHalfSize
        local roundSteps = math.floor(self.meshCount)
        local vertices = Amaz.FloatVector()
        local indices = Amaz.UInt16Vector()
        local index = 0
        for i, opt in ipairs(LumiCube.Surfaces) do
            local id = i - 1
            local meshHalfSize = opt.sizeShuffle(halfSizeX, halfSizeY, halfSizeZ)
            local pos, uv = self.createMeshData(meshHalfSize, roundRadius, roundSteps)
            index = self.appendMeshData(vertices, indices, index, pos, uv, id, 0, false)
            if self.twoSide then
                index = self.appendMeshData(vertices, indices, index, pos, uv, id, 1, true)
            end
        end
        local mesh = self.createMesh(vertices, indices)
        self.renderer1.mesh = mesh
        self.renderer2.mesh = mesh
        self.meshDataComputed = true
    end

    if not self.vtMatrixComputed then
        local matrixList = Amaz.Vec4Vector()
        for id, opt in ipairs(LumiCube.Surfaces) do
            local size = opt.sizeShuffle(halfSizeX, halfSizeY, halfSizeZ)
            local translate = self["translate" .. opt.name]
            local scale = self["scale" .. opt.name]
            local rotate = self["rotate" .. opt.name]
            local matrix = self.createTransform({opt.preRotate, {
                z = size.z
            }, {
                x = translate.x * designSize.x,
                y = (translate.y - 1) * designSize.y,
                z = translate.z * designSize.y,
                sx = scale.x * designSize.x * 0.01,
                sy = (1 - scale.y) * designSize.y * 0.01,
                sz = scale.z * designSize.y * 0.01,
                rx = rotate.x * designSize.x,
                ry = (1 - rotate.y) * designSize.y,
                rz = rotate.z * designSize.y
            }})
            matrixList:pushBack(matrix:getColumn(0))
            matrixList:pushBack(matrix:getColumn(1))
            matrixList:pushBack(matrix:getColumn(2))
            matrixList:pushBack(matrix:getColumn(3))
        end
        self.material1:setVec4Vector("u_model", matrixList)
        self.material2:setVec4Vector("u_model", matrixList)
    end

    if not self.uvMatrixComputed then
        local uvScaleCList = Amaz.Vec4Vector()
        local uvRotateList = Amaz.FloatVector()
        for id, opt in ipairs(LumiCube.Surfaces) do
            local size = opt.sizeShuffle(halfSizeX, halfSizeY, halfSizeZ)
            local keyF = self:getSurfaceFKey(opt.name)
            local keyB = self:getSurfaceBKey(opt.name)
            local imageF = self["image" .. keyF] or self.OutputTex
            local imageB = self["image" .. keyB] or self.OutputTex
            local fillModeF = self["fillMode" .. keyF]
            local fillModeB = self["fillMode" .. keyB]
            local uvScaleFx = self["uvScale" .. keyF].x * designSize.x * 0.01
            local uvScaleFy = (1 - self["uvScale" .. keyF].y) * designSize.y * 0.01
            local uvScaleBx = self["uvScale" .. keyB].x * designSize.x * 0.01
            local uvScaleBy = (1 - self["uvScale" .. keyB].y) * designSize.y * 0.01
            local uvCenterFx = self["uvCenter" .. keyF].x * designSize.x * 0.01
            local uvCenterFy = (1 - self["uvCenter" .. keyF].y) * designSize.y * 0.01
            local uvCenterBx = self["uvCenter" .. keyB].x * designSize.x * 0.01
            local uvCenterBy = (1 - self["uvCenter" .. keyB].y) * designSize.y * 0.01
            local uvScaleF = self.solveScale(size.x, size.y, imageF.width, imageF.height, uvScaleFx, uvScaleFy,
                fillModeF)
            local uvScaleB = self.solveScale(size.x, size.y, imageB.width, imageB.height, uvScaleBx, uvScaleBy,
                fillModeB)
            uvScaleCList:pushBack(Amaz.Vector4f(1 / uvScaleF.x, 1 / uvScaleF.y, uvCenterFx, -uvCenterFy))
            uvScaleCList:pushBack(Amaz.Vector4f(1 / uvScaleB.x, 1 / uvScaleB.y, uvCenterBx, -uvCenterBy))
            local rotateF = math.rad(self["uvRotate" .. keyF])
            local rotateB = math.rad(self["uvRotate" .. keyB])
            uvRotateList:pushBack(rotateF)
            uvRotateList:pushBack(rotateB)
        end
        self.material1:setVec4Vector("u_uvScaleC", uvScaleCList)
        self.material2:setVec4Vector("u_uvScaleC", uvScaleCList)
        self.material1:setFloatVector("u_uvRotate", uvRotateList)
        self.material2:setFloatVector("u_uvRotate", uvRotateList)
        self.uvMatrixComputed = true
    end

    if not self.wrapModeComputed then
        local wrapModeList = Amaz.FloatVector()
        for id, opt in ipairs(LumiCube.Surfaces) do
            local keyF = self:getSurfaceFKey(opt.name)
            local keyB = self:getSurfaceBKey(opt.name)
            wrapModeList:pushBack(self["wrapMode" .. keyF])
            wrapModeList:pushBack(self["wrapMode" .. keyB])
        end
        self.material1:setFloatVector("u_wrapMode", wrapModeList)
        self.material2:setFloatVector("u_wrapMode", wrapModeList)
        self.wrapModeComputed = true
    end

    if not self.texturesComputed then
        for id, opt in ipairs(LumiCube.Surfaces) do
            local uniformF = "u_imageF" .. opt.name
            local uniformB = "u_imageB" .. opt.name
            local keyF = self:getSurfaceFKey(opt.name)
            local keyB = self:getSurfaceBKey(opt.name)
            local imageF = self["image" .. keyF] or self.InputTex
            local imageB = self["image" .. keyB] or self.InputTex
            self.material1:setTex(uniformF, imageF)
            self.material1:setTex(uniformB, imageB)
            self.material2:setTex(uniformF, imageF)
            self.material2:setTex(uniformB, imageB)
        end
        self.camera.renderTexture = self.OutputTex
        self.texturesComputed = true
    end

    -- update depth test
    if self.material1.xshader then
        local passes = self.material1.xshader.passes
        if self.translucency then
            self.renderer2.entity.visible = true
            passes:get(0).renderState.depthstencil.depthTestEnable = true
            passes:get(0).renderState.depthstencil.depthWriteEnable = false
        else
            self.renderer2.entity.visible = false
            passes:get(0).renderState.depthstencil.depthTestEnable = true
            passes:get(0).renderState.depthstencil.depthWriteEnable = true
        end
    end

    self:updateMat(self.material1)
    self:updateMat(self.material2)
end

function LumiCube:setEffectAttr(key, value, comp)
    local setter = LumiCube.Setters[key]
    if setter then
        setter(self, comp, key, value)
    else
        self[key] = value
        comp.properties:set(key, value)
    end
end

function LumiCube:setupBaseOnLong(ow, oh, designSize)
    if not self.focalLength then
        if designSize.x < designSize.y then
            self.benchmarks = designSize.y
            self.focalLength = designSize.y * 0.5 / math.tan(math.rad(self.fov * 0.5))
        else
            self.benchmarks = designSize.x
            self.focalLength = designSize.x * 0.5 / math.tan(math.rad(self.fov * 0.5))
        end
    end
    if ow ~= self.ow or oh ~= self.oh then
        self.uvMatrixComputed = false
        self.ow = ow
        self.oh = oh
        if ow < oh then
            self.screenScale = self.benchmarks / oh
            self.camera.fovy = self.fov
        else
            self.screenScale = self.benchmarks / ow
            self.camera.fovy = math.deg(math.atan(oh * self.screenScale * 0.5 / self.focalLength) * 2)
        end
    end
end

function LumiCube:setupBaseOnShort(ow, oh, designSize)
    if not self.focalLength then
        if designSize.x < designSize.y then
            self.benchmarks = designSize.x
            self.focalLength = designSize.x * 0.5 / math.tan(math.rad(self.fov * 0.5))
        else
            self.benchmarks = designSize.y
            self.focalLength = designSize.y * 0.5 / math.tan(math.rad(self.fov * 0.5))
        end
    end
    if ow ~= self.ow or oh ~= self.oh then
        self.uvMatrixComputed = false
        self.ow = ow
        self.oh = oh
        if ow < oh then
            self.screenScale = self.benchmarks / ow
            self.camera.fovy = math.deg(math.atan(oh * self.screenScale * 0.5 / self.focalLength) * 2)
        else
            self.screenScale = self.benchmarks / oh
            self.camera.fovy = self.fov
        end
    end
end

function LumiCube:getSurfaceFKey(suffix)
    if self.separateSurface then
        if self["imageF" .. suffix] then
            return "F" .. suffix
        end
    end
    return "FDefault"
end

function LumiCube:getSurfaceBKey(suffix)
    if self.separateSurface then
        if self["imageB" .. suffix] then
            return "B" .. suffix
        elseif self.imageBDefault then
            return "BDefault"
        elseif self["imageF" .. suffix] then
            return "F" .. suffix
        else
            return "FDefault"
        end
    else
        if self.imageBDefault then
            return "BDefault"
        else
            return "FDefault"
        end
    end
end

function LumiCube:updateMat(material)
    -- update cull mode
    if material.xshader then
        local passes = material.xshader.passes
        if self.cullBack or self.twoSide then
            passes:get(0).renderState.rasterization.cullMode = 2
        else
            passes:get(0).renderState.rasterization.cullMode = 0
        end
    end

    if self.mask == nil then
        material:setInt("u_maskChannel", 100)
    else
        material:setTex("u_mask", self.mask)
        material:setInt("u_maskChannel", self.maskChannel)
    end
end

function LumiCube.instantiateMaterial(material)
    local newPass = Amaz.Pass()
    newPass.shaders = material.xshader.passes:get(0).shaders

    local semantics = Amaz.Map()
    semantics:insert("a_position", Amaz.VertexAttribType.POSITION)
    semantics:insert("a_texcoord0", Amaz.VertexAttribType.TEXCOORD0)
    semantics:insert("a_texcoord1", Amaz.VertexAttribType.TEXCOORD1)
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

function LumiCube.createMeshData(H, R, N)
    local pos = Amaz.Vec3Vector()
    local uv = Amaz.Vec2Vector()

    local L_arc = 2 * math.pi * R / 8
    local L_str = H - Amaz.Vector3f(R, R, R)
    local L_all = Amaz.Vector3f(L_arc, L_arc, L_arc) + L_str
    local P_arc = Amaz.Vector3f(L_arc / L_all.x, L_arc / L_all.y, L_arc / L_all.z)
    local P_str = Amaz.Vector3f(L_str.x / L_all.x, L_str.y / L_all.y, L_str.z / L_all.z)
    local C = 0.5
    local I0 = 0
    local s0, s1, c0, c1
    local i0, i1, j0, j1
    local CP

    -- flat
    pos:pushBack(Amaz.Vector3f(-L_str.x, -L_str.y, 0))
    pos:pushBack(Amaz.Vector3f(L_str.x, -L_str.y, 0))
    pos:pushBack(Amaz.Vector3f(L_str.x, L_str.y, 0))
    pos:pushBack(Amaz.Vector3f(-L_str.x, L_str.y, 0))
    uv:pushBack(Amaz.Vector2f(C - C * P_str.x, C - C * P_str.y))
    uv:pushBack(Amaz.Vector2f(C + C * P_str.x, C - C * P_str.y))
    uv:pushBack(Amaz.Vector2f(C + C * P_str.x, C + C * P_str.y))
    uv:pushBack(Amaz.Vector2f(C - C * P_str.x, C + C * P_str.y))

    if R > 0 then
        -- edge.up
        s0, c0 = 0, R
        for i = 0, N - 1 do
            I0 = I0 + 4
            local w = math.rad(45 * (i + 1) / N)
            s1, c1 = math.sin(w) * R, math.cos(w) * R
            pos:pushBack(Amaz.Vector3f(-L_str.x, L_str.y + s0, L_str.z + c0 - H.z))
            pos:pushBack(Amaz.Vector3f(L_str.x, L_str.y + s0, L_str.z + c0 - H.z))
            pos:pushBack(Amaz.Vector3f(L_str.x, L_str.y + s1, L_str.z + c1 - H.z))
            pos:pushBack(Amaz.Vector3f(-L_str.x, L_str.y + s1, L_str.z + c1 - H.z))
            uv:pushBack(Amaz.Vector2f(C - C * P_str.x, C + C * (P_str.y + P_arc.y * (i + 0) / N)))
            uv:pushBack(Amaz.Vector2f(C + C * P_str.x, C + C * (P_str.y + P_arc.y * (i + 0) / N)))
            uv:pushBack(Amaz.Vector2f(C + C * P_str.x, C + C * (P_str.y + P_arc.y * (i + 1) / N)))
            uv:pushBack(Amaz.Vector2f(C - C * P_str.x, C + C * (P_str.y + P_arc.y * (i + 1) / N)))
            s0, c0 = s1, c1
        end

        -- edge.down
        s0, c0 = 0, R
        for i = 0, N - 1 do
            I0 = I0 + 4
            local w = math.rad(45 * (i + 1) / N)
            s1, c1 = math.sin(w) * R, math.cos(w) * R
            pos:pushBack(Amaz.Vector3f(-L_str.x, -L_str.y - s1, L_str.z + c1 - H.z))
            pos:pushBack(Amaz.Vector3f(L_str.x, -L_str.y - s1, L_str.z + c1 - H.z))
            pos:pushBack(Amaz.Vector3f(L_str.x, -L_str.y - s0, L_str.z + c0 - H.z))
            pos:pushBack(Amaz.Vector3f(-L_str.x, -L_str.y - s0, L_str.z + c0 - H.z))
            uv:pushBack(Amaz.Vector2f(C - C * P_str.x, C - C * (P_str.y + P_arc.y * (i + 1) / N)))
            uv:pushBack(Amaz.Vector2f(C + C * P_str.x, C - C * (P_str.y + P_arc.y * (i + 1) / N)))
            uv:pushBack(Amaz.Vector2f(C + C * P_str.x, C - C * (P_str.y + P_arc.y * (i + 0) / N)))
            uv:pushBack(Amaz.Vector2f(C - C * P_str.x, C - C * (P_str.y + P_arc.y * (i + 0) / N)))
            s0, c0 = s1, c1
        end

        -- edge.left
        s0, c0 = 0, R
        for i = 0, N - 1 do
            I0 = I0 + 4
            local w = math.rad(45 * (i + 1) / N)
            s1, c1 = math.sin(w) * R, math.cos(w) * R
            pos:pushBack(Amaz.Vector3f(-L_str.x - s1, -L_str.y, L_str.z + c1 - H.z))
            pos:pushBack(Amaz.Vector3f(-L_str.x - s0, -L_str.y, L_str.z + c0 - H.z))
            pos:pushBack(Amaz.Vector3f(-L_str.x - s0, L_str.y, L_str.z + c0 - H.z))
            pos:pushBack(Amaz.Vector3f(-L_str.x - s1, L_str.y, L_str.z + c1 - H.z))
            uv:pushBack(Amaz.Vector2f(C - C * (P_str.x + P_arc.x * (i + 1) / N), C - C * P_str.y))
            uv:pushBack(Amaz.Vector2f(C - C * (P_str.x + P_arc.x * (i + 0) / N), C - C * P_str.y))
            uv:pushBack(Amaz.Vector2f(C - C * (P_str.x + P_arc.x * (i + 0) / N), C + C * P_str.y))
            uv:pushBack(Amaz.Vector2f(C - C * (P_str.x + P_arc.x * (i + 1) / N), C + C * P_str.y))
            s0, c0 = s1, c1
        end

        -- edge.right
        s0, c0 = 0, R
        for i = 0, N - 1 do
            I0 = I0 + 4
            local w = math.rad(45 * (i + 1) / N)
            s1, c1 = math.sin(w) * R, math.cos(w) * R
            pos:pushBack(Amaz.Vector3f(L_str.x + s0, -L_str.y, L_str.z + c0 - H.z))
            pos:pushBack(Amaz.Vector3f(L_str.x + s1, -L_str.y, L_str.z + c1 - H.z))
            pos:pushBack(Amaz.Vector3f(L_str.x + s1, L_str.y, L_str.z + c1 - H.z))
            pos:pushBack(Amaz.Vector3f(L_str.x + s0, L_str.y, L_str.z + c0 - H.z))
            uv:pushBack(Amaz.Vector2f(C + C * (P_str.x + P_arc.x * (i + 0) / N), C - C * P_str.y))
            uv:pushBack(Amaz.Vector2f(C + C * (P_str.x + P_arc.x * (i + 1) / N), C - C * P_str.y))
            uv:pushBack(Amaz.Vector2f(C + C * (P_str.x + P_arc.x * (i + 1) / N), C + C * P_str.y))
            uv:pushBack(Amaz.Vector2f(C + C * (P_str.x + P_arc.x * (i + 0) / N), C + C * P_str.y))
            s0, c0 = s1, c1
        end

        -- corner.left-up
        CP = Amaz.Vector3f(-L_str.x, L_str.y, L_str.z)
        i0 = Amaz.Vector3f(1, 0, 0)
        for i = 0, N - 1 do
            local wi = math.rad(45 * (i + 1) / N)
            local qi = Amaz.Quaternionf.axisAngleToQuaternion(Amaz.Vector3f(0, 1, 0), -wi)
            i1 = Amaz.Quaternionf.rotateVectorByQuat(qi, Amaz.Vector3f(1, 0, 0))

            j0 = Amaz.Vector3f(0, 1, 0)
            for j = 0, N - 1 do
                I0 = I0 + 4
                local wj = math.rad(45 * (j + 1) / N)
                local qj = Amaz.Quaternionf.axisAngleToQuaternion(Amaz.Vector3f(1, 0, 0), -wj)
                j1 = Amaz.Quaternionf.rotateVectorByQuat(qj, Amaz.Vector3f(0, 1, 0))

                local p0 = Amaz.Vector3f.normalize(Amaz.Vector3f.cross(i1, j0)) * R
                local p1 = Amaz.Vector3f.normalize(Amaz.Vector3f.cross(i0, j0)) * R
                local p2 = Amaz.Vector3f.normalize(Amaz.Vector3f.cross(i0, j1)) * R
                local p3 = Amaz.Vector3f.normalize(Amaz.Vector3f.cross(i1, j1)) * R
                pos:pushBack(Amaz.Vector3f(CP.x + p0.x, CP.y + p0.y, CP.z + p0.z - H.z))
                pos:pushBack(Amaz.Vector3f(CP.x + p1.x, CP.y + p1.y, CP.z + p1.z - H.z))
                pos:pushBack(Amaz.Vector3f(CP.x + p2.x, CP.y + p2.y, CP.z + p2.z - H.z))
                pos:pushBack(Amaz.Vector3f(CP.x + p3.x, CP.y + p3.y, CP.z + p3.z - H.z))
                uv:pushBack(Amaz.Vector2f(C - C * (P_str.x + P_arc.x * (i + 1) / N),
                    C + C * (P_str.y + P_arc.y * (j + 0) / N)))
                uv:pushBack(Amaz.Vector2f(C - C * (P_str.x + P_arc.x * (i + 0) / N),
                    C + C * (P_str.y + P_arc.y * (j + 0) / N)))
                uv:pushBack(Amaz.Vector2f(C - C * (P_str.x + P_arc.x * (i + 0) / N),
                    C + C * (P_str.y + P_arc.y * (j + 1) / N)))
                uv:pushBack(Amaz.Vector2f(C - C * (P_str.x + P_arc.x * (i + 1) / N),
                    C + C * (P_str.y + P_arc.y * (j + 1) / N)))
                j0 = j1
            end
            i0 = i1
        end

        -- corner.right-up
        CP = Amaz.Vector3f(L_str.x, L_str.y, L_str.z)
        i0 = Amaz.Vector3f(1, 0, 0)
        for i = 0, N - 1 do
            local wi = math.rad(45 * (i + 1) / N)
            local qi = Amaz.Quaternionf.axisAngleToQuaternion(Amaz.Vector3f(0, 1, 0), wi)
            i1 = Amaz.Quaternionf.rotateVectorByQuat(qi, Amaz.Vector3f(1, 0, 0))

            j0 = Amaz.Vector3f(0, 1, 0)
            for j = 0, N - 1 do
                I0 = I0 + 4
                local wj = math.rad(45 * (j + 1) / N)
                local qj = Amaz.Quaternionf.axisAngleToQuaternion(Amaz.Vector3f(1, 0, 0), -wj)
                j1 = Amaz.Quaternionf.rotateVectorByQuat(qj, Amaz.Vector3f(0, 1, 0))

                local p0 = Amaz.Vector3f.normalize(Amaz.Vector3f.cross(i0, j0)) * R
                local p1 = Amaz.Vector3f.normalize(Amaz.Vector3f.cross(i1, j0)) * R
                local p2 = Amaz.Vector3f.normalize(Amaz.Vector3f.cross(i1, j1)) * R
                local p3 = Amaz.Vector3f.normalize(Amaz.Vector3f.cross(i0, j1)) * R
                pos:pushBack(Amaz.Vector3f(CP.x + p0.x, CP.y + p0.y, CP.z + p0.z - H.z))
                pos:pushBack(Amaz.Vector3f(CP.x + p1.x, CP.y + p1.y, CP.z + p1.z - H.z))
                pos:pushBack(Amaz.Vector3f(CP.x + p2.x, CP.y + p2.y, CP.z + p2.z - H.z))
                pos:pushBack(Amaz.Vector3f(CP.x + p3.x, CP.y + p3.y, CP.z + p3.z - H.z))
                uv:pushBack(Amaz.Vector2f(C + C * (P_str.x + P_arc.x * (i + 0) / N),
                    C + C * (P_str.y + P_arc.y * (j + 0) / N)))
                uv:pushBack(Amaz.Vector2f(C + C * (P_str.x + P_arc.x * (i + 1) / N),
                    C + C * (P_str.y + P_arc.y * (j + 0) / N)))
                uv:pushBack(Amaz.Vector2f(C + C * (P_str.x + P_arc.x * (i + 1) / N),
                    C + C * (P_str.y + P_arc.y * (j + 1) / N)))
                uv:pushBack(Amaz.Vector2f(C + C * (P_str.x + P_arc.x * (i + 0) / N),
                    C + C * (P_str.y + P_arc.y * (j + 1) / N)))
                j0 = j1
            end
            i0 = i1
        end

        -- corner.left-down
        CP = Amaz.Vector3f(-L_str.x, -L_str.y, L_str.z)
        i0 = Amaz.Vector3f(1, 0, 0)
        for i = 0, N - 1 do
            local wi = math.rad(45 * (i + 1) / N)
            local qi = Amaz.Quaternionf.axisAngleToQuaternion(Amaz.Vector3f(0, 1, 0), -wi)
            i1 = Amaz.Quaternionf.rotateVectorByQuat(qi, Amaz.Vector3f(1, 0, 0))

            j0 = Amaz.Vector3f(0, 1, 0)
            for j = 0, N - 1 do
                I0 = I0 + 4
                local wj = math.rad(45 * (j + 1) / N)
                local qj = Amaz.Quaternionf.axisAngleToQuaternion(Amaz.Vector3f(1, 0, 0), wj)
                j1 = Amaz.Quaternionf.rotateVectorByQuat(qj, Amaz.Vector3f(0, 1, 0))

                local p0 = Amaz.Vector3f.normalize(Amaz.Vector3f.cross(i1, j1)) * R
                local p1 = Amaz.Vector3f.normalize(Amaz.Vector3f.cross(i0, j1)) * R
                local p2 = Amaz.Vector3f.normalize(Amaz.Vector3f.cross(i0, j0)) * R
                local p3 = Amaz.Vector3f.normalize(Amaz.Vector3f.cross(i1, j0)) * R
                pos:pushBack(Amaz.Vector3f(CP.x + p0.x, CP.y + p0.y, CP.z + p0.z - H.z))
                pos:pushBack(Amaz.Vector3f(CP.x + p1.x, CP.y + p1.y, CP.z + p1.z - H.z))
                pos:pushBack(Amaz.Vector3f(CP.x + p2.x, CP.y + p2.y, CP.z + p2.z - H.z))
                pos:pushBack(Amaz.Vector3f(CP.x + p3.x, CP.y + p3.y, CP.z + p3.z - H.z))
                uv:pushBack(Amaz.Vector2f(C - C * (P_str.x + P_arc.x * (i + 1) / N),
                    C - C * (P_str.y + P_arc.y * (j + 1) / N)))
                uv:pushBack(Amaz.Vector2f(C - C * (P_str.x + P_arc.x * (i + 0) / N),
                    C - C * (P_str.y + P_arc.y * (j + 1) / N)))
                uv:pushBack(Amaz.Vector2f(C - C * (P_str.x + P_arc.x * (i + 0) / N),
                    C - C * (P_str.y + P_arc.y * (j + 0) / N)))
                uv:pushBack(Amaz.Vector2f(C - C * (P_str.x + P_arc.x * (i + 1) / N),
                    C - C * (P_str.y + P_arc.y * (j + 0) / N)))
                j0 = j1
            end
            i0 = i1
        end

        -- corner.right-down
        CP = Amaz.Vector3f(L_str.x, -L_str.y, L_str.z)
        i0 = Amaz.Vector3f(1, 0, 0)
        for i = 0, N - 1 do
            local wi = math.rad(45 * (i + 1) / N)
            local qi = Amaz.Quaternionf.axisAngleToQuaternion(Amaz.Vector3f(0, 1, 0), wi)
            i1 = Amaz.Quaternionf.rotateVectorByQuat(qi, Amaz.Vector3f(1, 0, 0))

            j0 = Amaz.Vector3f(0, 1, 0)
            for j = 0, N - 1 do
                I0 = I0 + 4
                local wj = math.rad(45 * (j + 1) / N)
                local qj = Amaz.Quaternionf.axisAngleToQuaternion(Amaz.Vector3f(1, 0, 0), wj)
                j1 = Amaz.Quaternionf.rotateVectorByQuat(qj, Amaz.Vector3f(0, 1, 0))

                local p0 = Amaz.Vector3f.normalize(Amaz.Vector3f.cross(i0, j1)) * R
                local p1 = Amaz.Vector3f.normalize(Amaz.Vector3f.cross(i1, j1)) * R
                local p2 = Amaz.Vector3f.normalize(Amaz.Vector3f.cross(i1, j0)) * R
                local p3 = Amaz.Vector3f.normalize(Amaz.Vector3f.cross(i0, j0)) * R
                pos:pushBack(Amaz.Vector3f(CP.x + p0.x, CP.y + p0.y, CP.z + p0.z - H.z))
                pos:pushBack(Amaz.Vector3f(CP.x + p1.x, CP.y + p1.y, CP.z + p1.z - H.z))
                pos:pushBack(Amaz.Vector3f(CP.x + p2.x, CP.y + p2.y, CP.z + p2.z - H.z))
                pos:pushBack(Amaz.Vector3f(CP.x + p3.x, CP.y + p3.y, CP.z + p3.z - H.z))
                uv:pushBack(Amaz.Vector2f(C + C * (P_str.x + P_arc.x * (i + 0) / N),
                    C - C * (P_str.y + P_arc.y * (j + 1) / N)))
                uv:pushBack(Amaz.Vector2f(C + C * (P_str.x + P_arc.x * (i + 1) / N),
                    C - C * (P_str.y + P_arc.y * (j + 1) / N)))
                uv:pushBack(Amaz.Vector2f(C + C * (P_str.x + P_arc.x * (i + 1) / N),
                    C - C * (P_str.y + P_arc.y * (j + 0) / N)))
                uv:pushBack(Amaz.Vector2f(C + C * (P_str.x + P_arc.x * (i + 0) / N),
                    C - C * (P_str.y + P_arc.y * (j + 0) / N)))
                j0 = j1
            end
            i0 = i1
        end
    end
    return pos, uv
end

function LumiCube.solveScale(ow, oh, iw, ih, sx, sy, mode)
    local oa = ow / oh
    local ia = iw / ih
    if mode == LumiCube.FillMode.Fit then
        if ia > oa then
            return Amaz.Vector2f(sx, sy * oa / ia)
        else
            return Amaz.Vector2f(sx * ia / oa, sy)
        end
    elseif mode == LumiCube.FillMode.Fill then
        if ia > oa then
            return Amaz.Vector2f(sx * ia / oa, sy)
        else
            return Amaz.Vector2f(sx, sy * oa / ia)
        end
    else
        return Amaz.Vector2f(sx, sy)
    end
end

function LumiCube.createMesh(vertices, indices)
    local pos = Amaz.VertexAttribDesc()
    pos.semantic = Amaz.VertexAttribType.POSITION
    local uv0 = Amaz.VertexAttribDesc()
    uv0.semantic = Amaz.VertexAttribType.TEXCOORD0
    local uv1 = Amaz.VertexAttribDesc()
    uv1.semantic = Amaz.VertexAttribType.TEXCOORD1
    local desc = Amaz.Vector()
    desc:pushBack(pos)
    desc:pushBack(uv0)
    desc:pushBack(uv1)

    local mesh = Amaz.Mesh()
    mesh.vertexAttribs = desc
    mesh.clearAfterUpload = true
    mesh.vertices = vertices

    local subMesh = Amaz.SubMesh()
    subMesh.primitive = Amaz.Primitive.TRIANGLES
    subMesh.indices16 = indices
    subMesh.mesh = mesh
    mesh:addSubMesh(subMesh)
    return mesh
end

function LumiCube.appendMeshData(vertices, indices, index0, pos, uv, id0, id1, back)
    local quadCount = pos:size() / 4
    for i4 = 0, quadCount - 1 do
        local i = i4 * 4
        local p, c
        p = pos:get(i + 0)
        c = uv:get(i + 0)
        vertices:pushBack(p.x);
        vertices:pushBack(p.y);
        vertices:pushBack(p.z)
        vertices:pushBack(back and 1 - c.x or c.x);
        vertices:pushBack(c.y);
        vertices:pushBack(id0);
        vertices:pushBack(id1);

        p = pos:get(i + 1)
        c = uv:get(i + 1)
        vertices:pushBack(p.x);
        vertices:pushBack(p.y);
        vertices:pushBack(p.z)
        vertices:pushBack(back and 1 - c.x or c.x);
        vertices:pushBack(c.y);
        vertices:pushBack(id0);
        vertices:pushBack(id1);

        p = pos:get(i + 2)
        c = uv:get(i + 2)
        vertices:pushBack(p.x);
        vertices:pushBack(p.y);
        vertices:pushBack(p.z)
        vertices:pushBack(back and 1 - c.x or c.x);
        vertices:pushBack(c.y);
        vertices:pushBack(id0);
        vertices:pushBack(id1);

        p = pos:get(i + 3)
        c = uv:get(i + 3)
        vertices:pushBack(p.x);
        vertices:pushBack(p.y);
        vertices:pushBack(p.z)
        vertices:pushBack(back and 1 - c.x or c.x);
        vertices:pushBack(c.y);
        vertices:pushBack(id0);
        vertices:pushBack(id1);

        if back then
            indices:pushBack(index0 + 0);
            indices:pushBack(index0 + 2);
            indices:pushBack(index0 + 1);
            indices:pushBack(index0 + 0);
            indices:pushBack(index0 + 3);
            indices:pushBack(index0 + 2);
        else
            indices:pushBack(index0 + 0);
            indices:pushBack(index0 + 1);
            indices:pushBack(index0 + 2);
            indices:pushBack(index0 + 0);
            indices:pushBack(index0 + 2);
            indices:pushBack(index0 + 3);
        end
        index0 = index0 + 4
    end
    return index0
end

function LumiCube.rotateByAEAxis(x, y, z)
    local rotateX = Amaz.Quaternionf.eulerToQuaternion(Amaz.Vector3f(math.rad(x), 0, 0))
    local rotateY = Amaz.Quaternionf.eulerToQuaternion(Amaz.Vector3f(0, math.rad(-y), 0))
    local rotateZ = Amaz.Quaternionf.eulerToQuaternion(Amaz.Vector3f(0, 0, math.rad(-z)))
    return rotateX * rotateY * rotateZ
end

function LumiCube.createTransform(layers)
    local matrix = Amaz.Matrix4x4f()
    local rotate = Amaz.Matrix4x4f()
    local zero3 = Amaz.Vector3f(0, 0, 0)
    matrix:setIdentity()
    for i, layer in ipairs(layers) do
        local tx = layer.x or 0
        local ty = layer.y or 0
        local tz = layer.z or 0
        matrix:translate(Amaz.Vector3f(tx, ty, tz))

        local Q = Amaz.Quaternionf.identity()
        if layer.rx and layer.rx ~= 0 then
            Q = Q * Amaz.Quaternionf.eulerToQuaternion(Amaz.Vector3f(math.rad(layer.rx), 0, 0))
        end
        if layer.ry and layer.ry ~= 0 then
            Q = Q * Amaz.Quaternionf.eulerToQuaternion(Amaz.Vector3f(0, -math.rad(layer.ry), 0))
        end
        if layer.rz and layer.rz ~= 0 then
            Q = Q * Amaz.Quaternionf.eulerToQuaternion(Amaz.Vector3f(0, 0, -math.rad(layer.rz)))
        end
        rotate:setTR(zero3, Q)
        matrix = matrix * rotate

        local sx = layer.sx or 1
        local sy = layer.sy or 1
        local sz = layer.sz or 1
        matrix:scale(Amaz.Vector3f(sx, sy, sz))
    end
    return matrix
end

function LumiCube:setMeshData(comp, key, value)
    self.meshDataComputed = false
    self[key] = value
    comp.properties:set(key, value)
end

function LumiCube:setVTMatrix(comp, key, value)
    self.vtMatrixComputed = false
    self[key] = value
    comp.properties:set(key, value)
end

function LumiCube:setUVMatrix(comp, key, value)
    self.uvMatrixComputed = false
    self[key] = value
    comp.properties:set(key, value)
end

function LumiCube:setWrapMode(comp, key, value)
    self.wrapModeComputed = false
    self[key] = value
    comp.properties:set(key, value)
end

function LumiCube:setTextures(comp, key, value)
    self.uvMatrixComputed = false
    self.texturesComputed = false
    self[key] = value
    comp.properties:set(key, value)
end

function LumiCube:reset(comp, key, value)
    self.focalLength = nil
    self.ow = nil
    self.oh = nil
    self.meshDataComputed = false
    self.vtMatrixComputed = false
    self.uvMatrixComputed = false
    self.wrapModeComputed = false
    self.texturesComputed = false
    self[key] = value
    comp.properties:set(key, value)
end

LumiCube.Setters = {
    meshSize = LumiCube.setMeshData,
    meshRound = LumiCube.setMeshData,
    meshCount = LumiCube.setMeshData,
    twoSide = LumiCube.setMeshData,

    translateFront = LumiCube.setVTMatrix,
    translateBack = LumiCube.setVTMatrix,
    translateTop = LumiCube.setVTMatrix,
    translateBottom = LumiCube.setVTMatrix,
    translateLeft = LumiCube.setVTMatrix,
    translateRight = LumiCube.setVTMatrix,

    scaleFront = LumiCube.setVTMatrix,
    scaleBack = LumiCube.setVTMatrix,
    scaleTop = LumiCube.setVTMatrix,
    scaleBottom = LumiCube.setVTMatrix,
    scaleLeft = LumiCube.setVTMatrix,
    scaleRight = LumiCube.setVTMatrix,

    rotateFront = LumiCube.setVTMatrix,
    rotateBack = LumiCube.setVTMatrix,
    rotateTop = LumiCube.setVTMatrix,
    rotateBottom = LumiCube.setVTMatrix,
    rotateLeft = LumiCube.setVTMatrix,
    rotateRight = LumiCube.setVTMatrix,

    uvCenterFFront = LumiCube.setUVMatrix,
    uvCenterBFront = LumiCube.setUVMatrix,
    uvCenterFBack = LumiCube.setUVMatrix,
    uvCenterBBack = LumiCube.setUVMatrix,
    uvCenterFTop = LumiCube.setUVMatrix,
    uvCenterBTop = LumiCube.setUVMatrix,
    uvCenterFBottom = LumiCube.setUVMatrix,
    uvCenterBBottom = LumiCube.setUVMatrix,
    uvCenterFLeft = LumiCube.setUVMatrix,
    uvCenterBLeft = LumiCube.setUVMatrix,
    uvCenterFRight = LumiCube.setUVMatrix,
    uvCenterBRight = LumiCube.setUVMatrix,

    uvScaleFFront = LumiCube.setUVMatrix,
    uvScaleBFront = LumiCube.setUVMatrix,
    uvScaleFBack = LumiCube.setUVMatrix,
    uvScaleBBack = LumiCube.setUVMatrix,
    uvScaleFTop = LumiCube.setUVMatrix,
    uvScaleBTop = LumiCube.setUVMatrix,
    uvScaleFBottom = LumiCube.setUVMatrix,
    uvScaleBBottom = LumiCube.setUVMatrix,
    uvScaleFLeft = LumiCube.setUVMatrix,
    uvScaleBLeft = LumiCube.setUVMatrix,
    uvScaleFRight = LumiCube.setUVMatrix,
    uvScaleBRight = LumiCube.setUVMatrix,

    uvRotateFFront = LumiCube.setUVMatrix,
    uvRotateBFront = LumiCube.setUVMatrix,
    uvRotateFBack = LumiCube.setUVMatrix,
    uvRotateBBack = LumiCube.setUVMatrix,
    uvRotateFTop = LumiCube.setUVMatrix,
    uvRotateBTop = LumiCube.setUVMatrix,
    uvRotateFBottom = LumiCube.setUVMatrix,
    uvRotateBBottom = LumiCube.setUVMatrix,
    uvRotateFLeft = LumiCube.setUVMatrix,
    uvRotateBLeft = LumiCube.setUVMatrix,
    uvRotateFRight = LumiCube.setUVMatrix,
    uvRotateBRight = LumiCube.setUVMatrix,

    fillModeFFront = LumiCube.setUVMatrix,
    fillModeBFront = LumiCube.setUVMatrix,
    fillModeFBack = LumiCube.setUVMatrix,
    fillModeBBack = LumiCube.setUVMatrix,
    fillModeFTop = LumiCube.setUVMatrix,
    fillModeBTop = LumiCube.setUVMatrix,
    fillModeFBottom = LumiCube.setUVMatrix,
    fillModeBBottom = LumiCube.setUVMatrix,
    fillModeFLeft = LumiCube.setUVMatrix,
    fillModeBLeft = LumiCube.setUVMatrix,
    fillModeFRight = LumiCube.setUVMatrix,
    fillModeBRight = LumiCube.setUVMatrix,

    wrapModeFFront = LumiCube.setWrapMode,
    wrapModeBFront = LumiCube.setWrapMode,
    wrapModeFBack = LumiCube.setWrapMode,
    wrapModeBBack = LumiCube.setWrapMode,
    wrapModeFTop = LumiCube.setWrapMode,
    wrapModeBTop = LumiCube.setWrapMode,
    wrapModeFBottom = LumiCube.setWrapMode,
    wrapModeBBottom = LumiCube.setWrapMode,
    wrapModeFLeft = LumiCube.setWrapMode,
    wrapModeBLeft = LumiCube.setWrapMode,
    wrapModeFRight = LumiCube.setWrapMode,
    wrapModeBRight = LumiCube.setWrapMode,

    imageFFront = LumiCube.setTextures,
    imageBFront = LumiCube.setTextures,
    imageFBack = LumiCube.setTextures,
    imageBBack = LumiCube.setTextures,
    imageFTop = LumiCube.setTextures,
    imageBTop = LumiCube.setTextures,
    imageFBottom = LumiCube.setTextures,
    imageBBottom = LumiCube.setTextures,
    imageFLeft = LumiCube.setTextures,
    imageBLeft = LumiCube.setTextures,
    imageFRight = LumiCube.setTextures,
    imageBRight = LumiCube.setTextures,
    InputTex = LumiCube.setTextures,
    OutputTex = LumiCube.setTextures,

    separateSurface = LumiCube.reset,
    multiRatio = LumiCube.reset
}

exports.LumiCube = LumiCube
return exports
