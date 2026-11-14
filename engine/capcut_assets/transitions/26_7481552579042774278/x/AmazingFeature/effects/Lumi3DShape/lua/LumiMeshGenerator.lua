local exports = exports or {}
local LumiMeshGenerator = LumiMeshGenerator or {}
LumiMeshGenerator.__index = LumiMeshGenerator

function LumiMeshGenerator.new(construct, ...)
    self.meshtype = nil
    self.meshSize = nil
    self.res = nil
    self.breverseUV = nil
    self.btwoSide = nil

    self.mesh = nil

    -- property
    self.uvRatio = 1.0 -- y:x
end

function LumiMeshGenerator:constructor()
end

function LumiMeshGenerator:generateVads()
    -- vertex attributes
    local posVAD = Amaz.VertexAttribDesc()
    posVAD.semantic = Amaz.VertexAttribType.POSITION
    local uvVAD = Amaz.VertexAttribDesc()
    uvVAD.semantic = Amaz.VertexAttribType.TEXCOORD0
    local vads = Amaz.Vector()
    vads:pushBack(posVAD)
    vads:pushBack(uvVAD)
    local uviArray = {}
    return vads
end

--@input same as function@getMesh
function LumiMeshGenerator:generateQuadData(rect, res, breverseUV, btwoSide, quadCenter)
    local width = math.max(rect.x, 0.01)
    local height = math.max(rect.y, 0.01)
    res.x = math.max(res.x, 1)
    res.y = math.max(res.y, 1)

    -- vertex data
    local posArray = Amaz.Vec3Vector()
    local uvArray = Amaz.Vec2Vector()
    local indices = Amaz.UInt16Vector()

    if quadCenter == nil then
        quadCenter = Amaz.Vector3f(0.0, 0.0, 0.0)
    end
    for i = 0, res.y do
        local y = i * height / res.y - height / 2.0
        local v = i / res.y
        for j = 0, res.x do
            local x = j * width / res.x - width / 2.0
            local u = j / res.x
            posArray:pushBack(Amaz.Vector3f(x, y, 0.0) + quadCenter)
            if breverseUV then
                uvArray:pushBack(Amaz.Vector2f(v, u))
            else
                uvArray:pushBack(Amaz.Vector2f(u, v))
            end
        end
    end

    -- indice data
    for i = 0, res.y-1 do
        for j = 0, res.x-1 do
            indices:pushBack(i * (res.x+1) + j)
            indices:pushBack(i * (res.x+1) + j + 1)
            indices:pushBack((i+1) * (res.x+1) + j)
            indices:pushBack(i * (res.x+1) + j + 1)
            indices:pushBack((i+1) * (res.x+1) + j + 1)
            indices:pushBack((i+1) * (res.x+1) + j)
        end
    end

    local idbias = posArray:size()
    if btwoSide then
        for i = 0, res.y do
            local y = i * height / res.y - height / 2.0
            local v = i / res.y
            for j = 0, res.x do
                local x = j * width / res.x - width / 2.0
                local u = j / res.x
                posArray:pushBack(Amaz.Vector3f(x, y, 0.0) + quadCenter)
                if breverseUV then
                    uvArray:pushBack(Amaz.Vector2f(v, 1.0 - u))
                else
                    uvArray:pushBack(Amaz.Vector2f(1.0 - u, v))
                end
            end
        end
        for i = 0, res.y-1 do
            for j = 0, res.x-1 do
                indices:pushBack(idbias + i * (res.x+1) + j)
                indices:pushBack(idbias + (i+1) * (res.x+1) + j)
                indices:pushBack(idbias + i * (res.x+1) + j + 1)
                indices:pushBack(idbias + i * (res.x+1) + j + 1)
                indices:pushBack(idbias + (i+1) * (res.x+1) + j)
                indices:pushBack(idbias + (i+1) * (res.x+1) + j + 1)
            end
        end
    end

    if breverseUV then
        self.uvRatio = width / height
    else
        self.uvRatio = height / width
    end
    return {pos = posArray, uv = uvArray, indice = indices}
end

