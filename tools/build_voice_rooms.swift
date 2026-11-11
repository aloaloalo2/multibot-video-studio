import Foundation
import AVFoundation
guard CommandLine.arguments.count == 2 else { fputs("Usage: swift tools/build_voice_rooms.swift OUTPUT_DIRECTORY\n",stderr); exit(2) }
let destination=CommandLine.arguments[1]
try FileManager.default.createDirectory(atPath:destination,withIntermediateDirectories:true)
// The doctor's office has its own deterministic furnished-room response in build_voice_office.py.
let formats:[(String,AVAudioUnitReverbPreset)]=[("studio",.smallRoom),("room",.mediumRoom),("hall",.mediumHall)]
for (name,preset) in formats {
 let engine=AVAudioEngine(), player=AVAudioPlayerNode(), reverb=AVAudioUnitReverb()
 let format=AVAudioFormat(standardFormatWithSampleRate:48000,channels:2)!
 engine.attach(player);engine.attach(reverb)
 engine.connect(player,to:reverb,format:format);engine.connect(reverb,to:engine.mainMixerNode,format:format)
 reverb.loadFactoryPreset(preset);reverb.wetDryMix=100
 let values:[AUParameterAddress:Float]
 switch name {
 case "studio": values=[1:0,2:0.005,3:0.015,4:0.001,5:0.001,6:0.98,7:0.95,8:0.15,9:0.25,10:0.2,11:0.15,12:0.7,13:0.03]
 case "room": values=[1:15,2:0.010,3:0.04,4:0.003,5:0.01,6:0.95,7:0.95,8:0.3,9:0.45,10:0.4,11:0.3,12:0.7,13:0.05]
 default: values=[1:55,2:0.015,3:0.09,4:0.01,5:0.025,6:0.97,7:0.97,8:0.4,9:0.5,10:0.45,11:0.4,12:0.7,13:0.05]
 }
 for parameter in reverb.auAudioUnit.parameterTree?.allParameters ?? [] {if let value=values[parameter.address]{parameter.value=min(parameter.maxValue,max(parameter.minValue,value))}}
 try engine.enableManualRenderingMode(.offline,format:format,maximumFrameCount:4096)
 let source=AVAudioPCMBuffer(pcmFormat:format,frameCapacity:144000)!;source.frameLength=144000
 for c in 0..<2 {source.floatChannelData![c].initialize(repeating:0,count:144000);source.floatChannelData![c][0]=1}
 player.scheduleBuffer(source,at:nil,options:[])
 try engine.start();player.play()
 let out=URL(fileURLWithPath:destination).appendingPathComponent(name+".wav")
 let file=try AVAudioFile(forWriting:out,settings:[AVFormatIDKey:kAudioFormatLinearPCM,AVSampleRateKey:48000,AVNumberOfChannelsKey:2,AVLinearPCMBitDepthKey:16,AVLinearPCMIsFloatKey:false,AVLinearPCMIsBigEndianKey:false])
 let buffer=AVAudioPCMBuffer(pcmFormat:engine.manualRenderingFormat,frameCapacity:4096)!
 while engine.manualRenderingSampleTime < 144000 {
  let frames=AVAudioFrameCount(min(4096,144000-engine.manualRenderingSampleTime))
  let status=try engine.renderOffline(frames,to:buffer)
  if status == .success {try file.write(from:buffer)}
  else if status == .error {throw NSError(domain:"room-render",code:1)}
 }
 player.stop();engine.stop();print(name)
}
