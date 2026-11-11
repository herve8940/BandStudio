import Foundation
import AVFoundation

struct StudioError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
    init(_ message: String) { self.message = message }
}

struct Track: Codable {
    var id = UUID().uuidString
    var name: String
    var file: String
    var role: String
    var duration: Double
    var offset = 0.0
    var gain: Float = 0.8
    var pan: Float = 0
    var muted = false
    var solo = false
    var peaks: [Float] = []
}
struct Section: Codable {
    var id = UUID().uuidString
    var start: Double
    var end: Double
    var name: String
    var locked = false
    var origin = "manual"
    var callText:String? = nil
    var announce:Bool? = nil
}
struct Cue: Codable {
    var id = UUID().uuidString
    var time: Double
    var name: String
    var callText:String? = nil
    var announce:Bool? = nil
}
struct Preparation: Codable {
    var rate=1.0
    var pitch=0.0
    var mode="mix"
    var fingerprint:String? = nil
    var validatedAt:String? = nil
}
struct StudioProject: Codable {
    var preparation:Preparation? = nil
    var sessionDuration=0.0
    var capture=CaptureSettings()
    var version = 1
    var id = UUID().uuidString
    var name = "Nouveau morceau"
    var tracks: [Track] = []
    var sections: [Section] = []
    var cues: [Cue] = []
    var bpm = 0.0
    var beats: [Double] = []
    var notes = ""
    var settings=GuideSettings()
    var guideFiles:[String:String]=[:]
    var guideKey=""
    var lyrics:[TimedText]=[]
    var chords:[TimedText]=[]
    var drumHits:[DrumHit]=[]
    var key=""
    var capo=0
    var gridLocked=false
    var downbeats:[Double]=[]
    var analysisNote=""
    var sourceURL=""
    var duration: Double { max(sessionDuration,tracks.filter{!$0.role.hasPrefix("guide_")}.map { $0.duration + $0.offset }.max() ?? 0) }

    func validate() throws {
        try settings.validate();try capture.validate()
        if let prep=preparation {
            guard prep.rate.isFinite,(0.5...1.5).contains(prep.rate),prep.pitch.isFinite,(-12...12).contains(prep.pitch),Listening.valid(prep.mode) else {throw StudioError("Réglages de préparation invalides.")}
        }
        guard sessionDuration.isFinite,(0...43200).contains(sessionDuration) else{throw StudioError("Durée de session invalide.")}
        guard (0...12).contains(capo),downbeats.allSatisfy({$0.isFinite && $0>=0 && $0<=duration+0.1}) else {throw StudioError("Repères de mesure ou capo invalides.")}
        guard version == 1, tracks.count <= 128, sections.count <= 10000,
              Set(tracks.map(\.id)).count == tracks.count else { throw StudioError("Format de projet non pris en charge.") }
        for t in tracks {
            guard t.duration.isFinite, t.duration > 0, t.duration <= 43200,
                  t.offset.isFinite, t.offset >= -120, t.gain.isFinite, (0...2).contains(t.gain),
                  t.pan.isFinite, (-1...1).contains(t.pan), t.peaks.allSatisfy({ $0.isFinite }),
                  !t.file.hasPrefix("/"), !t.file.split(separator:"/").contains("..") else {
                throw StudioError("Une piste contient des données invalides.")
            }
        }
        for s in sections {
            guard s.start.isFinite, s.end.isFinite, s.start >= 0, s.end > s.start,
                  s.end <= duration + 0.1 else { throw StudioError("Les limites d’une section sont invalides.") }
        }
        guard bpm.isFinite, bpm >= 0, bpm <= 1000,
              beats.allSatisfy({$0.isFinite && $0 >= 0 && $0 <= duration + 0.1}),
              cues.allSatisfy({$0.time.isFinite && $0.time >= 0 && $0.time <= duration}) else {
            throw StudioError("Repères musicaux invalides.")
        }
        guard guideFiles.values.allSatisfy({!$0.hasPrefix("/") && !$0.split(separator:"/").contains("..")}),
              (lyrics+chords).allSatisfy({$0.start.isFinite && $0.end.isFinite && $0.start>=0 && $0.end>$0.start && $0.end<=duration+0.1}),
              drumHits.allSatisfy({$0.time.isFinite && $0.time>=0 && $0.time<=duration && (0...127).contains($0.pitch) && (1...127).contains($0.velocity)}) else {
            throw StudioError("Guides ou annotations invalides.")
        }
    }
    func audioURL(_ track: Track, root: URL) throws -> URL {
        let url = root.appendingPathComponent(track.file).resolvingSymlinksInPath().standardizedFileURL
        let base = root.resolvingSymlinksInPath().standardizedFileURL.path + "/"
        guard url.path.hasPrefix(base) else { throw StudioError("Le fichier audio sort du projet.") }
        return url
    }
    static func load(_ root: URL) throws -> StudioProject {
        let p = try JSONDecoder().decode(StudioProject.self, from:Data(contentsOf:root.appendingPathComponent("project.json")))
        try p.validate()
        for t in p.tracks {
            let f = try AVAudioFile(forReading:p.audioURL(t,root:root))
            guard abs(Double(f.length)/f.processingFormat.sampleRate-t.duration) < 0.1 else {
                throw StudioError("Le fichier de la piste « \(t.name) » a changé.")
            }
        }
        return p
    }
    func save(_ root: URL) throws {
        try validate()
        let enc = JSONEncoder(); enc.outputFormatting = [.prettyPrinted,.sortedKeys]
        try enc.encode(self).write(to:root.appendingPathComponent("project.json"),options:.atomic)
    }
    mutating func applySections(_ suggestions: [Section]) {
        let protected = sections.filter { $0.locked || $0.origin == "manual" }
        var result = protected
        // Preserve manual regions. Trim new suggestions around protected intervals.
        for var s in suggestions {
            s.start=max(0,s.start);s.end=min(duration,s.end)
            var ranges = [(s.start,s.end)]
            for keep in protected {
                ranges = ranges.flatMap { a,b -> [(Double,Double)] in
                    if keep.end <= a || keep.start >= b { return [(a,b)] }
                    return [(a,min(b,keep.start)),(max(a,keep.end),b)].filter{$0.1-$0.0>0.01}
                }
            }
            for (a,b) in ranges where b-a > 0.01 {
                var item=s;item.id=UUID().uuidString;item.start=a;item.end=b;result.append(item)
            }
        }
        sections=result.sorted{$0.start < $1.start}
    }
}