--@input same as function@getMesh
function LumiMeshGenerator:generateEllipseData(rect, res, breverseUV, btwoSide)
    rect.x = math.max(rect.x, 0.01)
    rect.y = math.max(rect.y, 0.01)
    res.x = math.max(res.x, 1)
    res.y = math.max(res.y, 3)

    local radius = rect.x / 2
    local yscale = rect.y / rect.x
    local posArray = Amaz.Vec3Vector()
    local uvArray = Amaz.Vec2Vector()
    local indices = Amaz.UInt16Vector()

    -- vertex data
    local quadCenter = Amaz.Vector3f(0.0, 0.0, 0.0)
    posArray:pushBack(Amaz.Vector3f(0, 0, 0.0) + quadCenter)
    if breverseUV then
        uvArray:pushBack(Amaz.Vector2f(0, 0))
    else
        uvArray:pushBack(Amaz.Vector2f(0.5, 0.5))
    end
    for i = 1, res.x do
        for j = 0, res.y do
            local radian = j / res.y * 2 * math.pi

            local x = math.cos(radian) * i / res.x
            local y = math.sin(radian) * i / res.x
            posArray:pushBack(Amaz.Vector3f(x * radius, y * radius * yscale, 0.0) + quadCenter)
            if breverseUV then
                uvArray:pushBack(Amaz.Vector2f(i/res.x, j/res.y))
            else
                uvArray:pushBack(Amaz.Vector2f(x * 0.5 + 0.5, y * 0.5 + 0.5))
            end
        end
    end

    -- indice data
    for i = 1, res.y do
        indices:pushBack(0)
        indices:pushBack(i)
        indices:pushBack(i+1)
    end
    for i = 1, res.x-1 do
        for j = 1, res.y do
            indices:pushBack((i-1) * (res.y+1) + j)
            indices:pushBack(i * (res.y+1) + j + 1)
            indices:pushBack((i-1) * (res.y+1) + j + 1)
            indices:pushBack((i-1) * (res.y+1) + j)
            indices:pushBack(i * (res.y+1) + j)
            indices:pushBack(i * (res.y+1) + j + 1)
        end
    end

    if btwoSide then
        local idbias = posArray:size()
        posArray:pushBack(Amaz.Vector3f(0, 0, 0.0) + quadCenter)
        if breverseUV then
            uvArray:pushBack(Amaz.Vector2f(0, 0))
        else
            uvArray:pushBack(Amaz.Vector2f(0.5, 0.5))
        end
        for i = 1, res.x do
            for j = 0, res.y do
                local radian = j / res.y * 2 * math.pi
    
                local x = -math.cos(radian) * i / res.x
                local y = math.sin(radian) * i / res.x
                posArray:pushBack(Amaz.Vector3f(x * radius, y * radius * yscale, 0.0) + quadCenter)
                if breverseUV then
                    uvArray:pushBack(Amaz.Vector2f(i/res.x, j/res.y))
                else
                    uvArray:pushBack(Amaz.Vector2f(1.0 - (x * 0.5 + 0.5), y * 0.5 + 0.5))
                end
            end
        end
    
        for i = 1, res.y do
            indices:pushBack(idbias)
            indices:pushBack(idbias+i+1)
            indices:pushBack(idbias+i)
        end
        for i = 1, res.x-1 do
            for j = 1, res.y do
                indices:pushBack(idbias+(i-1) * (res.y+1) + j)
                indices:pushBack(idbias+i * (res.y+1) + j + 1)
                indices:pushBack(idbias+(i-1) * (res.y+1) + j + 1)
                indices:pushBack(idbias+(i-1) * (res.y+1) + j)
                indices:pushBack(idbias+i * (res.y+1) + j)
                indices:pushBack(idbias+i * (res.y+1) + j + 1)
            end
        end
    
    end

    if breverseUV then
        self.uvRatio = 2 * math.pi
    else
        self.uvRatio = yscale
    end

    return {pos = posArray, uv = uvArray, indice = indices}
end

