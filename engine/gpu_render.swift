import Foundation
import AVFoundation
import CoreImage
import CoreVideo
import Metal

struct Project: Decodable { let width: Int; let height: Int; let fps: Int32; let duration: Double; let scenes: [Scene] }
struct Scene: Decodable { let start: Double; let end: Double; let color: String; let layers: [Layer] }
struct Gradient: Decodable { let colors: [String]; let points: [[Double]]; let speed: Double?; let amplitude: Double?; let softness: Double? }
struct Layer: Decodable { let kind: String; let source: String; let width: Double; let height: Double; let trim_start: Double; let first: Int; let frames: [[Double]]; let gradient: Gradient?; let alphaFrames: [Double]?; let group: String?; let groupAlpha: [Double]? }

func fail(_ message: String) -> Never { FileHandle.standardError.write(Data((message + "\n").utf8)); exit(1) }
func color(_ hex: String) -> CIColor {
    let clean = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
    let value = UInt64(clean, radix: 16) ?? 0x101114
    return CIColor(red: CGFloat((value >> 16) & 255)/255, green: CGFloat((value >> 8) & 255)/255, blue: CGFloat(value & 255)/255, alpha: 1)
}

let gradientKernelSource = """
kernel vec4 gradient(vec3 c0, vec3 c1, vec3 c2, vec3 c3,
                     vec2 p0, vec2 p1, vec2 p2, vec2 p3,
                     float phase, float amplitude, float softness, vec2 size) {
    vec2 uv = (destCoord() - vec2(0.5,0.5)) / (size - vec2(1.0,1.0));
    uv.y = 1.0 - uv.y;
    vec2 q0 = clamp(p0 + amplitude*vec2(sin(phase),cos(phase*0.82)), 0.02, 0.98);
    vec2 q1 = clamp(p1 + amplitude*vec2(sin(phase+1.7),cos(phase*0.82+1.3)), 0.02, 0.98);
    vec2 q2 = clamp(p2 + amplitude*vec2(sin(phase+3.4),cos(phase*0.82+2.6)), 0.02, 0.98);
    vec2 q3 = clamp(p3 + amplitude*vec2(sin(phase+5.1),cos(phase*0.82+3.9)), 0.02, 0.98);
    vec2 d0 = uv-q0; vec2 d1 = uv-q1; vec2 d2 = uv-q2; vec2 d3 = uv-q3;
    float w0 = 1.0/pow(dot(d0,d0)+softness,1.8);
    float w1 = 1.0/pow(dot(d1,d1)+softness,1.8);
    float w2 = 1.0/pow(dot(d2,d2)+softness,1.8);
    float w3 = 1.0/pow(dot(d3,d3)+softness,1.8);
    return vec4((c0*w0+c1*w1+c2*w2+c3*w3)/(w0+w1+w2+w3),1.0);
}
"""
let gradientKernel = CIColorKernel(source:gradientKernelSource)
func gradientImage(_ config: Gradient, _ time: Double) -> CIImage {
    guard config.colors.count == 4, config.points.count == 4, config.points.allSatisfy({$0.count == 2}), let kernel=gradientKernel else { fail("Invalid gradient") }
    func rgb(_ hex:String) -> CIVector {
        guard let n=UInt64(hex.trimmingCharacters(in:CharacterSet(charactersIn:"#")),radix:16) else { fail("Invalid gradient color") }
        return CIVector(x:CGFloat((n>>16)&255)/255,y:CGFloat((n>>8)&255)/255,z:CGFloat(n&255)/255)
    }
    let phase=time*(config.speed ?? 0.05)*2*Double.pi
    let args:[Any]=config.colors.map(rgb)+config.points.map{CIVector(x:$0[0],y:$0[1])}+[phase,config.amplitude ?? 0.14,config.softness ?? 0.1,CIVector(x:320,y:180)]
    guard let result=kernel.apply(extent:CGRect(x:0,y:0,width:320,height:180),arguments:args) else { fail("Cannot render gradient") }
    return result
}

