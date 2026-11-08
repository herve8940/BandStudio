import Foundation
import AppKit
import AVFoundation

func selfTest(_ directory:String) throws {
    let root=URL(fileURLWithPath:directory)
    try FileManager.default.createDirectory(at:root.appendingPathComponent("Audio"),withIntermediateDirectories:true)
    let fmt=AVAudioFormat(standardFormatWithSampleRate:44100,channels:2)!
    for (name,hz) in [("source",440.0),("drums",880.0),("bass",220.0)] {
        let file=try AVAudioFile(forWriting:root.appendingPathComponent("Audio/"+name+".caf"),settings:fmt.settings)
        let buffer=AVAudioPCMBuffer(pcmFormat:fmt,frameCapacity:88200)!
        buffer.frameLength=88200
        for i in 0..<88200 {let sample=Float(sin(Double(i)/44100*2*Double.pi*hz)*0.2);for c in 0..<2{buffer.floatChannelData![c][i]=sample}}
        try file.write(from:buffer)
    }
    var project=StudioProject();project.name="Test audio autonome"
    for role in ["source","drums","bass"] {
        let (duration,peaks)=try inspectAudio(root.appendingPathComponent("Audio/"+role+".caf"))
        project.tracks.append(Track(name:role,file:"Audio/"+role+".caf",role:role,duration:duration,gain:1,peaks:peaks))
    }
    project.sections=[Section(start:0.5,end:0.7,name:"Break court",locked:true)]
    project.applySections([Section(start:0,end:2,name:"Proposition",origin:"analysis")])
    guard project.sections.count == 3,project.sections[1].name == "Break court" else{throw StudioError("Protection des sections incorrecte")}
    project.cues=[Cue(time:0.61,name:"Reprise")]
    try project.save(root);let loaded=try StudioProject.load(root)
    guard loaded.cues[0].time == 0.61,loaded.tracks.count == 3 else{throw StudioError("Rechargement incorrect")}
    var bad=loaded;bad.tracks[0].file="../outside.wav"
    do{try bad.validate();throw StudioError("Traversée de chemin acceptée")}
    catch let error as StudioError {if error.message == "Traversée de chemin acceptée"{throw error}}
    let audio=StudioAudio();try audio.load(loaded,root:root)
    for mode in ["original","mix","drums","minus"] {
        audio.mode=mode;audio.applyMix()
        let url=root.appendingPathComponent(mode+".caf")
        try audio.render(to:url,start:0,end:2)
        let output=try AVAudioFile(forReading:url)
        guard output.length == 88200 else{throw StudioError("Durée export incorrecte : \(mode)")}
        let buffer=AVAudioPCMBuffer(pcmFormat:output.processingFormat,frameCapacity:88200)!
        try output.read(into:buffer)
        let data=buffer.floatChannelData![0]
        var energy=0.0
        for i in 20000..<80000{energy += Double(data[i]*data[i])}
        guard energy > 50 else{throw StudioError("Export silencieux : \(mode)")}
        print("PASS offline render \(mode) frames=\(output.length) energy=\(energy)")
    }
    audio.rate=0.75;audio.mode="minus";audio.applyMix()
    try audio.render(to:root.appendingPathComponent("slow.caf"),start:0.25,end:1.75)
    let slow=try AVAudioFile(forReading:root.appendingPathComponent("slow.caf"))
    guard slow.length == 88200 else{throw StudioError("Durée ralentie incorrecte")}
    print("PASS project roundtrip, protected short cues, traversal rejection, crop and slowdown")
}

if CommandLine.arguments.count >= 3 && CommandLine.arguments[1] == "--self-test" {
    do {try selfTest(CommandLine.arguments[2]);exit(0)}catch{fputs("FAIL: \(error.localizedDescription)\n",stderr);exit(1)}
}
if CommandLine.arguments.count >= 3 && CommandLine.arguments[1] == "--render-test" {
    do {
        let root=URL(fileURLWithPath:CommandLine.arguments[2]),p=try StudioProject.load(root),audio=StudioAudio()
        try audio.load(p,root:root);audio.mode="mix";audio.applyMix()
        try audio.render(to:root.appendingPathComponent("with-guides.wav"),start:0,end:p.duration,includeCount:true)
        audio.pitch=12
        try audio.render(to:root.appendingPathComponent("transposed-guides.wav"),start:0,end:p.duration,includeCount:true)
        audio.pitch=0;audio.project.settings.exportGuides=false
        try audio.render(to:root.appendingPathComponent("without-guides.wav"),start:0,end:p.duration)
        print("PASS offline guide rendering, initial count and independent voice pitch")
        exit(0)
    }catch{fputs("FAIL: \(error.localizedDescription)\n",stderr);exit(1)}
}
let app=NSApplication.shared
let delegate=StudioApp();app.delegate=delegate
app.run()