--@input same as function@getMesh
function LumiMeshGenerator:generateRingData(rect, res, breverseUV, btwoSide)
    res.x = math.max(res.x, 1)
    res.y = math.max(res.y, 1)
    
    local outerradius = math.max(0, rect.x) / 2
    local innerradius = outerradius / math.max(1, rect.y)

    local posArray = Amaz.Vec3Vector()
    local uvArray = Amaz.Vec2Vector()
    local indices = Amaz.UInt16Vector()

    -- vertex data
    local quadCenter = Amaz.Vector3f(0.0, 0.0, 0.0)
    for i = 0, res.x do
        local radius = i / res.x * (outerradius - innerradius) + innerradius
        local uvradius = radius / outerradius
        for j = 0, res.y do
            local radian = j / res.y * 2 * math.pi

            local x = math.cos(radian)
            local y = math.sin(radian)
            posArray:pushBack(Amaz.Vector3f(x * radius, y * radius, 0.0) + quadCenter)
            if breverseUV then
                uvArray:pushBack(Amaz.Vector2f(i/res.x, j/res.y))
            else
                uvArray:pushBack(Amaz.Vector2f(x * uvradius * 0.5 + 0.5, y * uvradius * 0.5 + 0.5))
            end
        end
    end

    -- indice data
    for i = 0, res.x-1 do
        for j = 0, res.y do
            indices:pushBack(i * (res.y+1) + j)
            indices:pushBack((i+1) * (res.y+1) + j)
            indices:pushBack(i * (res.y+1) + j + 1)
            indices:pushBack(i * (res.y+1) + j + 1)
            indices:pushBack((i+1) * (res.y+1) + j)
            indices:pushBack((i+1) * (res.y+1) + j + 1)
        end
    end

    if btwoSide then
        local idbias = posArray:size()
        for i = 0, res.x do
            local radius = i / res.x * (outerradius - innerradius) + innerradius
            local uvradius = radius / outerradius
            for j = 0, res.y do
                local radian = j / res.y * 2 * math.pi
    
                local x = -math.cos(radian)
                local y = math.sin(radian)
                posArray:pushBack(Amaz.Vector3f(x * radius, y * radius, 0.0) + quadCenter)
                if breverseUV then
                    uvArray:pushBack(Amaz.Vector2f(i/res.x, j/res.y))
                else
                    uvArray:pushBack(Amaz.Vector2f(1.0 - (x * uvradius * 0.5 + 0.5), y * uvradius * 0.5 + 0.5))
                end
            end
        end
    
        -- indice data
        for i = 0, res.x-1 do
            for j = 0, res.y do
                indices:pushBack(idbias + i * (res.y+1) + j)
                indices:pushBack(idbias + (i+1) * (res.y+1) + j)
                indices:pushBack(idbias + i * (res.y+1) + j + 1)
                indices:pushBack(idbias + i * (res.y+1) + j + 1)
                indices:pushBack(idbias + (i+1) * (res.y+1) + j)
                indices:pushBack(idbias + (i+1) * (res.y+1) + j + 1)
            end
        end
    end

    if breverseUV then
        self.uvRatio = 2 * math.pi
    else
        self.uvRatio = 1
    end

    return {pos = posArray, uv = uvArray, indice = indices}
end

--@input same as function@getMesh
function LumiMeshGenerator:combineMeshData(mesh1, mesh2, modelMat)
    local posArray = mesh1.pos:copy() -- Amaz.Vec3Vector()
    local uvArray = mesh1.uv:copy() -- Amaz.Vec2Vector()
    local indices = mesh1.indice:copy() -- Amaz.UInt16Vector()

    if modelMat == nil then
        modelMat = Amaz.Matrix3x3f():setIdentity()
    end
    local idBias = mesh1.pos:size()
    for i = 0, mesh2.pos:size()-1 do
        posArray:pushBack(modelMat:multiplyVector3(mesh2.pos:get(i)))
    end
    for i = 0, mesh2.uv:size()-1 do
        uvArray:pushBack(mesh2.uv:get(i))
    end
    for i = 0, mesh2.indice:size()-1 do
        indices:pushBack(mesh2.indice:get(i) + idBias)
    end

    return {pos = posArray, uv = uvArray, indice = indices}
end

