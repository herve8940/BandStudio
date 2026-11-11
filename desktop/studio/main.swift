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

func recordingSelfTest(_ directory:String) throws {
    setbuf(stdout,nil)
    try selfTest(directory)
    let root=URL(fileURLWithPath:directory),rate=48000.0,rec=Recorder()
    let layout=AVAudioChannelLayout(layoutTag:kAudioChannelLayoutTag_DiscreteInOrder | 18)!
    let format=AVAudioFormat(standardFormatWithSampleRate:rate,channelLayout:layout),mono=AVAudioFormat(standardFormatWithSampleRate:rate,channels:1)!
    rec.selected=[CaptureChannel(input:1,name:"Kick"),CaptureChannel(input:3,name:"Snare"),CaptureChannel(input:18,name:"Ambiance")];rec.sampleRate=rate
    for channel in rec.selected {
        let url=root.appendingPathComponent("Audio/input-\(channel.input).wav");rec.paths.append(url)
        rec.files.append(try AVAudioFile(forWriting:url,settings:[AVFormatIDKey:kAudioFormatLinearPCM,AVSampleRateKey:rate,AVNumberOfChannelsKey:1,AVLinearPCMBitDepthKey:24,AVLinearPCMIsFloatKey:false,AVLinearPCMIsBigEndianKey:false]))
    }
    let buffer=AVAudioPCMBuffer(pcmFormat:format,frameCapacity:4800)!;buffer.frameLength=4800
    for c in 0..<18 {for i in 0..<4800{buffer.floatChannelData![c][i]=Float(c+1)/100}}
    for i in 0..<10{rec.ingest(buffer,when:AVAudioTime(hostTime:UInt64(100+i)),mono:mono);rec.queue.sync{}}
    rec.queue.sync{rec.files=[]}
    guard rec.error==nil,rec.elapsed==1,rec.firstSampleHost==100 else{throw StudioError("Horloge d’enregistrement incorrecte")}
    for (i,url) in rec.paths.enumerated(){
        let file=try AVAudioFile(forReading:url),b=AVAudioPCMBuffer(pcmFormat:file.processingFormat,frameCapacity:48000)!;try file.read(into:b)
        guard file.length==48000,file.fileFormat.settings[AVLinearPCMBitDepthKey] as? Int==24,abs(b.floatChannelData![0][200]-Float(rec.selected[i].input)/100)<0.00001 else{throw StudioError("Routage ou format de capture incorrect")}
        let cropped=root.appendingPathComponent("crop-\(i).wav");try cropCapture(url,to:cropped,start:0.125,end:0.625)
        guard try AVAudioFile(forReading:cropped).length==24000 else{throw StudioError("Découpage de punch incorrect")}
    }
    let app=StudioApp();app.root=root;app.project=try StudioProject.load(root);try app.audio.load(app.project,root:root)
    app.project.capture.channels=rec.selected;app.project.sessionDuration=5;try app.project.save(root)
    guard try StudioProject.load(root).capture.channels[2].input==18 else{throw StudioError("Configuration de capture perdue")}
    var starts=0;let prepared=app.afterPreparation{starts += 1}
    app.recordPending=false;app.recordRequest="";app.transportGeneration += 1
    try prepared();guard starts==0 else{throw StudioError("Stop laisse démarrer une action préparée") }
    guard !app.recordPending,app.recordRequest.isEmpty else{throw StudioError("Stop ne révoque pas le départ en attente")}
    print("PASS 18-channel source, selected mono WAV24, timestamps, sample-accurate punch, settings roundtrip, pending stop")
}
if CommandLine.arguments.count >= 3 && CommandLine.arguments[1] == "--recording-test" {
    do{try recordingSelfTest(CommandLine.arguments[2]);exit(0)}catch{fputs("FAIL: \(error.localizedDescription)\n",stderr);exit(1)}
}

