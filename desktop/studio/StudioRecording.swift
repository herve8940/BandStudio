import Foundation
import AVFoundation
import AudioToolbox
import CoreAudio

struct CaptureChannel: Codable {var input:Int;var name:String}
struct CaptureSettings: Codable {
    var deviceUID=""
    var channels:[CaptureChannel]=[]
    var mode="overdub"
    var latencyMS=0.0
    var punchStart=0.0
    var punchEnd=0.0
    var preRoll=2.0
    func validate() throws {
        guard ["live","overdub","punch"].contains(mode),deviceUID.count<512,
              latencyMS.isFinite,(-2000...2000).contains(latencyMS),preRoll.isFinite,(0...30).contains(preRoll),
              punchStart.isFinite,punchEnd.isFinite,punchStart>=0,punchEnd>=0,punchEnd<=43200,
              channels.count<=32,Set(channels.map(\.input)).count==channels.count,
              channels.allSatisfy({(1...32).contains($0.input) && !$0.name.trimmingCharacters(in:.whitespaces).isEmpty && $0.name.count<=120}) else {throw StudioError("Configuration d’enregistrement invalide.")}
    }
}

struct CaptureDevice {
    var id:AudioDeviceID;var uid:String;var name:String;var channels:Int;var rate:Double
    var json:[String:Any]{["uid":uid,"name":name,"channels":channels,"rate":rate]}
}
func captureDevices()->[CaptureDevice] {
    var address=AudioObjectPropertyAddress(mSelector:kAudioHardwarePropertyDevices,mScope:kAudioObjectPropertyScopeGlobal,mElement:kAudioObjectPropertyElementMain)
    var size:UInt32=0
    guard AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject),&address,0,nil,&size)==noErr else{return []}
    var ids=[AudioDeviceID](repeating:0,count:Int(size)/MemoryLayout<AudioDeviceID>.size)
    guard AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject),&address,0,nil,&size,&ids)==noErr else{return []}
    func string(_ id:AudioDeviceID,_ selector:AudioObjectPropertySelector)->String {
        var a=AudioObjectPropertyAddress(mSelector:selector,mScope:kAudioObjectPropertyScopeGlobal,mElement:kAudioObjectPropertyElementMain)
        var value:CFString="" as CFString;var n=UInt32(MemoryLayout<CFString>.size)
        guard AudioObjectGetPropertyData(id,&a,0,nil,&n,&value)==noErr else{return ""};return value as String
    }
    return ids.compactMap{id in
        var a=AudioObjectPropertyAddress(mSelector:kAudioDevicePropertyStreamConfiguration,mScope:kAudioDevicePropertyScopeInput,mElement:kAudioObjectPropertyElementMain),n:UInt32=0
        guard AudioObjectGetPropertyDataSize(id,&a,0,nil,&n)==noErr,n>0 else{return nil}
        let memory=UnsafeMutableRawPointer.allocate(byteCount:Int(n),alignment:MemoryLayout<AudioBufferList>.alignment);defer{memory.deallocate()}
        guard AudioObjectGetPropertyData(id,&a,0,nil,&n,memory)==noErr else{return nil}
        let channels=UnsafeMutableAudioBufferListPointer(memory.assumingMemoryBound(to:AudioBufferList.self)).reduce(0){$0+Int($1.mNumberChannels)}
        guard channels>0 else{return nil}
        a.mSelector=kAudioDevicePropertyNominalSampleRate;a.mScope=kAudioObjectPropertyScopeGlobal
        var rate=0.0;n=UInt32(MemoryLayout<Double>.size);_ = AudioObjectGetPropertyData(id,&a,0,nil,&n,&rate)
        return CaptureDevice(id:id,uid:string(id,kAudioDevicePropertyDeviceUID),name:string(id,kAudioObjectPropertyName),channels:channels,rate:rate)
    }
}