--@input same as function@getMesh
function LumiMeshGenerator:generateCubeData(rect, res, breverseUV, btwoSide)
    res.x = math.max(res.x, 1)
    res.y = math.max(res.y, 1)
    res.z = math.max(res.z, 1)
    rect.x = math.max(rect.x, 0.01)
    rect.y = math.max(rect.y, 0.01)
    rect.z = math.max(rect.z, 0.01)

    local posArray = Amaz.Vec3Vector()
    local uvArray = Amaz.Vec2Vector()
    local indices = Amaz.UInt16Vector()

    local backMat = Amaz.Matrix3x3f():setIdentity()
    Amaz.Matrix3x3f.eulerToMatrix(Amaz.Vector3f(0, math.pi, 0), backMat)

    local leftMat = Amaz.Matrix3x3f():setIdentity()
    Amaz.Matrix3x3f.eulerToMatrix(Amaz.Vector3f(0, -math.pi/2, 0), leftMat)

    local rightMat = Amaz.Matrix3x3f():setIdentity()
    Amaz.Matrix3x3f.eulerToMatrix(Amaz.Vector3f(0, math.pi/2, 0), rightMat)

    local topMat = Amaz.Matrix3x3f():setIdentity()
    Amaz.Matrix3x3f.eulerToMatrix(Amaz.Vector3f(-math.pi/2, 0, 0), topMat)

    local bottomMat = Amaz.Matrix3x3f():setIdentity()
    Amaz.Matrix3x3f.eulerToMatrix(Amaz.Vector3f(math.pi/2, 0, 0), bottomMat)

    local quadMesh = self:generateQuadData(rect, res, breverseUV, btwoSide, Amaz.Vector3f(0, 0, rect.z / 2))
    local backMesh = self:generateQuadData(rect, res, breverseUV, btwoSide, Amaz.Vector3f(0, 0, rect.z / 2))
    quadMesh = self:combineMeshData(quadMesh, backMesh, backMat)
    local leftMesh = self:generateQuadData(
        Amaz.Vector3f(rect.z, rect.y, 0), 
        Amaz.Vector3f(res.z, res.y, 0), 
        breverseUV, btwoSide, 
        Amaz.Vector3f(0, 0, rect.x / 2))
    quadMesh = self:combineMeshData(quadMesh, leftMesh, leftMat)
    local rightMesh = self:generateQuadData(
        Amaz.Vector3f(rect.z, rect.y, 0), 
        Amaz.Vector3f(res.z, res.y, 0), 
        breverseUV, btwoSide, 
        Amaz.Vector3f(0, 0, rect.x / 2))
    quadMesh = self:combineMeshData(quadMesh, rightMesh, rightMat)
    local topMesh = self:generateQuadData(
        Amaz.Vector3f(rect.x, rect.z, 0), 
        Amaz.Vector3f(res.x, res.z, 0), 
        breverseUV, btwoSide, 
        Amaz.Vector3f(0, 0, rect.y / 2))
    quadMesh = self:combineMeshData(quadMesh, topMesh, topMat)
    local bottomMesh = self:generateQuadData(
        Amaz.Vector3f(rect.x, rect.z, 0), 
        Amaz.Vector3f(res.x, res.z, 0), 
        breverseUV, btwoSide, 
        Amaz.Vector3f(0, 0, rect.y / 2))
    quadMesh = self:combineMeshData(quadMesh, bottomMesh, bottomMat)

    if breverseUV then
        self.uvRatio = rect.x / rect.y
    else
        self.uvRatio = rect.y / rect.x
    end

    return quadMesh
end

--@input same as function@getMesh
function LumiMeshGenerator:generateSphereData(rect, res, breverseUV, btwoSide)
    local rx = math.max(rect.x, 0.01) / 2
    local ry = math.max(rect.y, 0.01) / 2
    local rz = math.max(rect.z, 0.01) / 2
    local longitudeRes = math.max(res.x, 4)
    local latitudeRes = math.max(res.y, 1) * 2 + 1
    
    -- vertex data
    local posArray = Amaz.Vec3Vector()
    local uvArray = Amaz.Vec2Vector()
    local indices = Amaz.UInt16Vector()
    for i = 0, latitudeRes do
        local latitude = i / (latitudeRes) * math.pi
        for j = 0, longitudeRes do
            local longitude = j / longitudeRes * 2 * math.pi
            local x = math.sin(latitude) * math.cos(longitude) * rx
            local y = math.cos(latitude) * ry
            local z = math.sin(latitude) * math.sin(longitude) * rz
            local u = j / longitudeRes
            local v = 1.0 - i / latitudeRes
            posArray:pushBack(Amaz.Vector3f(x, y, z))
            if breverseUV then
                uvArray:pushBack(Amaz.Vector2f(v, u))
            else
                uvArray:pushBack(Amaz.Vector2f(u, v))
            end
        end
    end
    
    -- indice data
    for i = 0, latitudeRes-1 do
        for j = 0, longitudeRes-1 do
            if i > 0 then
                indices:pushBack(i * (longitudeRes+1) + j)
                indices:pushBack((i+1) * (longitudeRes+1) + j)
                indices:pushBack(i * (longitudeRes+1) + j + 1)
            end
            if i < latitudeRes-1 then
                indices:pushBack(i * (longitudeRes+1) + j + 1)
                indices:pushBack((i+1) * (longitudeRes+1) + j)
                indices:pushBack((i+1) * (longitudeRes+1) + j + 1)
            end
        end
    end

    if breverseUV then
        self.uvRatio = rx / rz
    else
        self.uvRatio = rz / rx
    end
    return {pos = posArray, uv = uvArray, indice = indices}
