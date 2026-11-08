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

func advancedSelfTest(_ directory:String,_ engine:String) throws {
    try selfTest(directory)
    let root=URL(fileURLWithPath:directory),app=StudioApp()
    app.root=root;app.library=root.deletingLastPathComponent();app.runtime=URL(fileURLWithPath:engine)
    app.project=try StudioProject.load(root);app.project.bpm=120
    try app.audio.load(app.project,root:root);app.audio.mode="mix";app.audio.applyMix()
    try app.musicSettings(["capo":2.0,"key":"D","gridLocked":true])
    guard try StudioProject.load(root).capo == 2 else{throw StudioError("Réglages musicaux non enregistrés")}
    try app.annotation(["kind":"lyrics","start":0.2,"end":1.8,"text":"Très bien","words":[["start":0.2,"end":0.8,"text":"Très"],["start":0.9,"end":1.8,"text":"bien"]]])
    guard try StudioProject.load(root).lyrics.first?.words?.count == 2 else{throw StudioError("Horaires des mots perdus")}
    for (kind,options) in [("lyricsimport",["text":"[00:00.00]Intro","replace":true] as [String:Any]),("lyricsexport",["format":"srt"]),("stemsexport",["format":"flac"]),("sheet",[:]),("report",[:]),("portable",[:]),("master",["lufs":-16,"peak":-1,"lra":11])] {
        try app.advancedTask(["kind":kind,"options":options])
        let deadline=Date().addingTimeInterval(90)
        while app.busy && Date()<deadline {_ = RunLoop.main.run(mode:.default,before:Date().addingTimeInterval(0.05))}
        guard !app.busy,!app.notice.contains("échoué"),!app.notice.contains("impossible") else{throw StudioError("Outil \(kind) : \(app.notice)")}
        if kind == "lyricsimport" {guard app.project.lyrics.first?.text == "Intro" else{throw StudioError("Import paroles sans effet")}}
        else {guard FileManager.default.fileExists(atPath:app.lastExport) else{throw StudioError("Export manquant : \(kind)")}}
        print("PASS native tool \(kind)")
    }
    // A decomposed drum track must replace its parent in the native audio mix.
    let baseline=StudioAudio();try baseline.load(app.project,root:root);baseline.mode="drums";baseline.applyMix()
    try baseline.render(to:root.appendingPathComponent("drums-reference.wav"),start:0,end:2)
    var parts=app.project;var child=parts.tracks.first(where:{$0.role=="drums"})!;child.id=UUID().uuidString;child.role="drum_kick";parts.tracks.append(child)
    let decomposed=StudioAudio();try decomposed.load(parts,root:root);decomposed.mode="drums";decomposed.applyMix()
    try decomposed.render(to:root.appendingPathComponent("drums-parts.wav"),start:0,end:2)
    print("PASS native tools, words, protected grid and drum-parts renders")
}

if CommandLine.arguments.count >= 4 && CommandLine.arguments[1] == "--advanced-test" {
    do{try advancedSelfTest(CommandLine.arguments[2],CommandLine.arguments[3]);exit(0)}catch{fputs("FAIL: \(error.localizedDescription)\n",stderr);exit(1)}
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
