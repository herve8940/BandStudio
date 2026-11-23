import Foundation
import AppKit
import AVFoundation

if CommandLine.arguments.count>=3 && CommandLine.arguments[1]=="--timing-test" {
    do {
        let data=try Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[2]))
        let rows=try JSONSerialization.jsonObject(with:data) as! [[String:Any]]
        for row in rows {
            let p=try JSONDecoder().decode(StudioProject.self,from:JSONSerialization.data(withJSONObject:row["project"]!))
            guard let grid=p.timingGrid,grid.basis.matches(p) else{throw StudioError("Grille musicale obsolète")}
            for sample in row["samples"] as! [[String:Double]] {
                let time=sample["time"]!,coordinate=sample["coordinate"]!
                guard abs(p.musicalClock.coordinate(time)-coordinate)<1e-8,
                      abs(p.musicalClock.at(coordinate)-time)<1e-8,
                      abs(p.period(at:time)-sample["period"]!)<1e-8 else{throw StudioError("Horloge native différente de l’export")}
            }
            for expected in row["plans"] as! [[String:Any]] {
                let plan=p.countPlan(at:expected["position"] as! Double)
                let times=expected["times"] as! [Double],numbers=expected["numbers"] as! [Int]
                guard abs(plan.lead-(expected["lead"] as! Double))<1e-8,
                      abs(plan.target-(expected["target"] as! Double))<1e-8,
                      plan.events.map({$0.number})==numbers,plan.events.count==times.count,
                      zip(plan.events,times).allSatisfy({abs($0.0.time-$0.1)<1e-8}) else{throw StudioError("Décompte natif différent des guides")}
            }
            var edited=p;edited.settings.firstBeat+=0.125
            guard !grid.basis.matches(edited) else{throw StudioError("Ancienne grille réutilisée après correction")}
        }
        print("PASS native clock and count-in parity for \(rows.count) recordings");exit(0)
    } catch {fputs("FAIL: \(error.localizedDescription)\n",stderr);exit(1)}
}