// A bounded disk queue; all channels in a block have the same sample count and timestamp.
final class Recorder {
    var engine=AVAudioEngine()
    var files:[AVAudioFile]=[];var paths:[URL]=[];var selected:[CaptureChannel]=[]
    private let lock=NSLock();private let pending=DispatchSemaphore(value:16)
    private var lastError:Error?;private var firstHost:UInt64=0;private var frames:Int64=0;private var levels:[Float]=[]
    var sampleRate=0.0;var running=false
    let queue=DispatchQueue(label:"studio.recording")
    var error:Error?{get{lock.lock();defer{lock.unlock()};return lastError}set{lock.lock();lastError=newValue;lock.unlock()}}
    var firstSampleHost:UInt64{lock.lock();defer{lock.unlock()};return firstHost}
    var elapsed:Double{lock.lock();defer{lock.unlock()};return sampleRate>0 ? Double(frames)/sampleRate : 0}
    var meters:[Float]{lock.lock();defer{lock.unlock()};return levels}
    func start(root:URL,settings:CaptureSettings) throws {
        try settings.validate();guard !running else{return}
        engine=AVAudioEngine()
        let input=engine.inputNode
        if !settings.deviceUID.isEmpty {
            guard let device=captureDevices().first(where:{$0.uid==settings.deviceUID}),let unit=input.audioUnit else{throw StudioError("L’interface sélectionnée est débranchée. Choisis une entrée disponible.")}
            var id=device.id
            guard AudioUnitSetProperty(unit,kAudioOutputUnitProperty_CurrentDevice,kAudioUnitScope_Global,0,&id,UInt32(MemoryLayout<AudioDeviceID>.size))==noErr else{throw StudioError("Impossible d’ouvrir cette interface audio.")}
        }
        let format=input.outputFormat(forBus:0)
        guard format.sampleRate>0,format.channelCount>0 else{throw StudioError("Aucune entrée audio disponible.")}
        selected=settings.channels
        guard !selected.isEmpty,selected.allSatisfy({$0.input<=Int(format.channelCount)}) else {throw StudioError("Arme au moins une entrée disponible sur l’interface sélectionnée.")}
        let free=(try? root.resourceValues(forKeys:[.volumeAvailableCapacityForImportantUsageKey]).volumeAvailableCapacityForImportantUsage) ?? Int64.max
        guard free>100_000_000 else{throw StudioError("Moins de 100 Mo disponibles pour la prise.")}
        paths=[];files=[];error=nil;firstHost=0;frames=0;levels=Array(repeating:0,count:selected.count);sampleRate=format.sampleRate
        let mono=AVAudioFormat(standardFormatWithSampleRate:format.sampleRate,channels:1)!
        let take=UUID().uuidString
        try FileManager.default.createDirectory(at:root.appendingPathComponent("Audio"),withIntermediateDirectories:true)
        for channel in selected {
            let url=root.appendingPathComponent("Audio/prise-\(take)-\(channel.input).wav")
            paths.append(url);files.append(try AVAudioFile(forWriting:url,settings:[AVFormatIDKey:kAudioFormatLinearPCM,AVSampleRateKey:format.sampleRate,AVNumberOfChannelsKey:1,AVLinearPCMBitDepthKey:24,AVLinearPCMIsFloatKey:false,AVLinearPCMIsBigEndianKey:false]))
        }
        input.installTap(onBus:0,bufferSize:1024,format:format){[weak self] buffer,when in
            self?.ingest(buffer,when:when,mono:mono)
        }
        do{try engine.start();running=true}catch{input.removeTap(onBus:0);files=[];throw error}
    }
    func ingest(_ buffer:AVAudioPCMBuffer,when:AVAudioTime,mono:AVAudioFormat) {
        guard error==nil else{return}
        guard pending.wait(timeout:.now()) == .success else{error=StudioError("Le disque ne suit pas : prise arrêtée, fichiers capturés conservés.");return}
        var copies:[AVAudioPCMBuffer]=[],peaks:[Float]=[]
        for channel in selected {
            guard let b=AVAudioPCMBuffer(pcmFormat:mono,frameCapacity:buffer.frameLength),let src=buffer.floatChannelData?[channel.input-1],let dst=b.floatChannelData?[0] else{pending.signal();error=StudioError("Format d’entrée audio non pris en charge.");return}
            b.frameLength=buffer.frameLength;dst.update(from:src,count:Int(buffer.frameLength));copies.append(b)
            var peak:Float=0;for i in 0..<Int(buffer.frameLength){peak=max(peak,abs(src[i]))};peaks.append(peak)
        }
        lock.lock();if firstHost==0{firstHost=when.isHostTimeValid ? when.hostTime : mach_absolute_time()};frames += Int64(buffer.frameLength);levels=peaks;lock.unlock()
        queue.async {defer{self.pending.signal()};do{for(i,b) in copies.enumerated(){try self.files[i].write(from:b)}}catch{self.error=error}}
    }
    func stop() throws->[URL] {
        guard running else{return []};engine.inputNode.removeTap(onBus:0);engine.stop();running=false
        queue.sync{files=[]};return paths
    }
}

func cropCapture(_ source:URL,to target:URL,start:Double,end:Double) throws {
    let file=try AVAudioFile(forReading:source),rate=file.processingFormat.sampleRate
    let first=max(0,Int64((start*rate).rounded())),last=min(file.length,Int64((end*rate).rounded()))
    guard last>first else{throw StudioError("La prise ne contient pas de son dans la plage choisie.")}
    file.framePosition=first
    let output=try AVAudioFile(forWriting:target,settings:file.fileFormat.settings)
    let block=AVAudioPCMBuffer(pcmFormat:file.processingFormat,frameCapacity:16384)!
    while file.framePosition<last {try file.read(into:block,frameCount:AVAudioFrameCount(min(16384,last-file.framePosition)));guard block.frameLength>0 else{break};try output.write(from:block)}
}