final class SequentialVideo {
    let reader: AVAssetReader
    let output: AVAssetReaderTrackOutput
    var next: CMSampleBuffer?
    var current: CVPixelBuffer?
    let sourceFPS: Double
    let outputFPS: Double
    var outputOffset: Double = 0
    var alphaFrameOffset: Int = 0
    // HEVC with alpha written by FFmpeg's hevc_videotoolbox (the studio's motion-code renders) holds straight colour
    // but is labelled premultiplied, and AVFoundation hands it over as such: Core Image then read every soft edge pixel
    // at full brightness and letters got a ring of light dots in the export (26 November 2026, «що з якістю
    // тексту?»). FFmpeg's own decoder, the CPU path, reads it as straight, so it is premultiplied here to match.
    // ProRes 4444 comes out of AVFoundation premultiplied already and is left alone.
    var straightAlpha = false
    init(_ path: String, _ start: Double, _ duration: Double, _ targetFPS: Double) throws {
        outputFPS = targetFPS
        let asset = AVURLAsset(url: URL(fileURLWithPath: path))
        guard let track = asset.tracks(withMediaType: .video).first else { throw NSError(domain:"GPUPrototype", code:1, userInfo:[NSLocalizedDescriptionKey:"Video stream unavailable: \(URL(fileURLWithPath:path).lastPathComponent)"]) }
        if let description = track.formatDescriptions.first {
            let format = description as! CMFormatDescription
            let subtype = CMFormatDescriptionGetMediaSubType(format)
            let alpha = (CMFormatDescriptionGetExtension(format, extensionKey: kCMFormatDescriptionExtension_ContainsAlphaChannel) as? Bool) ?? false
            straightAlpha = alpha && (subtype == kCMVideoCodecType_HEVC || subtype == kCMVideoCodecType_HEVCWithAlpha || subtype == 0x68657631)   // hvc1, muxa, hev1
        }
        sourceFPS = track.nominalFrameRate > 0 ? Double(track.nominalFrameRate) : 25
        reader = try AVAssetReader(asset: asset)
        let attrs: [String: Any] = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA, kCVPixelBufferMetalCompatibilityKey as String: true]
        output = AVAssetReaderTrackOutput(track: track, outputSettings: attrs)
        output.alwaysCopiesSampleData = false
        guard reader.canAdd(output) else { throw NSError(domain:"GPUPrototype", code:2, userInfo:[NSLocalizedDescriptionKey:"Cannot decode video"]) }
        reader.add(output)
        // Reading from exactly the trim point can return an earlier frame with
        // its timestamp clipped to that point. Seek a little earlier and skip
        // samples before the requested start, matching the software renderer.
        reader.timeRange = CMTimeRange(start: CMTime(seconds: max(0,start-2/max(1,sourceFPS)), preferredTimescale: 60000), duration: CMTime(seconds: duration + 2, preferredTimescale: 60000))
        guard reader.startReading() else { throw reader.error ?? NSError(domain:"GPUPrototype", code:3) }
        next = output.copyNextSampleBuffer()
        while let sample = next, CMSampleBufferGetPresentationTimeStamp(sample).seconds < start - 0.000001 { next = output.copyNextSampleBuffer() }
        if let first = next {
            let firstTime = CMSampleBufferGetPresentationTimeStamp(first).seconds
            alphaFrameOffset = max(0,Int(((firstTime - max(0,start))*outputFPS).rounded()))
            outputOffset = Double(alphaFrameOffset)/outputFPS + 0.5/outputFPS - 0.000001
        }
    }
    func image(_ time: Double) -> CIImage? {
        let threshold = time + outputOffset
        while let sample = next, CMSampleBufferGetPresentationTimeStamp(sample).seconds <= threshold {
            current = CMSampleBufferGetImageBuffer(sample)
            next = output.copyNextSampleBuffer()
        }
        if current == nil, let sample = next {
            current = CMSampleBufferGetImageBuffer(sample)
            next = output.copyNextSampleBuffer()
        }
        return current.map { straightAlpha ? CIImage(cvPixelBuffer: $0).premultiplyingAlpha() : CIImage(cvPixelBuffer: $0) }
    }
}

let args = CommandLine.arguments
if args.count != 3 { fail("Usage: gpu_render project.json output.mp4") }
let start = Date()
let project = try JSONDecoder().decode(Project.self, from: Data(contentsOf: URL(fileURLWithPath: args[1])))
let outputURL = URL(fileURLWithPath: args[2])
if FileManager.default.fileExists(atPath: outputURL.path) { fail("Output already exists") }
guard let device = MTLCreateSystemDefaultDevice() else { fail("Metal unavailable") }
let context = CIContext(mtlDevice: device, options: [.cacheIntermediates: false, .workingColorSpace: NSNull()])
let writer = try AVAssetWriter(outputURL: outputURL, fileType: .mp4)
let environment = ProcessInfo.processInfo.environment
let codec = environment["GPU_CODEC"] == "hevc" ? AVVideoCodecType.hevc : AVVideoCodecType.h264
let bitrate = Int(environment["GPU_BITRATE"] ?? "4000000") ?? 4000000
let videoSettings: [String: Any] = [AVVideoCodecKey: codec, AVVideoWidthKey: project.width, AVVideoHeightKey: project.height,
 AVVideoColorPropertiesKey: [AVVideoColorPrimariesKey: AVVideoColorPrimaries_ITU_R_709_2,
                           AVVideoTransferFunctionKey: AVVideoTransferFunction_ITU_R_709_2,
                           AVVideoYCbCrMatrixKey: AVVideoYCbCrMatrix_ITU_R_709_2],
 AVVideoCompressionPropertiesKey: [AVVideoAverageBitRateKey: bitrate, AVVideoExpectedSourceFrameRateKey: Int(project.fps), AVVideoMaxKeyFrameIntervalKey: Int(project.fps)*2,
  // the Mac's one hardware encoder held a frame twice as long as its drawing: speed first made a 2-minute chunk 31%
  // faster for a structural similarity 0.2 dB lower at the same bitrate (25 November 2026)
  "PrioritizeEncodingSpeedOverQuality": true]]
