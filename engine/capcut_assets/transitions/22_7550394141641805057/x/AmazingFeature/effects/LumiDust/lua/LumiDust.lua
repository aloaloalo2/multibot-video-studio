local isEditor = (Amaz.Macros and Amaz.Macros.EditorSDK) and true or false
local exports = exports or {}
local LumiDust = LumiDust or {}
LumiDust.__index = LumiDust
---@class LumiDust : ScriptComponent
---@field InputTex Texture
---@field OutputTex Texture

---@field dustNum number [UI(Range={0, 2}, Slider)]
---@field dustSize number [UI(Range={0, 10}, Slider)]

---@field distorIns number

---@field brightness number
---@field contrast number
---@field quantity number
---@field complexity number
---@field evolution number
---@field cycle int [UI(Range={1, 100}, Slider)]
---@field offset_x number
---@field offset_y number


---@field maskType string [UI(Option={"Noise", "Line", "Image"})]

---@field mask_noise_brightness number
---@field mask_noise_contrast number
---@field mask_noise_quantity number
---@field mask_noise_complexity number
---@field mask_noise_evolution number
---@field mask_noise_cycle int [UI(Range={1, 100}, Slider)]
---@field mask_noise_offset_x number
---@field mask_noise_offset_y number
---@field mask_line_rot number 
---@field maskFeather number [UI(Range={0, 1}, Drag)]
---@field mask_image Texture


---@field startRotX number
---@field startRotY number
---@field startRotZ number
---@field startMoveX number
---@field startMoveY number
---@field startMoveZ number
---@field startSize number

---@field endRotX number
---@field endRotY number
---@field endRotZ number
---@field endMoveX number
---@field endMoveY number
---@field endMoveZ number
---@field endSize number
---@field endImg Texture

---@field progress number [UI(Range={0, 100}, Drag)]


local maskTypeVec = {
    "Noise", "Line", "Image"
}

local AE_EFFECT_TAG = 'AE_EFFECT_TAG LumiTag'

local function createRenderTexture(width, height, filterMag, filterMin)
    local rt = Amaz.RenderTexture()
    rt.width = width
    rt.height = height
    rt.depth = 1
    rt.filterMag = filterMag or Amaz.FilterMode.LINEAR
    rt.filterMin = filterMin or Amaz.FilterMode.LINEAR
    rt.filterMipmap = Amaz.FilterMipmapMode.NONE
    rt.attachment = Amaz.RenderTextureAttachment.NONE
    return rt
end

local function updateTexSize(rt, width, height)
    if rt == nil or width <= 0 or height <= 0 then
        return
    end
    if rt.width ~= width or rt.height ~= height then
        rt.width = width
        rt.height = height
    end
end

function LumiDust.new(construct, ...)

    local self = setmetatable({}, LumiDust)

    self.__lumi_type = "lumi_obj"
    self.__lumi_rt_pingpong_type = "custom"

    self.InputTex = nil
    self.OutputTex = nil
    self.width = 0
    self.height = 0

    self.startTime = 0.0
    self.endTime = 6

    -- for particle

    self.progress = 1

    self.maskFeather = 1
    self.brightness = 0
    self.contrast = 0
    self.quantity = 2
    self.complexity = 1
    self.evolution = 0
    self.cycle = 100
    self.offset_x = 0
    self.offset_y = 0
    self.distorIns = 1
    self.gravity = 0
    self.gravityRot = 0

    self.mask_noise_brightness = 0
    self.mask_noise_contrast = 0
    self.mask_noise_quantity = 2
    self.mask_noise_complexity = 1
    self.mask_noise_evolution = 0
    self.mask_noise_cycle = 100
    self.mask_noise_offset_x = 0
    self.mask_noise_offset_y = 0
    self.mask_line_rot = 0
    self.mask_image = nil
    self.maskType = "Noise"

    self.startRotX = 0
    self.startRotY = 0
    self.startRotZ = 0
    self.startMoveX = 0
    self.startMoveY = 0
    self.startMoveZ = 0
    self.startSize = 1

    self.endRotX = 0
    self.endRotY = 0
    self.endRotZ = 0
    self.endMoveX = 0
    self.endMoveY = 0
    self.endMoveZ = 0
    self.endSize = 1
    self.endImg = nil
    self.AEPlugin = false

    self.dustNum = 1
    self.dustSize = 1

    return self