func selfTest(_ directory:String) throws {
    var review=StructureProposal(schema:1,id:"test",fingerprint:"test",createdAt:0,status:"proposed",message:"Prête",
                                sources:[],anchors:0,changes:[],warnings:[],sections:[],chords:[],chordReference:nil,chordUpdate:false)
    guard !review.hasChanges,review.reviewNotice=="Aucune amélioration proposée — préparation actuelle conservée." else{throw StudioError("Proposition vide annoncée comme disponible")}
    review.chordUpdate=true
    guard review.hasChanges,review.reviewNotice.hasPrefix("Proposition disponible") else{throw StudioError("Proposition d’accords masquée")}
    review.chordUpdate=false;review.memory=StructureMemory(name:"Même enregistrement",scope:"library",sections:2,chords:0)
    guard review.hasChanges else{throw StudioError("Préparation mémorisée masquée")}
    print("PASS native empty review notice and real chord/memory proposals")
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
    let editor=StudioApp();editor.root=root;editor.runtime=root;editor.library=root;editor.project=loaded
    let guideKey=editor.project.desiredGuideKey(),sectionID=editor.project.sections[1].id
    try editor.guideMix(["key":"cuesGain","value":0.25])
    try editor.editMarker(["kind":"section","id":sectionID],review:true)
    guard editor.project.desiredGuideKey()==guideKey,editor.project.sections[1].reviewed==true else{throw StudioError("Validation ou volume provoquant un recalcul")}
    try editor.editMarker(["kind":"section","id":sectionID,"time":0.4],review:false)
    guard editor.project.sections[0].end==0.4,editor.project.sections[1].start==0.4,editor.project.sections[1].reviewed==false else{throw StudioError("Déplacement de limite incorrect")}
    let edited=try StudioProject.load(root)
    guard edited.sections[1].start==0.4,edited.settings.cuesGain==0.25,edited.analysisDone("structure") else{throw StudioError("Correction ou cache de projet perdu")}
    let journal=try FileManager.default.contentsOfDirectory(at:root.appendingPathComponent("Learning/events"),includingPropertiesForKeys:nil)
    let learningEvents=try journal.map{try JSONSerialization.jsonObject(with:Data(contentsOf:$0)) as! [String:Any]}
    let reviews=learningEvents.filter{event in
        guard let after=event["after"] as? [String:Any],let rows=after["sections"] as? [[String:Any]] else{return false}
        return rows.contains{($0["id"] as? String)==sectionID && ($0["reviewed"] as? Bool)==true}
    }
    guard reviews.count==1,journal.count==3 else{throw StudioError("Historique de corrections manquant ou pollué par le volume")}
    print("PASS native correction journal, explicit review and revoked review after move")
    try editor.runAnalysis("structure",model:"htdemucs")
    guard !editor.busy else{throw StudioError("Structure existante réanalysée")}
    editor.project.chords=[TimedText(start:0,end:0.5,text:"Am",manual:true),TimedText(start:0.5,end:2,text:"Ab")]
    let chordResult=root.appendingPathComponent("web-chords.json")
    let source="https://www.cifraclub.com/example/song/"
    var chordData:[String:Any] = ["engine":"web-reference","reference":["query":"Example Song","status":"found","sources":[["title":"Song","publisher":"Cifra Club","url":source,"chords":["C","G"],"transitions":[["C","G"]]]],"checkedAt":1.0,"message":"Calage proposé","alignment":["status":"proposed","message":"À vérifier","subdivision":2]],"segments":[["start":0.25,"end":0.75,"label":"C","sourceURL":source,"confidence":0.9],["start":1.0,"end":1.5,"label":"G","sourceURL":source,"confidence":0.7]]]
    var chordMetadata=chordData["reference"] as! [String:Any]
    chordMetadata["catalogVersion"]=2;chordMetadata["selectedURL"]=source;chordMetadata["checks"]=[["id":"cifraclub","status":"found"]];chordData["reference"]=chordMetadata
    try JSONSerialization.data(withJSONObject:chordData).write(to:chordResult)
    try editor.applyTextAnalysis("chords",result:chordResult)
    let webChords=try StudioProject.load(root)
    guard webChords.chords.map({$0.text})==["Am","G"],webChords.chords[0].manual,
          webChords.chords[1].sourceURL==source,webChords.chords[1].confidence==0.7,
          webChords.chordReference?.alignment?.subdivision==2,
          webChords.chordReference?.sources.first?.transitions==[["C","G"]],webChords.chordReference?.selectedURL==source,
          webChords.chordReference?.catalogVersion==2,webChords.chordReference?.checks?.first?.status=="found" else{throw StudioError("Source, calage ou correction manuelle d’accords perdus")}
    let providers=ChordProvider.all
    guard Set(providers.map(\.id)).count==providers.count,
          providers.contains(where:{$0.id=="topaccords" && $0.template != nil}),
          providers.contains(where:{$0.id=="ultimate" && $0.template == nil}) else{throw StudioError("Catalogue des sources d’accords invalide")}
    let providerSearch=try ChordProvider.searchURL(query:"AC/DC Highway to Hell",kind:"chords",provider:"ultimate")
    guard URLComponents(url:providerSearch,resolvingAgainstBaseURL:false)?.queryItems?.first?.value?.contains("site:ultimate-guitar.com")==true else{throw StudioError("Recherche ciblée invalide")}
    print("PASS native web chord sources, grid placement, confidence and manual protection roundtrip")
    let lyricResult=root.appendingPathComponent("lyric-review.json")
    let lyricData:[String:Any] = ["segments":[["t":0.2,"end":0.7,"text":"Listen","timingReview":true,"confidence":0.8,
                                               "words":[["t":0.2,"end":0.7,"w":"Listen","timingReview":true]]],
                                              ["t":1.0,"end":1.5,"text":"Aligned","timingReview":false,"confidence":0.8]],
                                   "lyricsReference":["status":"corrected","message":"OK","sources":["LRCLIB"],"corrected":2,"review":0,
                                                      "lineTimingCheck":["publisher":"LRCLIB","url":"https://lrclib.net/api/get/1","compared":7,"consistent":6,"offsetSeconds":0.2]]]
    try JSONSerialization.data(withJSONObject:lyricData).write(to:lyricResult)
    try editor.applyTextAnalysis("lyrics",result:lyricResult)
    let lyricsReloaded=try StudioProject.load(root)
    guard lyricsReloaded.lyrics.map({$0.timingReview})==[true,false], lyricsReloaded.lyrics.first?.words?.first?.timingReview==true,
          lyricsReloaded.lyricsReference?.lineTimingCheck?.consistent==6 else{throw StudioError("Alertes de calage des paroles perdues")}
    print("PASS native per-line lyric timing warnings survive save/reload")
    try loaded.save(root)
    print("PASS native manual boundary, validation, volumes, persistence and analysis reuse")
    var inherited=GuideSettings();inherited.firstBeat=2.635;inherited.gridMode="fixed";inherited.clickGain=1.28
    var imported=loaded;imported.settings=inherited.forNewSong()
    guard imported.settings.firstBeat==0,imported.settings.gridMode=="detected",imported.settings.clickGain==1.28 else{throw StudioError("Calage hérité d’un autre morceau")}
    let grid:[String:Any] = ["beats":[0.25,0.75,1.25,1.75],"downbeats":[0.75],"bpm":120.0,"firstBeat":0.75,"beatsPerBar":4,"gridStatus":"« 1 » calé automatiquement sur les mesures détectées"]
    imported.applyDetectedGrid(grid)
    guard imported.settings.firstBeat==0.75,imported.beats.count==4 else{throw StudioError("Calage automatique non appliqué")}
    imported.applyDetectedGrid(["beats":[0.1,0.6],"firstBeat":0.1])
    guard imported.settings.firstBeat==0.75 else{throw StudioError("Calage existant remplacé")}
    var validated=loaded;validated.preparation=Preparation(fingerprint:"approved")
    validated.applyDetectedGrid(grid)
    guard validated.beats.isEmpty else{throw StudioError("Calage validé remplacé")}
    validated.applyDetectedGrid(grid,reanalyze:true)
    guard validated.beats.count==4 else{throw StudioError("Réanalyse explicite du calage validé bloquée")}
    imported.analysisCompleted("smartgrid")
    imported.applyDetectedGrid(["beats":[0.1,0.6],"firstBeat":0.1,"bpm":113.0],reanalyze:true)
    guard imported.beats==[0.1,0.6],imported.bpm==113 else{throw StudioError("Réanalyse explicite bloquée par l’historique")}
    imported.gridLocked=true
    imported.applyDetectedGrid(grid,reanalyze:true)
    guard imported.beats==[0.1,0.6] else{throw StudioError("Réanalyse remplaçant un calage verrouillé")}
    print("PASS native import defaults, automatic downbeat and protected grids")
    var intro=loaded;intro.settings.gridMode="detected";intro.settings.firstBeat=2.68;intro.settings.countBars=2
    intro.beats=(0..<24).map{2.68+Double($0)*0.64};intro.bpm=93.75
    let count=intro.countPlan(at:0)
    guard abs(count.lead-5.0)<1e-8,abs(count.end-5.12)<1e-8,count.events.map({$0.number})==[1,2,3,4,1,2,3,4],abs(count.end-count.lead-count.target)<1e-8 else{throw StudioError("Décompte détaché de l’entrée musicale")}
    intro.beats=(0..<24).map{0.56+Double($0)*0.62};intro.settings.firstBeat=1.18;intro.bpm=60/0.62
    let pickup=intro.countPlan(at:0)
    guard abs(pickup.target-1.18)<1e-8,pickup.events.map({$0.number})==[1,2,3,4,1,2,3,4],
          abs(pickup.events.last!.time-pickup.lead-0.56)<1e-8 else{throw StudioError("Quatre absent du décompte en levée")}
    print("PASS native count-in speaks four on the pickup and joins the downbeat")
    var compound=loaded
    compound.settings.pulseUnit="dottedQuarter";compound.settings.referenceBPM=113
    compound.settings.gridMode="fixed";compound.settings.manualBPM=113;compound.settings.beatsPerBar=2
    compound.settings.firstBeat=0.98;compound.settings.countBars=1
    let compoundPeriod=90.0/113
    guard abs(compound.period(at:0)-compoundPeriod)<1e-9,
          abs(compound.countPlan(at:0).end-2*compoundPeriod)<1e-9 else{throw StudioError("Tempo ternaire mal converti")}
    let compoundCopy=try JSONDecoder().decode(StudioProject.self,from:JSONEncoder().encode(compound))
    guard compoundCopy.settings.referenceBPM==113,compoundCopy.settings.pulseUnit=="dottedQuarter",
          compoundCopy.settings.forNewSong().referenceBPM==nil,compoundCopy.settings.forNewSong().pulseUnit==nil else{throw StudioError("Unité ou référence de tempo mal conservée")}
    print("PASS native compound tempo, count-in, persistence and fresh import defaults")
    var bad=loaded;bad.tracks[0].file="../outside.wav"
    do{try bad.validate();throw StudioError("Traversée de chemin acceptée")}
    catch let error as StudioError {if error.message == "Traversée de chemin acceptée"{throw error}}
    let audio=StudioAudio();try audio.load(loaded,root:root)
    var guides=loaded
    guides.settings.clickEnabled=true;guides.settings.callsEnabled=true;guides.settings.speakCues=true;guides.settings.regionCountEnabled=true
    for role in ["guide_click","guide_voice","guide_cue","guide_count"] {
        guides.tracks.append(Track(name:role,file:"Audio/source.caf",role:role,duration:2))
    }
    try audio.load(guides,root:root)
    for index in 3..<7 {
        audio.project=guides;audio.project.tracks[index].solo=true
        for mode in ["original","mix","drums","minus"] {
            audio.mode=mode;audio.applyMix()
            guard audio.players[index].volume>0,audio.players.enumerated().allSatisfy({$0.offset==index || $0.element.volume==0}) else{throw StudioError("Solo du guide incorrect")}
        }
        audio.project.tracks[index].muted=true;audio.applyMix()
        guard audio.players.allSatisfy({$0.volume==0}) else{throw StudioError("Mute du guide solo ignoré")}
    }
    audio.project=guides;audio.project.tracks[1].solo=true;audio.mode="mix";audio.applyMix()
    guard audio.players[1].volume>0,audio.players[3...6].allSatisfy({$0.volume==0}),audio.countVoice.volume==0,audio.startCall.volume==0 else{throw StudioError("Solo musical laisse passer les guides")}
    audio.project=guides;audio.project.settings.cuesGain=0.37;audio.applyMix()
    guard abs(audio.players[5].volume-0.37)<0.001 else{throw StudioError("Volume des cues ignoré")}
    print("PASS native guide volume, mute, solo and count-in isolation")
    try audio.load(loaded,root:root)
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

func audioStartupSelfTest(_ directory:String) throws {
    let root=URL(fileURLWithPath:directory)
    try FileManager.default.createDirectory(at:root,withIntermediateDirectories:true)
    let format=AVAudioFormat(standardFormatWithSampleRate:44100,channels:2)!
    let silence=AVAudioPCMBuffer(pcmFormat:format,frameCapacity:44100)!
    silence.frameLength=44100
    for ch in 0..<2 {silence.floatChannelData![ch].initialize(repeating:0,count:44100)}
    let source=root.appendingPathComponent("silence.caf")
    try AVAudioFile(forWriting:source,settings:format.settings).write(from:silence)
    var p=StudioProject();p.settings.gridMode="fixed";p.settings.manualBPM=120
    p.settings.countBars=2;p.settings.countClick=true;p.settings.countVoice=false;p.settings.callsEnabled=false
    p.tracks=[Track(name:"Silence",file:"silence.caf",role:"source",duration:1)]
    let audio=StudioAudio();try audio.load(p,root:root)
    for pass in 0..<4 {
        let output=root.appendingPathComponent("startup-\(pass).wav")
        try audio.render(to:output,start:0,end:1,includeCount:true)
        guard audio.stretch.bypass,audio.guideStretch.bypass else{throw StudioError("Traitement inutile à vitesse neutre")}
        let file=try AVAudioFile(forReading:output)
        let buffer=AVAudioPCMBuffer(pcmFormat:file.processingFormat,frameCapacity:AVAudioFrameCount(file.length))!
        try file.read(into:buffer);let samples=buffer.floatChannelData![0]
        for beat in 0..<8 {
            let expected=beat*22050
            let onset=(expected..<expected+100).first{abs(samples[$0])>0.01}
            guard let onset=onset,onset-expected<=2 else{throw StudioError("Premier click retardé ou tronqué")}
            guard (expected+2205..<expected+20000).allSatisfy({abs(samples[$0])<0.00001}) else{throw StudioError("Click doublé ou hors grille")}
        }
    }
    audio.rate=0.75;audio.configureTimeEffects()
    guard !audio.stretch.bypass,!audio.guideStretch.bypass else{throw StudioError("Ralentissement désactivé")}
    audio.rate=1;audio.pitch=2;audio.configureTimeEffects()
    guard !audio.stretch.bypass,audio.guideStretch.bypass else{throw StudioError("Transposition des guides incorrecte")}
    print("PASS four repeated starts: eight complete clicks, sample-aligned at 120 BPM; speed and pitch preserved")
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
if CommandLine.arguments.count >= 3 && CommandLine.arguments[1] == "--audio-startup-test" {
    do {try audioStartupSelfTest(CommandLine.arguments[2]);exit(0)}catch{fputs("FAIL: \(error.localizedDescription)\n",stderr);exit(1)}
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
if CommandLine.arguments.count >= 4 && CommandLine.arguments[1] == "--refresh-guides" {
    do {
        let root=URL(fileURLWithPath:CommandLine.arguments[2]),app=StudioApp()
        app.root=root;app.library=root.deletingLastPathComponent();app.runtime=URL(fileURLWithPath:CommandLine.arguments[3])
        app.project=try StudioProject.load(root);try app.audio.load(app.project,root:root)
        try app.withGuides{}
        let deadline=Date().addingTimeInterval(900)
        while app.busy && Date()<deadline {_ = RunLoop.main.run(mode:.default,before:Date().addingTimeInterval(0.05))}
        guard !app.busy,app.project.guideKey==app.project.desiredGuideKey() else{app.job?.terminate();throw StudioError("Guides non actualisés : "+app.notice)}
        print("PASS guides ready without model inference: "+app.project.name);exit(0)
    } catch {fputs("FAIL: \(error.localizedDescription)\n",stderr);exit(1)}
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
func structureHandoffSelfTest(_ directory:String,_ engine:String) throws {
    try selfTest(directory)
    let root=URL(fileURLWithPath:directory),app=StudioApp()
    app.root=root;app.library=root.deletingLastPathComponent();app.runtime=URL(fileURLWithPath:engine)
    app.project=try StudioProject.load(root)
    app.project.settings.gridMode="fixed";app.project.settings.manualBPM=120
    app.project.settings.exportGuides=false;app.project.settings.exportCount=false
    app.project.chords=[TimedText(start:0,end:1,text:"Am",manual:true)]
    try app.audio.load(app.project,root:root);try app.changed()
    func finish() throws {
        let end=Date().addingTimeInterval(90)
        while app.busy && Date()<end {RunLoop.current.run(until:Date().addingTimeInterval(0.05))}
        if app.busy {app.job?.terminate();throw StudioError("Délai de vérification dépassé")}
    }
    let original=try JSONEncoder().encode(app.project.sections)
    try app.startJob("structureReview") {result in
        app.project.structureProposal=try JSONDecoder().decode(StructureProposal.self,from:Data(contentsOf:result))
        try app.changed(invalidate:false)
    }
    try finish()
    guard let proposal=app.project.structureProposal else {throw StudioError("Proposition native absente : "+app.notice)}
    try app.exportStructure(["proposalID":proposal.id,"reviewed":true]);try finish()
    guard !app.lastExport.isEmpty,app.project.structureProposal==nil,app.project.preparation?.fingerprint != nil else {
        throw StudioError("Validation/export natifs échoués : "+app.notice)
    }
    let sections=try JSONDecoder().decode([Section].self,from:original)
    guard app.project.sections.map(\.start)==sections.map(\.start),app.project.sections.map(\.name)==sections.map(\.name) else {
        throw StudioError("Les sections protégées ont changé")
    }
    let path=app.lastExport,text=try String(contentsOfFile:path)
    guard text.contains("NAME \"Accords\"") else {throw StudioError("Piste d’accords absente")}
    // The ordinary, pre-existing export must still accept the returned document.
    try app.exportRPP();try finish()
    guard app.lastExport != path else {throw StudioError("Export habituel après validation échoué : "+app.notice)}
    print("PASS optional native structure review, single-action export and ordinary export: "+path)
}
if CommandLine.arguments.count >= 4 && CommandLine.arguments[1] == "--structure-review-test" {
    do{try structureHandoffSelfTest(CommandLine.arguments[2],CommandLine.arguments[3]);exit(0)}catch{fputs("FAIL: \(error.localizedDescription)\n",stderr);exit(1)}
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
if CommandLine.arguments.count >= 4 && CommandLine.arguments[1] == "--prepare-all-test" {
    do {
        setbuf(stdout,nil)
        let root=URL(fileURLWithPath:CommandLine.arguments[2]),host=StudioApp()
        guard FileManager.default.fileExists(atPath:root.appendingPathComponent(".test-fixture").path) else {throw StudioError("Copie de test requise.")}
        host.root=root;host.library=root.deletingLastPathComponent();host.runtime=URL(fileURLWithPath:CommandLine.arguments[3])
        host.project=try StudioProject.load(root);try host.audio.load(host.project,root:root)
        let protected=try JSONEncoder().encode(host.project.sections.filter{$0.locked || $0.reviewed == true || $0.origin == "manual"})
        print("PLAN: "+host.analysisPlan().joined(separator:" → "))
        try host.prepareAll(["model":"htdemucs","language":"en"])
        let end=Date().addingTimeInterval(1200);var last=""
        while host.busy && Date()<end {
            if host.jobName != last {last=host.jobName;print(last)}
            RunLoop.current.run(until:Date().addingTimeInterval(0.05))
        }
        if host.busy {host.job?.terminate();throw StudioError("Délai du parcours complet dépassé")}
        guard host.project.structureProposal?.status=="prepared",host.project.structureProposal?.beforeSections != nil else {throw StudioError("Préparation finale absente : "+host.notice)}
        guard host.project.analysisDone("drumsep"),host.project.analysisDone("vocalsplit"),host.project.lyricsReference != nil else {throw StudioError("Étapes incomplètes : "+host.notice)}
        for section in try JSONDecoder().decode([Section].self,from:protected) {
            guard host.project.sections.contains(where:{$0.id==section.id && $0.start==section.start && $0.end==section.end && $0.name==section.name}) else {throw StudioError("Section protégée modifiée")}
        }
        guard host.analysisPlan().isEmpty else {throw StudioError("Calculs répétés : "+host.analysisPlan().joined(separator:", "))}
        try host.prepareAll([:]);guard !host.busy else {throw StudioError("Deuxième préparation relancée")}
        print("PASS native all-inclusive preparation, protected sections, saved result, and second click without recomputation");exit(0)
    } catch {fputs("FAIL: \(error.localizedDescription)\n",stderr);exit(1)}
}
let app=NSApplication.shared
let delegate=StudioApp();app.delegate=delegate
app.run()