end

--@input same as function@getMesh
function LumiMeshGenerator:generateCylinderData(rect, res, breverseUV, btwoSide)
    local radius = rect.x / 2
    local height = rect.y
    res.x = math.max(res.x, 3)
    res.y = math.max(res.y, 1)

    -- vertex data
    local posArray = Amaz.Vec3Vector()
    local uvArray = Amaz.Vec2Vector()
    local indices = Amaz.UInt16Vector()

    local quadCenter = Amaz.Vector3f(0.0, 0.0, 0.0)
    for i = 0, res.y do
        local y = i * height / res.y - height / 2.0
        local v = i / res.y
        for j = 0, res.x do
            local radian = j / res.x * 2 * math.pi
            local x = math.cos(radian) * radius
            local z = math.sin(radian) * radius
            local u = j / res.x
            posArray:pushBack(Amaz.Vector3f(x, y, z) + quadCenter)
            if breverseUV then
                uvArray:pushBack(Amaz.Vector2f(v, u))
            else
                uvArray:pushBack(Amaz.Vector2f(u, v))
            end
        end
    end

    -- indice data
    for i = 0, res.y-1 do
        for j = 0, res.x-1 do
            indices:pushBack(i * (res.x+1) + j)
            indices:pushBack((i+1) * (res.x+1) + j)
            indices:pushBack(i * (res.x+1) + j + 1)
            indices:pushBack(i * (res.x+1) + j + 1)
            indices:pushBack((i+1) * (res.x+1) + j)
            indices:pushBack((i+1) * (res.x+1) + j + 1)
        end
    end

    local idbias = posArray:size()
    if btwoSide then
        for i = 0, res.y do
            local y = i * height / res.y - height / 2.0
            local v = i / res.y
            for j = 0, res.x do
                local radian = j / res.x * 2 * math.pi - 0.1
                local x = math.cos(radian) * radius
                local z = -math.sin(radian) * radius
                local u = j / res.x
                posArray:pushBack(Amaz.Vector3f(x, y, z) + quadCenter)
                if breverseUV then
                    uvArray:pushBack(Amaz.Vector2f(v, u))
                else
                    uvArray:pushBack(Amaz.Vector2f(u, v))
                end
            end
        end
    
        for i = 0, res.y-1 do
            for j = 0, res.x-1 do
                indices:pushBack(idbias + i * (res.x+1) + j)
                indices:pushBack(idbias + (i+1) * (res.x+1) + j)
                indices:pushBack(idbias + i * (res.x+1) + j + 1)
                indices:pushBack(idbias + i * (res.x+1) + j + 1)
                indices:pushBack(idbias + (i+1) * (res.x+1) + j)
                indices:pushBack(idbias + (i+1) * (res.x+1) + j + 1)
            end
        end
    end

    if breverseUV then
        self.uvRatio = (radius * math.pi) / height
    else
        self.uvRatio = height / (radius * math.pi)
    end

    return {pos = posArray, uv = uvArray, indice = indices}
end