end

function LumiDust:setEffectAttr(key, value, comp)
    local function _setEffectAttr(_key, _value, _force)
        if _force or self[_key] ~= nil then
            self[_key] = _value
            if comp and comp.properties ~= nil then
                comp.properties:set(_key, _value)
            end
        end
    end
    
    if key == 'maskType' then
        local maskType = maskTypeVec[value + 1]
        _setEffectAttr(key, maskType)
    else
        _setEffectAttr(key, value)
    end
end
function LumiDust:createCustomMesh()
    local customMesh = Amaz.Mesh()
    local customSubMesh = Amaz.SubMesh()
    customSubMesh.primitive = Amaz.Primitive.POINTS
    if customMesh and customSubMesh then
    end

    local attPosition = Amaz.VertexAttribDesc()
    attPosition.semantic = Amaz.VertexAttribType.POSITION
    local texcoord1 = Amaz.VertexAttribDesc()
    texcoord1.semantic = Amaz.VertexAttribType.TEXCOORD1

    local vads = Amaz.Vector()

    vads:pushBack(attPosition)

    -- vads:pushBack(uv)
    vads:pushBack(texcoord1)

    customMesh.vertexAttribs = vads

    local vertexData = {}
    local indexData = {}

    local fv = Amaz.FloatVector()

    local indices = Amaz.UInt16Vector()

    local pointNum = 1

            
    fv:pushBack(0)
    fv:pushBack(0)
    fv:pushBack(14.50)
    fv:pushBack(pointNum)
    fv:pushBack(pointNum)
    indices:pushBack(pointNum-1)
    customMesh.vertices = fv
    customSubMesh.indices16 = indices
    customSubMesh.mesh = customMesh
    customMesh:addSubMesh(customSubMesh)

    return customMesh
end


function LumiDust:onStart(comp)
    

    self.entity = comp.entity
    self.comp = comp
    self.TAG = AE_EFFECT_TAG .. ' ' .. self.entity.name

    -- Use entity instead of scene 
    self.camera = self.entity:searchEntity("Camera_renderer"):getComponent("Camera")

    -- if temporary texture has the same dimensions as self.OutputTex, and need not persist, advised to used sharedRT
    if self.lumiSharedRt and self.lumiSharedRt:size() > 0 then
        self.midTex = self.lumiSharedRt:get(0)
    end
    self.dust_mat = self.entity:searchEntity("render_mesh"):getComponent("MeshRenderer").material

    self.noiseMaterial = self.entity:searchEntity("noise"):getComponent("MeshRenderer").material
    self.maskNoiseMaterial = self.entity:searchEntity("maskNoise"):getComponent("MeshRenderer").material


    -- self.dust_mat.xshader.passes:get(0).instanceCount = self.OutputTex.width*self.OutputTex.height
    self.MeshEntity = self.entity:searchEntity("render_mesh"):getComponent("MeshRenderer")
    



end

function LumiDust:onUpdate(comp, deltaTime)
    

    -- set the input and output textures to be displayed
    if self.OutputTex then
        self.camera.renderTexture = self.OutputTex
    end

    -- if using sharedRT, dimensions need to be consistent with self.InputTex or self.OutputTex
    if self.midTex then
        if self.midTex.width ~= self.OutputTex.width or self.midTex.height ~= self.OutputTex.height then
            self.midTex.width = self.OutputTex.width
            self.midTex.height = self.OutputTex.height
        end
    end


    self.curTime = self.curTime + deltaTime
      
    self:updateMaterials(self.curTime)
end