if CommandLine.arguments.count >= 4 && CommandLine.arguments[1] == "--creative-test" {
    do {
        setbuf(stdout,nil);try selfTest(CommandLine.arguments[2])
        let root=URL(fileURLWithPath:CommandLine.arguments[2]),app=StudioApp();app.root=root;app.runtime=URL(fileURLWithPath:CommandLine.arguments[3]);app.project=try StudioProject.load(root);try app.audio.load(app.project,root:root)
        try app.creativeTask(["kind":"generate","options":["prompt":"instrumental bass and clean guitar, slow rock groove, no drums","duration":2.0,"seed":42]])
        let deadline=ProcessInfo.processInfo.systemUptime+900
        while app.busy && ProcessInfo.processInfo.systemUptime<deadline{_ = RunLoop.main.run(mode:.default,before:Date().addingTimeInterval(0.05))}
        if app.busy {app.job?.terminate();throw StudioError("Délai de génération dépassé") }
        let restored=try StudioProject.load(root)
        guard !app.busy,let track=restored.tracks.last,track.name=="Accompagnement généré",track.muted,abs(track.duration-2)<0.01 else{throw StudioError("Création native incorrecte : \(app.notice)")}
        print("PASS native offline MusicGen worker, exact duration, imported muted track and project roundtrip")
        exit(0)
    }catch{fputs("FAIL: \(error.localizedDescription)\n",stderr);exit(1)}
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
func handoffSelfTest(_ directory:String,_ engine:String) throws {
    try selfTest(directory)
    let root=URL(fileURLWithPath:directory),app=StudioApp()
    app.root=root;app.library=root.deletingLastPathComponent();app.runtime=URL(fileURLWithPath:engine)
    app.project=try StudioProject.load(root);app.project.settings.gridMode="fixed";app.project.settings.manualBPM=120
    try app.audio.load(app.project,root:root);app.audio.rate=0.75;app.audio.pitch=2;app.audio.mode="mix";app.audio.applyMix()
    try app.savePlayback()
    func finish() throws {
        let end=Date().addingTimeInterval(90)
        while app.busy && Date()<end {RunLoop.current.run(until:Date().addingTimeInterval(0.05))}
        if app.busy {app.job?.terminate();throw StudioError("Délai de préparation dépassé")}
    }
    try app.validatePreparation();try finish()
    guard app.project.preparation?.fingerprint != nil else {throw StudioError("Validation native échouée : "+app.notice)}
    let saved=try StudioProject.load(root)
    guard saved.preparation?.rate==0.75,saved.preparation?.pitch==2 else {throw StudioError("Réglages validés non conservés")}
    try app.exportRPP();try finish()
    guard app.lastExport.hasSuffix(".rpp"),FileManager.default.fileExists(atPath:app.lastExport) else {throw StudioError("Export natif échoué : "+app.notice)}
    print("PASS validated native handoff: "+app.lastExport)
    app.project.cues.append(Cue(time:1.8,name:"Correction après validation"));try app.changed()
    guard app.project.preparation?.fingerprint==nil else {throw StudioError("Validation non révoquée après correction")}
    do {try app.exportRPP();throw StudioError("Export non validé accepté")}
    catch let error as StudioError {if error.message=="Export non validé accepté" {throw error}}
    print("PASS persisted playback settings and required revalidation after edits")
}
if CommandLine.arguments.count >= 4 && CommandLine.arguments[1] == "--handoff-test" {
    do{try handoffSelfTest(CommandLine.arguments[2],CommandLine.arguments[3]);exit(0)}catch{fputs("FAIL: \(error.localizedDescription)\n",stderr);exit(1)}
}
if CommandLine.arguments.count >= 3 && CommandLine.arguments[1] == "--transport-test" {
    do {
        try selfTest(CommandLine.arguments[2])
        let root=URL(fileURLWithPath:CommandLine.arguments[2]),audio=StudioAudio()
        var project=try StudioProject.load(root);project.settings.countBars=0
        try audio.load(project,root:root);audio.engine.mainMixerNode.outputVolume=0
        for _ in 0..<5 {
            audio.position=0;try audio.play(withCount:false)
            let deadline=Date().addingTimeInterval(0.4)
            while Date()<deadline {RunLoop.current.run(until:Date().addingTimeInterval(0.01));audio.tick()}
            let position=audio.current()
            guard audio.running,position>0.05,position<0.8 else{throw StudioError("Horloge audio incorrecte : \(position)")}
            audio.pause()
        }
        print("PASS repeated real-time play/pause, no startup jump to end");exit(0)
    } catch {fputs("FAIL: \(error.localizedDescription)\n",stderr);exit(1)}
}
let app=NSApplication.shared
let delegate=StudioApp();app.delegate=delegate
app.run()