func inspectAudio(_ url: URL) throws -> (Double,[Float]) {
    let f=try AVAudioFile(forReading:url)
    let duration=Double(f.length)/f.processingFormat.sampleRate
    guard duration > 0, duration <= 43200, f.processingFormat.channelCount <= 32 else {
        throw StudioError("Audio vide, trop long ou format non pris en charge.")
    }
    let count=720
    var peaks=[Float](repeating:0,count:count)
    guard let buffer=AVAudioPCMBuffer(pcmFormat:f.processingFormat,frameCapacity:16384) else {throw StudioError("Mémoire audio insuffisante.")}
    var position:Int64=0
    while position < f.length {
        try f.read(into:buffer)
        if buffer.frameLength == 0 { break }
        if let data=buffer.floatChannelData {
            for i in 0..<Int(buffer.frameLength) {
                let bucket=min(count-1,Int((position+Int64(i))*Int64(count)/f.length))
                for ch in 0..<Int(buffer.format.channelCount) { peaks[bucket]=max(peaks[bucket],abs(data[ch][i])) }
            }
        }
        position += Int64(buffer.frameLength)
    }
    return (duration,peaks)
}

final class StudioAudio {
    let engine=AVAudioEngine()
    let stretch=AVAudioUnitTimePitch()
    let musicMixer=AVAudioMixerNode()
    let guideMixer=AVAudioMixerNode()
    let guideStretch=AVAudioUnitTimePitch()
    let countClick=AVAudioPlayerNode()
    let countVoice=AVAudioPlayerNode()
    let startCall=AVAudioPlayerNode()
    let clock=AVAudioPlayerNode()
    var players:[AVAudioPlayerNode]=[]
    var files:[AVAudioFile]=[]
    var project=StudioProject()
    var running=false
    var playbackHost:UInt64=0
    var position=0.0
    var rate:Float=1
    var pitch:Float=0
    var mode="mix"
    var loop=false
    var loopStart=0.0
    var loopEnd=0.0
    private var startPosition=0.0
    private var firstLength=0.0
    private var scheduled=0.0
    private var preRoll=0.0
    private var loopGap=0.0
    private var countPeriod=0.5
    private var completedLoops=0
    private var speechFiles:[String:AVAudioFile]=[:]
    private let clockFormat=AVAudioFormat(standardFormatWithSampleRate:44100,channels:2)!