let input = AVAssetWriterInput(mediaType: .video, outputSettings: videoSettings); input.expectsMediaDataInRealTime = false
let attrs: [String: Any] = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA, kCVPixelBufferWidthKey as String: project.width,
 kCVPixelBufferHeightKey as String: project.height, kCVPixelBufferMetalCompatibilityKey as String: true, kCVPixelBufferIOSurfacePropertiesKey as String: [:]]
let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: attrs)
guard writer.canAdd(input) else { fail("Cannot add output video") }; writer.add(input)
guard writer.startWriting() else { fail("Writer start failed: \(String(describing:writer.error))") }; writer.startSession(atSourceTime: .zero)
let bounds = CGRect(x: 0,y: 0,width: project.width,height: project.height)
let deviceColorSpace = CGColorSpaceCreateDeviceRGB()
var imageCache: [String: CIImage] = [:]
var frameNumber: Int64 = 0
// A scene's videos are opened (seek, decode up to the first frame: about 0.15 s each) on another thread while the scene
// before it is drawn; opening them in turn left the GPU idle some 15 s in a 24-minute film (25 November 2026).
final class OpenedVideos {
    let ready = DispatchSemaphore(value: 0)
    var readers: [Int: SequentialVideo] = [:]
    var error: Error?
}
let opening = DispatchQueue(label: "gpu-render.open-videos")
func openVideos(_ scene: Scene) -> OpenedVideos {
    let opened = OpenedVideos()
    opening.async {
        do {
            for (index,layer) in scene.layers.enumerated() where layer.kind == "video" {
                opened.readers[index] = try SequentialVideo(layer.source,layer.trim_start,scene.end-scene.start,Double(project.fps))
            }
        } catch { opened.error = error }
        opened.ready.signal()
    }
    return opened
}
// The GPU draws a frame while the main thread reads the videos and builds the next one, and a second thread hands each
// finished frame to the encoder in order: one frame after another left the GPU waiting for the processor and the
// processor for the GPU. Without dithering the destination gets exactly the pixels context.render drew.
let encoding = DispatchQueue(label: "gpu-render.encode")
let inFlight = DispatchSemaphore(value: 3)
func draw(_ composite: CIImage, _ buffer: CVPixelBuffer, _ time: Int64) {
    inFlight.wait()
    let destination = CIRenderDestination(pixelBuffer: buffer)
    destination.colorSpace = deviceColorSpace
    destination.isDithered = false
    let task: CIRenderTask
    do { task = try context.startTask(toRender: composite, from: bounds, to: destination, at: .zero) }
    catch { fail("Cannot draw a frame: \(error)") }
    encoding.async {
        do { _ = try task.waitUntilCompleted() } catch { fail("GPU frame failed: \(error)") }
        while !input.isReadyForMoreMediaData {
            if writer.status == .failed || writer.status == .cancelled { fail("Video writer stopped: \(String(describing:writer.error))") }
            Thread.sleep(forTimeInterval:0.001)
        }
        guard adaptor.append(buffer,withPresentationTime:CMTime(value:time,timescale:project.fps)) else { fail("Frame write failed: \(String(describing:writer.error))") }
        inFlight.signal()
    }
}
var nextVideos = project.scenes.first.map(openVideos)
for (sceneIndex, scene) in project.scenes.enumerated() {
    guard let opened = nextVideos else { break }
    opened.ready.wait()
    if let error = opened.error { throw error }
    let readers = opened.readers
    nextVideos = sceneIndex + 1 < project.scenes.count ? openVideos(project.scenes[sceneIndex + 1]) : nil
    let frameCount = Int(((scene.end-scene.start)*Double(project.fps)).rounded())
    // A frame group fading in or out is composited first and faded as one picture, at its top layer's place
    // (user, 22 November 2026: «перехід використовує групи, а не кожен слой»).
    var groupTop: [String: Int] = [:]
    for (index,layer) in scene.layers.enumerated() { if let g=layer.group { groupTop[g]=index } }
    for local in 0..<frameCount {
        autoreleasepool {
            guard let pool=adaptor.pixelBufferPool else { fail("Missing output buffers") }
            var buffer: CVPixelBuffer?
            guard CVPixelBufferPoolCreatePixelBuffer(nil,pool,&buffer)==kCVReturnSuccess, let buffer else { fail("Cannot allocate output frame") }
            var composite=CIImage(color:color(scene.color)).cropped(to:bounds)
            var groups: [String: CIImage] = [:]
            var groupFade: [String: Double] = [:]
            func flush(_ index: Int) {
                for (g,top) in groupTop where top==index {
                    guard let picture=groups[g] else { continue }
                    let fade=groupFade[g] ?? 1
                    if fade<=0.000001 { continue }
                    composite=(fade<0.999999 ? picture.applyingFilter("CIColorMatrix",parameters:["inputAVector":CIVector(x:0,y:0,z:0,w:fade)]) : picture).composited(over:composite)
                }
            }
            for (index,layer) in scene.layers.enumerated() {
                defer { flush(index) }
                let n=local-layer.first
                if n<0 || n>=layer.frames.count { continue }
                let f=layer.frames[n]; if f.count<4 { continue }
                var alpha=f[3]
                if layer.kind == "video", let reader=readers[index], let values=layer.alphaFrames, !values.isEmpty {
                    alpha=values[min(values.count-1,max(0,n+reader.alphaFrameOffset))]
                }
                if alpha<=0.000001 { continue }
                let original: CIImage?
                if layer.kind == "gradient" {
                    guard let config=layer.gradient else { fail("Gradient configuration missing") }
                    original=gradientImage(config,layer.trim_start+Double(local)/Double(project.fps))
                }
                else if layer.kind == "video" { original=readers[index]?.image(layer.trim_start+Double(local)/Double(project.fps)) }
                else {
                    if imageCache[layer.source] == nil { imageCache[layer.source]=CIImage(contentsOf: URL(fileURLWithPath:layer.source)) }
                    original=imageCache[layer.source]
                }
                guard var image=original else { fail("Cannot read a visual source: \(URL(fileURLWithPath:layer.source).lastPathComponent)") }
                let extent=image.extent
                if extent.width<=0 || extent.height<=0 { continue }
                let drawWidth=layer.width*f[2],drawHeight=layer.height*f[2]
                if drawWidth<=0 || drawHeight<=0 { continue }
                image=image.transformed(by:CGAffineTransform(translationX:-extent.origin.x,y:-extent.origin.y))
                image=image.transformed(by:CGAffineTransform(scaleX:drawWidth/extent.width,y:drawHeight/extent.height))
                image=image.transformed(by:CGAffineTransform(translationX:f[0],y:Double(project.height)-f[1]-drawHeight))
                if layer.kind == "gradient" { image=image.cropped(to:CGRect(x:f[0],y:Double(project.height)-f[1]-drawHeight,width:drawWidth,height:drawHeight)) }
                if alpha<0.999999 { image=image.applyingFilter("CIColorMatrix",parameters:["inputAVector":CIVector(x:0,y:0,z:0,w:alpha)]) }
                if let g=layer.group {
                    if groupFade[g]==nil, let values=layer.groupAlpha, !values.isEmpty { groupFade[g]=values[min(values.count-1,max(0,n))] }
                    groups[g]=image.composited(over:groups[g] ?? CIImage.empty())
                    continue
                }
                composite=image.composited(over:composite)
            }
            draw(composite,buffer,frameNumber)
            frameNumber += 1
        }
    }
    encoding.sync {}   // the scene's video frames stay readable until its last frame is drawn
    for reader in readers.values { reader.reader.cancelReading() }
    // Keep long projects from retaining every picture ever used.
    if imageCache.count > 128 { imageCache.removeAll(keepingCapacity:true) }
    print("scene \(sceneIndex+1)/\(project.scenes.count) frames=\(frameNumber)")
    fflush(stdout)
}
encoding.sync {}
input.markAsFinished();let done=DispatchSemaphore(value:0);writer.finishWriting { done.signal() };done.wait()
guard writer.status == .completed else { fail("Video writer failed: \(String(describing:writer.error))") }
print("GPU device=\(device.name) frames=\(frameNumber) seconds=\(String(format:"%.2f",Date().timeIntervalSince(start)))")