function LumiDust:updateMaterials(time)
    self.dust_mat:setTex("inputTex", self.InputTex)

    self.noiseMaterial:setFloat("u_Brightness", self.brightness)
    self.noiseMaterial:setFloat("u_Contrast", self.contrast)
    self.noiseMaterial:setVec2("u_Scale", Amaz.Vector2f(self.quantity, self.quantity));
    self.noiseMaterial:setFloat("u_Complexity", self.complexity);
    self.noiseMaterial:setFloat("u_Evolution", math.abs(self.evolution) / 90.0);
    self.noiseMaterial:setFloat("u_Cycle", math.max(2, math.floor(self.cycle*3.0 + 0.5)));
    self.noiseMaterial:setVec2("u_Offset", Amaz.Vector2f(self.offset_x, self.offset_y))
    self.noiseMaterial:setFloat("picture_scale", 1)


    self.maskNoiseMaterial:setFloat("u_Brightness", self.mask_noise_brightness)
    self.maskNoiseMaterial:setFloat("u_Contrast", self.mask_noise_contrast)
    self.maskNoiseMaterial:setVec2("u_Scale", Amaz.Vector2f(self.mask_noise_quantity, self.mask_noise_quantity));
    self.maskNoiseMaterial:setFloat("u_Complexity", self.mask_noise_complexity);
    self.maskNoiseMaterial:setFloat("u_Evolution", math.abs(self.mask_noise_evolution) / 90.0);
    self.maskNoiseMaterial:setFloat("u_Cycle", math.max(2, math.floor(self.mask_noise_cycle*3.0 + 0.5)));
    self.maskNoiseMaterial:setVec2("u_Offset", Amaz.Vector2f(self.mask_noise_offset_x, self.mask_noise_offset_y))
    self.maskNoiseMaterial:setFloat("picture_scale", 1)

    local normalW = self.OutputTex.width/math.min(self.OutputTex.width,self.OutputTex.height)*720
    local normalH = self.OutputTex.height/math.min(self.OutputTex.width,self.OutputTex.height)*720
    self.dust_mat:setFloat("normalW",normalW)
    self.dust_mat:setFloat("normalH",normalH)
    self.dust_mat.xshader.passes:get(0).instanceCount = normalW*normalH*self.dustNum*self.dustNum
    -- Amaz.LOGI("1111", self.dustNum)
    self.dust_mat:setFloat("dustNum",self.dustNum)
    self.dust_mat:setFloat("dustSize",self.dustSize)
  
    self.dust_mat:setFloat("iTime", self.curTime)
    self.dust_mat:setFloat("distorIns", self.distorIns)
    self.dust_mat:setFloat("noiseFeather", self.maskFeather)

    if(self.maskType == "Noise") then
        self.dust_mat:setInt("maskType", 0)
    elseif(self.maskType == "Line") then
        self.dust_mat:setInt("maskType", 1)
        self.dust_mat:setFloat("mask_line_rot",math.rad(self.mask_line_rot))
        
    else
        self.dust_mat:setInt("maskType", 2)
        self.dust_mat:setTex("mask_image", self.mask_image)
    end


    self.dust_mat:setFloat("startRotX",math.rad(self.startRotX))
    self.dust_mat:setFloat("startRotY",math.rad(self.startRotY))
    self.dust_mat:setFloat("startRotZ",math.rad(self.startRotZ))
    self.dust_mat:setFloat("startMoveX",self.startMoveX)
    self.dust_mat:setFloat("startMoveY",self.startMoveY)
    self.dust_mat:setFloat("startMoveZ",self.startMoveZ)
    self.dust_mat:setFloat("startSize",self.startSize)

    self.dust_mat:setFloat("endRotX",math.rad(self.endRotX))
    self.dust_mat:setFloat("endRotY",math.rad(self.endRotY))
    self.dust_mat:setFloat("endRotZ",math.rad(self.endRotZ))
    self.dust_mat:setFloat("endMoveX",self.endMoveX)
    self.dust_mat:setFloat("endMoveY",self.endMoveY)
    self.dust_mat:setFloat("endMoveZ",self.endMoveZ)
    self.dust_mat:setFloat("endSize",self.endSize)
    self.dust_mat:setTex("endImg", self.endImg)
    self.dust_mat:setFloat("progress",self.progress/100)

    if self.AEPlugin then
        self.dust_mat:setInt('AEPlugin', 1)
    else
        self.dust_mat:setInt('AEPlugin', 0)
    end

end
function LumiDust:onEvent(sys,event)

end

exports.LumiDust = LumiDust
return exports