    init() {
        for node in [stretch,clock,musicMixer,guideMixer,guideStretch,countClick,countVoice,startCall] as [AVAudioNode] {engine.attach(node)}
        engine.connect(clock,to:musicMixer,format:clockFormat)
        engine.connect(musicMixer,to:stretch,format:clockFormat)
        engine.connect(stretch,to:engine.mainMixerNode,format:clockFormat)
        engine.connect(guideMixer,to:guideStretch,format:clockFormat)
        engine.connect(guideStretch,to:engine.mainMixerNode,format:clockFormat)
        for n in [countClick,countVoice,startCall]{engine.connect(n,to:guideMixer,format:clockFormat)}
        clock.volume=0
        engine.mainMixerNode.outputVolume=0.85
    }
    func load(_ p:StudioProject,root:URL) throws {
        let opened=try p.tracks.map { try AVAudioFile(forReading:p.audioURL($0,root:root)) }
        pause();engine.stop()
        for n in players { engine.detach(n) }
        players=[];files=opened;project=p;position=0
        speechFiles=[:]
        for (key,path) in p.guideFiles where key.hasPrefix("number:") || key.hasPrefix("call:") {
            let url=root.appendingPathComponent(path).resolvingSymlinksInPath()
            if url.path.hasPrefix(root.resolvingSymlinksInPath().path+"/"),let file=try? AVAudioFile(forReading:url),file.processingFormat.sampleRate == 44100,file.processingFormat.channelCount == 2{speechFiles[key]=file}
        }
        for (i,f) in files.enumerated() {
            let n=AVAudioPlayerNode();engine.attach(n)
            engine.connect(n,to:p.tracks[i].role.hasPrefix("guide_") ? guideMixer : musicMixer,format:f.processingFormat)
            players.append(n)
        }
        mode=p.tracks.contains{$0.role == "source"} ? "original" : "mix"
        applyMix()
    }
    func applyMix() {
        let hasSolo=project.tracks.contains{$0.solo && $0.role != "source" && !$0.role.hasPrefix("guide_")}
        let hasStems=project.tracks.contains{$0.role != "source" && $0.role != "take" && !$0.role.hasPrefix("guide_")}
        let hasDrumParts=project.tracks.contains{$0.role.hasPrefix("drum_")}
        let s=project.settings
        countClick.volume=s.countClick ? s.countGain : 0;countClick.pan=s.countPan
        countVoice.volume=s.countVoice ? s.countGain : 0;countVoice.pan=s.countPan
        startCall.volume=s.callsEnabled ? s.callsGain : 0;startCall.pan=s.callsPan
        for (i,t) in project.tracks.enumerated() where i < players.count {
            if t.role == "guide_click" {players[i].volume=s.clickEnabled ? s.clickGain : 0;players[i].pan=s.clickPan;continue}
            if t.role == "guide_voice" {players[i].volume=s.callsEnabled ? s.callsGain : 0;players[i].pan=s.callsPan;continue}
            if t.role == "guide_count" {players[i].volume=s.regionCountEnabled ? s.countGain : 0;players[i].pan=s.countPan;continue}
            var audible = !t.muted && (!hasSolo || t.solo)
            if mode == "original" {audible=t.role == "source" && !t.muted}
            else if t.role == "source" {audible=mode == "mix" && !hasStems && !t.muted && !hasSolo}
            else {audible=audible && Listening.includes(t.role,mode)}
            if t.role == "drums" && hasDrumParts && !t.solo {audible=false}
            if t.role == "vocals" && project.tracks.contains(where:{$0.role.hasPrefix("vocal_")}) && !t.solo {audible=false}
            players[i].volume=audible ? t.gain : 0;players[i].pan=t.pan
        }
    }
    func elapsed() -> Double {
        guard let node=clock.lastRenderTime,node.isHostTimeValid,node.hostTime>=playbackHost,
              let t=clock.playerTime(forNodeTime:node),t.isSampleTimeValid,t.sampleRate>0,t.sampleTime>=0 else {return 0}
        return max(0,Double(t.sampleTime)/t.sampleRate)
    }
    func current() -> Double {
        guard running else{return position}
        let e=elapsed()
        if loop && loopEnd-loopStart > 0.05 && e >= firstLength {
            let phase=(e-firstLength).truncatingRemainder(dividingBy:loopEnd-loopStart+loopGap)
            return loopStart+max(0,phase-loopGap)
        }
        return min(project.duration,startPosition+max(0,e-preRoll))
    }
    func countRemaining()->Int {
        guard running else{return 0}
        var remaining=preRoll-elapsed()
        if loop && elapsed()>=firstLength && loopGap>0 {
            let phase=(elapsed()-firstLength).truncatingRemainder(dividingBy:loopEnd-loopStart+loopGap)
            remaining=loopGap-phase
        }
        let period=project.period(at:loop && elapsed()>=firstLength ? loopStart : startPosition)
        return max(0,Int(ceil(remaining/period)))
    }
    func plannedCount(at position:Double)->Double {Double(project.settings.countBars*project.settings.beatsPerBar)*project.period(at:position)}
    private func scheduleCount(at time:Double,duration:Double,position:Double) {
        guard duration>0 else{return}
        let s=project.settings,period=project.period(at:position)
        countPeriod=period
        var callEnd=0.0
        if s.callsEnabled,(s.countBars>1 || !s.countVoice),let section=project.sections.first(where:{$0.start<=position+0.1 && $0.end>position}),section.announce != false,
           let f=speechFiles["call:"+section.id] {
            let available=duration-(s.countVoice ? Double(s.beatsPerBar)*period : 0)
            let length=min(f.length,Int64(available*44100))
            startCall.scheduleSegment(f,startingFrame:0,frameCount:UInt32(length),at:AVAudioTime(sampleTime:Int64(time*44100),atRate:44100))
            callEnd=Double(length)/44100+0.05
        }
        for beat in 0..<(s.countBars*s.beatsPerBar) {
            let at=time+Double(beat)*period
            let buffer=AVAudioPCMBuffer(pcmFormat:clockFormat,frameCapacity:1543)!
            buffer.frameLength=1543
            for i in 0..<1543 {
                let t=Double(i)/44100
                let sample=Float(sin(2*Double.pi*(beat%s.beatsPerBar==0 ? 1760 : 1100)*t)*exp(-t*130)*0.65)
                for ch in 0..<2{buffer.floatChannelData![ch][i]=sample}
            }
            countClick.scheduleBuffer(buffer,at:AVAudioTime(sampleTime:Int64(at*44100),atRate:44100))
            if beat>=(s.countBars-1)*s.beatsPerBar,Double(beat)*period>=callEnd,
               let f=speechFiles["number:"+String(beat%s.beatsPerBar+1)] {
                let length=min(f.length,Int64(period*44100*0.92))
                countVoice.scheduleSegment(f,startingFrame:0,frameCount:UInt32(length),at:AVAudioTime(sampleTime:Int64(at*44100),atRate:44100))
            }
        }
    }
    private func schedule(_ a:Double,_ b:Double,at:Double) {
        guard b > a else{return}
        for (i,t) in project.tracks.enumerated() {
            let f=files[i],sr=f.processingFormat.sampleRate
            let begin=max(a,t.offset),end=min(b,t.offset+t.duration)
            guard end > begin else{continue}
            let frame=max(0,Int64((begin-t.offset)*sr))
            let length=min(f.length-frame,Int64((end-begin)*sr))
            guard length > 0, length <= Int64(UInt32.max) else{continue}
            players[i].scheduleSegment(f,startingFrame:frame,frameCount:UInt32(length),
                at:AVAudioTime(sampleTime:Int64((at+begin-a)*sr),atRate:sr))
        }
    }
    func play(withCount:Bool=true) throws {
        guard !players.isEmpty else{return}
        if running{return}
        if position >= project.duration-0.001 {position=0}
        if loop && (position < loopStart || position >= loopEnd) {position=loopStart}
        clock.stop();for n in players+[countClick,countVoice,startCall]{n.stop()}
        startPosition=position
        let end=loop ? loopEnd : project.duration
        preRoll=withCount ? plannedCount(at:position) : 0
        loopGap=project.settings.countEveryLoop ? plannedCount(at:loopStart) : 0
        firstLength=preRoll+end-position;scheduled=firstLength;completedLoops=0
        stretch.rate=rate;stretch.pitch=pitch*100;guideStretch.rate=rate;guideStretch.pitch=0
        scheduleCount(at:0,duration:preRoll,position:position)
        schedule(position,end,at:preRoll)
        if loop { for _ in 0..<3 {scheduleCount(at:scheduled,duration:loopGap,position:loopStart);schedule(loopStart,loopEnd,at:scheduled+loopGap);scheduled += loopEnd-loopStart+loopGap} }
        let silence=AVAudioPCMBuffer(pcmFormat:clockFormat,frameCapacity:1024)!
        silence.frameLength=1024
        for c in 0..<2 {silence.floatChannelData![c].initialize(repeating:0,count:1024)}
        clock.scheduleBuffer(silence,at:nil,options:.loops)
        engine.prepare();try engine.start()
        playbackHost=mach_absolute_time()+AVAudioTime.hostTime(forSeconds:0.08)
        let time=AVAudioTime(hostTime:playbackHost)
        clock.play(at:time);for n in players+[countClick,countVoice,startCall] {n.play(at:time)}
        running=true
    }
    func pause() {
        if running {position=current()}
        running=false;clock.stop();for n in players+[countClick,countVoice,startCall]{n.stop()};engine.pause()
    }
    func seek(_ value:Double) throws {
        let was=running;pause();position=min(project.duration,max(0,value));if was{try play(withCount:project.settings.countOnSeek)}
    }
    func configureLoop(on:Bool,start:Double,end:Double) throws {
        guard !on || (start >= 0 && end <= project.duration+0.001 && end-start >= 0.05) else {throw StudioError("Choisis une boucle d’au moins 50 ms dans le morceau.")}
        let was=running;pause();loop=on;loopStart=start;loopEnd=end
        if was{try play()}
    }
    func tick() {
        guard running else{return}
        if loop {
            let size=loopEnd-loopStart
            if size > 0.05 {
                while scheduled-elapsed() < (size+loopGap)*2 {scheduleCount(at:scheduled,duration:loopGap,position:loopStart);schedule(loopStart,loopEnd,at:scheduled+loopGap);scheduled += size+loopGap}
                let lap=elapsed()<firstLength ? 0 : 1+Int((elapsed()-firstLength)/(size+loopGap))
                if lap>completedLoops {
                    completedLoops=lap;let s=project.settings
                    if s.loopStep>0,Double(rate)<s.loopMaxRate,lap%s.loopEvery==0 {rate=min(Float(s.loopMaxRate),rate+Float(s.loopStep));stretch.rate=rate;guideStretch.rate=rate}
                }
            }
        } else if current() >= project.duration-0.001 {pause();position=project.duration}
    }
    func render(to url:URL,start:Double,end:Double,includeCount:Bool=false) throws {
        pause();engine.stop()
        guard end > start else {throw StudioError("Plage d’export vide.")}
        let format=clockFormat
        try engine.enableManualRenderingMode(.offline,format:format,maximumFrameCount:4096)
        defer {engine.stop();for n in players+[countClick,countVoice,startCall]{n.stop()};engine.disableManualRenderingMode();applyMix()}
        stretch.rate=rate;stretch.pitch=pitch*100;guideStretch.rate=rate;guideStretch.pitch=0
        let lead=includeCount ? plannedCount(at:start) : 0
        scheduleCount(at:0,duration:lead,position:start);schedule(start,end,at:lead)
        if !project.settings.exportGuides {startCall.volume=0;for (i,t) in project.tracks.enumerated() where t.role.hasPrefix("guide_"){players[i].volume=0}}
        try engine.start();for n in players+[countClick,countVoice,startCall]{n.play()}
        let output=try AVAudioFile(forWriting:url,settings:format.settings)
        let buffer=AVAudioPCMBuffer(pcmFormat:format,frameCapacity:4096)!
        let target=Int64((end-start+lead)/Double(rate)*format.sampleRate)
        var written:Int64=0,stalls=0
        while written < target {
            let count=AVAudioFrameCount(min(4096,target-written))
            let status=try engine.renderOffline(count,to:buffer)
            switch status {
            case .success,.insufficientDataFromInputNode:
                if buffer.frameLength > 0 {try output.write(from:buffer);written += Int64(buffer.frameLength);stalls=0}
                else {stalls += 1}
            case .cannotDoInCurrentContext:stalls += 1
            default:throw StudioError("Le moteur audio a interrompu l’export.")
            }
            if stalls > 100 {throw StudioError("L’export audio ne progresse plus.")}
        }
    }
}


enum Listening {
    static let instruments=["drums","bass","vocals","guitar","piano","other","vocal_lead","vocal_backing","drum_kick","drum_snare","drum_toms","drum_cymbals","take"]
    static func target(_ mode:String)->String? {
        if mode=="minus" || mode=="drums" {return "drums"}
        let parts=mode.split(separator:":").map(String.init)
        return parts.count==2 && ["minus","solo"].contains(parts[0]) && instruments.contains(parts[1]) ? parts[1] : nil
    }
    static func valid(_ mode:String)->Bool {["original","mix"].contains(mode) || target(mode) != nil}
    static func matches(_ role:String,_ instrument:String)->Bool {
        role==instrument || (instrument=="drums" && role.hasPrefix("drum_")) || (instrument=="vocals" && role.hasPrefix("vocal_"))
    }
    static func includes(_ role:String,_ mode:String)->Bool {
        guard let instrument=target(mode) else{return true}
        return mode=="minus" || mode.hasPrefix("minus:") ? !matches(role,instrument) : matches(role,instrument)
    }
}