extension StudioApp {
    func captureState()->[String:Any] {
        let config=(try? JSONSerialization.jsonObject(with:JSONEncoder().encode(project.capture))) ?? [:]
        return ["settings":config,"devices":captureDevices().map(\.json),"elapsed":recorder.elapsed,"meters":recorder.meters,"pending":recordPending]
    }
    func setCapture(_ args:[String:Any]) throws {
        try requireIdle();let data=try JSONSerialization.data(withJSONObject:args)
        let config=try JSONDecoder().decode(CaptureSettings.self,from:data);try config.validate()
        if config.mode=="punch"{guard config.punchEnd>config.punchStart,config.punchEnd<=project.duration else{throw StudioError("La plage de punch doit être dans le morceau.")}}
        remember();project.capture=config;try changed()
    }
    func newSession(_ name:String) throws {
        try requireIdle();let clean=safeName(name.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty ? "Répétition" : name)
        let folder=library.appendingPathComponent(clean+"-"+String(UUID().uuidString.prefix(8))+".bandstudio")
        try FileManager.default.createDirectory(at:folder.appendingPathComponent("Audio"),withIntermediateDirectories:true)
        var p=StudioProject();p.name=clean;p.capture.mode="live";p.settings.countBars=0
        try p.save(folder);try load(folder);notice="Session créée. Choisis l’interface USB et arme les entrées avant REC.";sendState()
    }
    func startRecord() throws {
        try requireIdle();guard root != nil else{throw StudioError("Crée une session ou ouvre un morceau.")}
        try project.capture.validate()
        guard !project.capture.channels.isEmpty else{throw StudioError("Choisis les entrées à enregistrer dans Prises.")}
        guard project.tracks.count+project.capture.channels.count<=128 else{throw StudioError("Le projet atteindrait la limite de 128 pistes.")}
        guard audio.rate==1,audio.pitch==0,!audio.loop else{throw StudioError("Enregistre à 100 %, sans transposition ni boucle.")}
        let settings=project.capture
        if settings.mode != "live" && project.duration<=0{throw StudioError("Ouvre un morceau pour enregistrer par-dessus.")}
        if settings.mode=="punch" {guard settings.punchEnd>settings.punchStart,settings.punchEnd<=project.duration else{throw StudioError("Plage de punch invalide.")}}
        let request=UUID().uuidString;recordRequest=request;recordPending=true;sendState()
        AVCaptureDevice.requestAccess(for:.audio){[weak self] granted in DispatchQueue.main.async {
            guard let self=self,self.recordRequest==request,self.recordPending else{return};self.recordPending=false
            if !granted{self.notice="Autorise le microphone pour BandStudio dans Réglages Système → Confidentialité et sécurité.";self.sendState();return}
            self.perform {
                guard let root=self.root else{return}
                if settings.mode=="live"{self.audio.pause();self.audio.position=0}
                if settings.mode=="punch"{self.audio.pause();self.audio.position=max(0,settings.punchStart-settings.preRoll)}
                self.recordingStart=self.audio.current();self.recordingHost=mach_absolute_time()
                try self.recorder.start(root:root,settings:settings)
                do {
                    if settings.mode != "live" && !self.audio.running {
                        let lead=settings.mode=="punch" ? 0 : self.audio.plannedCount(at:self.audio.current())
                        try self.audio.play(withCount:settings.mode != "punch")
                        self.recordingHost=self.audio.playbackHost;self.recordingStart=self.audio.position-lead
                    }
                } catch {_ = try? self.recorder.stop();throw error}
                self.notice="Prise en cours · \(self.recorder.selected.count) entrées · \(Int(self.recorder.sampleRate)) Hz · WAV 24 bits. Retour d’écoute sur la console.";self.sendState()
            }
        }}
    }
    func stopRecord() throws {
        guard recorder.running else{return};audio.pause()
        let paths=try recorder.stop();guard let root=root else{return}
        let capture=project.capture
        let hostDelta=AVAudioTime.seconds(forHostTime:recorder.firstSampleHost)-AVAudioTime.seconds(forHostTime:recordingHost)
        let offset=capture.mode=="live" ? 0 : recordingStart+hostDelta-capture.latencyMS/1000
        var additions:[Track]=[]
        for(i,raw) in paths.enumerated() {
            guard let file=try? AVAudioFile(forReading:raw),file.length>0 else{continue}
            var url=raw,at=offset
            if capture.mode=="punch" {
                let from=max(0,capture.punchStart-offset),to=min(Double(file.length)/file.processingFormat.sampleRate,capture.punchEnd-offset)
                if to<=from{continue}
                url=raw.deletingPathExtension().appendingPathExtension("punch.wav");try cropCapture(raw,to:url,start:from,end:to);at=offset+from
            }
            let(duration,peaks)=try inspectAudio(url)
            additions.append(Track(name:recorder.selected[i].name+" · prise",file:"Audio/"+url.lastPathComponent,role:"take",duration:duration,offset:at,gain:1,peaks:peaks))
        }
        remember();project.tracks += additions;project.sessionDuration=max(project.sessionDuration,additions.map{$0.offset+$0.duration}.max() ?? 0)
        try project.save(root);try audio.load(project,root:root);audio.mode="mix";audio.applyMix()
        notice=recorder.error?.localizedDescription ?? "\(additions.count) pistes enregistrées. Les captures originales sont conservées dans Audio."
        try changed()
    }
}
