const effect_api = "undefined" != typeof effect ? effect : "undefined" != typeof tt ? tt : "undefined" != typeof lynx ? lynx : {};
const Amaz = effect_api.getAmaz();
const isEditor = (Amaz.Macros && Amaz.Macros.EditorSDK) && true || false


class LumiManager {
    constructor() {
        this.name = "LumiManager";

        this.startTime = 0.0
        this.endTime = 6.0
        this.curTime = 0.0

        this.animationMode = 0 // AnimationMode.Once
        this.autoPlay = true
        this.debugTime = 0.0

        this.jsSysScript = null;
    }

    onInit()
    {
        this.scene = null;
    }

    onLoadScenes(...scenes)
    {
        this.scene = scenes[0];
    }

    onUnloadScenes()
    {
        this.jsSysScript = null;
        this.scene = null;
        this.builtinObject = null;
        this.InputTex = null;
        this.OutputTex = null;
        this.width = null;
        this.height = null;
        this.curTime = 0.0;
        this.startTime = 0.0;
        this.endTime = 0.0;
    }

    onStart() {
        console.log("running:LumiManager:onStart");
        
        this.builtinObject = Amaz.AmazingManager.getSingleton("BuiltinObject");

    }

    onUpdate(deltaTime) {
        const w = this.builtinObject.getInputTextureWidth();
        const h = this.builtinObject.getInputTextureHeight();
        
        if (this.InputTex) {
            w = this.InputTex.width;
            h = this.InputTex.height;
        }
        
        if (this.OutputTex && (this.OutputTex.width !== w || this.OutputTex.height !== h)) {
            console.error('Invalid rt size, input: ' + w + 'x' + h + ', output: ' + this.OutputTex.width + 'x' + this.OutputTex.height);
        }
        
        if (this.width === null || this.width !== w || this.height === null || this.height !== h) {
            this.width = w;
            this.height = h;
            this.updateOutputRtSize();
        }

        this.curTime = this.curTime + deltaTime;
 
    }

    onLateUpdate(deltaTime) {
        // console.log("running:LumiManager:onLateUpdate");
    }

    onEvent(event) {
        
    }

    onDestroy() {
        
    }

    onSetFeatureTime(type, value){
        if (type === 'startTime') {
            this.startTime = value;
        } else if (type === 'endTime') {
            this.endTime = value;
        } else if (type == 'curTime') {
            this.curTime = value;
        }
        if (this.jsSysScript == null)
        {
            this.jsScriptSystem = this.scene.getSystem("JSScriptSystem");
            if (this.jsScriptSystem) {
                const script = this.jsScriptSystem.getSystemScriptByName("JSSys");
                if (script) {
                    this.jsSysScript = script.ref;
                }
            }
        }

        if (this.jsSysScript != null)
        {
            const curTime = this.curTime;
            const startTime = this.startTime;
            const endTime = this.endTime;
            
            this.jsSysScript.curTime = curTime;
            this.jsSysScript.startTime = startTime;
            this.jsSysScript.endTime = endTime;
        }
    }

    updateOutputRtSize() {
        // 更新输出渲染纹理大小的逻辑
        console.log("LumiManager: 更新输出渲染纹理大小", this.width, "x", this.height);
    }
}

exports.LumiManager = LumiManager;