--@input same as function@getMesh
function LumiMeshGenerator:generateDonutData(rect, res, breverseUV, btwoSide)
    -- r: inner radius, tunnel's radius
    -- R: outer radius, distance between tunnel's center and donut's center
    local R = math.max(rect.x, 0.01) / 2
    local r = math.min(math.max(rect.y, 0.01) / 2, R / 2)

    local rRes = math.max(res.x, 4) + 1
    local RRes = math.max(res.y, 4) + 1
    
    -- vertex data
    local posArray = Amaz.Vec3Vector()
    local uvArray = Amaz.Vec2Vector()
    local indices = Amaz.UInt16Vector()
    for i = 0, RRes do
        local Theta = i / RRes * math.pi * 2
        for j = 0, rRes do
            local theta = j / rRes * 2 * math.pi
            local xx = R - math.cos(theta) * r
            local x = xx * math.cos(Theta)
            local y = math.sin(theta) * r
            local z = xx * math.sin(Theta)
            local u = j / rRes
            local v = i / RRes
            posArray:pushBack(Amaz.Vector3f(x, y, z))
            if breverseUV then
                uvArray:pushBack(Amaz.Vector2f(v, u))
            else
                uvArray:pushBack(Amaz.Vector2f(u, v))
            end
        end
    end
    
    -- indice data
    for i = 0, RRes-1 do
        for j = 0, rRes-1 do
            indices:pushBack(i * (rRes+1) + j)
            indices:pushBack((i+1) * (rRes+1) + j)
            indices:pushBack(i * (rRes+1) + j + 1)
            indices:pushBack(i * (rRes+1) + j + 1)
            indices:pushBack((i+1) * (rRes+1) + j)
            indices:pushBack((i+1) * (rRes+1) + j + 1)
        end
    end

    if breverseUV then
        self.uvRatio = r / R
    else
        self.uvRatio = R / r
    end

    return {pos = posArray, uv = uvArray, indice = indices}
end

--@input same as function@getMesh
function LumiMeshGenerator:_getMesh(meshtype, meshSize, res, breverseUV, btwoSide)
    local meshData = nil

    if meshtype == "quad" then
        meshData = self:generateQuadData(meshSize, res, breverseUV, btwoSide)
    elseif meshtype == "ellipse" then
        meshData = self:generateEllipseData(meshSize, res, breverseUV, btwoSide)
    elseif meshtype == "ring" then
        meshData = self:generateRingData(meshSize, res, breverseUV, btwoSide)
    elseif meshtype == "cube" then
        meshData = self:generateCubeData(meshSize, res, breverseUV, btwoSide)
    elseif meshtype == "sphere" then
        meshData = self:generateSphereData(meshSize, res, breverseUV, btwoSide)
    elseif meshtype == "cylinder" then
        meshData = self:generateCylinderData(meshSize, res, breverseUV, btwoSide)
    elseif meshtype == "donut" then
        meshData = self:generateDonutData(meshSize, res, breverseUV, btwoSide)
    else
        Amaz.LOGI('zikuan', "wrong mesh type!")
        meshData = nil
    end

    if meshData == nil then
        return nil
    end

    local mesh = Amaz.Mesh()

    -- vertex attributes
    mesh.vertexAttribs = self:generateVads()
    mesh.clearAfterUpload = true

    -- mesh data
    mesh:setVertexArray(meshData.pos)
    mesh:setUvArray(0, meshData.uv)

    local subMesh = Amaz.SubMesh()
    subMesh.primitive = Amaz.Primitive.TRIANGLES
    subMesh.indices16 = meshData.indice
    subMesh.mesh = mesh
    mesh:addSubMesh(subMesh)
    return mesh

end

--@input meshtype, string
--@input meshSize or rect, Amaz.Vector3f
--@input res, Amaz.Vector2f
--@input breverseUV, boolean
--@input btwoSide, boolean
function LumiMeshGenerator:getMesh(meshtype, meshSize, res, breverseUV, btwoSide)
    if self.meshtype == meshtype and self.meshSize == meshSize and self.res == res and self.breverseUV == breverseUV and self.btwoSide == btwoSide then
        return self.mesh
    else
        self.meshtype = meshtype
        self.meshSize = meshSize
        self.res = res
        self.breverseUV = breverseUV
        self.btwoSide = btwoSide
        local mesh = self:_getMesh(meshtype, meshSize, res, breverseUV, btwoSide)
        if mesh ~= nil then
            self.mesh = mesh
        end
        return self.mesh
    end
end

exports.LumiMeshGenerator = LumiMeshGenerator
return exports
