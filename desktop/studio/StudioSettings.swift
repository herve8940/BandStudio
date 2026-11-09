import Foundation
import CryptoKit

struct GuideSettings: Codable {
    var clickEnabled=false
    var clickGain:Float=0.45
    var clickPan:Float=0
    var subdivision=1
    var beatsPerBar=4
    var firstBeat=0.0
    var gridMode="detected"
    var manualBPM=120.0
    var countBars=2
    var countClick=true
    var countVoice=true
    var countGain:Float=0.8
    var countPan:Float=0
    var countEveryLoop=false
    var countOnSeek=true
    var callsEnabled=true
    var callsGain:Float=0.9
    var callsPan:Float=0
    var leadBeats=8
    var voice="Thomas"
    var language="fr"
    var speechRate=210
    var speakCues=true
    var regionCountEnabled=true
    var regionCountBeats=4
    var exportGuides=true
    var exportCount=true
    var loopStep=0.0
    var loopEvery=4
    var loopMaxRate=1.0

    func validate() throws {
        guard [1,2,3,4].contains(subdivision),(1...12).contains(beatsPerBar),
              (0...8).contains(countBars),(0...32).contains(leadBeats),(1...12).contains(regionCountBeats),(100...360).contains(speechRate),
              ["detected","fixed"].contains(gridMode),["fr","en"].contains(language),
              firstBeat.isFinite,(-30...43200).contains(firstBeat),manualBPM.isFinite,(20...400).contains(manualBPM),
              [clickGain,countGain,callsGain].allSatisfy({$0.isFinite && (0...1.5).contains($0)}),
              [clickPan,countPan,callsPan].allSatisfy({$0.isFinite && (-1...1).contains($0)}),
              loopStep.isFinite,(0...0.25).contains(loopStep),(1...32).contains(loopEvery),
              loopMaxRate.isFinite,(0.5...1.5).contains(loopMaxRate),voice.count<=120 else {
            throw StudioError("Un réglage musical est hors limites.")
        }
    }
}

struct TimedText:Codable {
    var id=UUID().uuidString
    var start:Double
    var end:Double
    var text:String
    var manual=false
    var words:[TimedWord]?=nil
}
struct TimedWord:Codable {var start:Double;var end:Double;var text:String}
struct DrumHit:Codable {var time:Double;var pitch:Int;var velocity:Int}
struct StudioSetlist:Codable {var id=UUID().uuidString;var name:String;var paths:[String]=[]}

extension StudioProject {
    enum CodingKeys:String,CodingKey {
        case sessionDuration,capture,version,id,name,tracks,sections,cues,bpm,beats,notes,settings,guideFiles,guideKey,lyrics,chords,drumHits,key,sourceURL,capo,gridLocked,downbeats,analysisNote
    }
    init(from decoder:Decoder) throws {
        let d=try decoder.container(keyedBy:CodingKeys.self)
        sessionDuration=try d.decodeIfPresent(Double.self,forKey:.sessionDuration) ?? 0
        capture=try d.decodeIfPresent(CaptureSettings.self,forKey:.capture) ?? CaptureSettings()
        version=try d.decode(Int.self,forKey:.version);id=try d.decode(String.self,forKey:.id)
        name=try d.decode(String.self,forKey:.name);tracks=try d.decode([Track].self,forKey:.tracks)
        sections=try d.decodeIfPresent([Section].self,forKey:.sections) ?? []
        cues=try d.decodeIfPresent([Cue].self,forKey:.cues) ?? []
        bpm=try d.decodeIfPresent(Double.self,forKey:.bpm) ?? 0
        beats=try d.decodeIfPresent([Double].self,forKey:.beats) ?? []
        notes=try d.decodeIfPresent(String.self,forKey:.notes) ?? ""
        settings=try d.decodeIfPresent(GuideSettings.self,forKey:.settings) ?? GuideSettings()
        guideFiles=try d.decodeIfPresent([String:String].self,forKey:.guideFiles) ?? [:]
        guideKey=try d.decodeIfPresent(String.self,forKey:.guideKey) ?? ""
        lyrics=try d.decodeIfPresent([TimedText].self,forKey:.lyrics) ?? []
        chords=try d.decodeIfPresent([TimedText].self,forKey:.chords) ?? []
        drumHits=try d.decodeIfPresent([DrumHit].self,forKey:.drumHits) ?? []
        key=try d.decodeIfPresent(String.self,forKey:.key) ?? ""
        capo=try d.decodeIfPresent(Int.self,forKey:.capo) ?? 0
        gridLocked=try d.decodeIfPresent(Bool.self,forKey:.gridLocked) ?? !beats.isEmpty
        downbeats=try d.decodeIfPresent([Double].self,forKey:.downbeats) ?? []
        analysisNote=try d.decodeIfPresent(String.self,forKey:.analysisNote) ?? ""
        sourceURL=try d.decodeIfPresent(String.self,forKey:.sourceURL) ?? ""
    }
    func desiredGuideKey()->String {
        struct Input:Encodable{var generator=2;var settings:GuideSettings;var bpm:Double;var beats:[Double];var sections:[Section];var cues:[Cue];var duration:Double}
        let input=Input(settings:settings,bpm:bpm,beats:beats,sections:sections,cues:cues,duration:duration)
        let enc=JSONEncoder();enc.outputFormatting = .sortedKeys
        return SHA256.hash(data:(try? enc.encode(input)) ?? Data()).map{String(format:"%02x",$0)}.joined()
    }
    func period(at position:Double)->Double {
        if settings.gridMode == "detected",beats.count>1 {
            let index=beats.firstIndex(where:{$0>position}) ?? beats.count-1
            let i=max(1,index),delta=beats[i]-beats[i-1]
            if delta>0.1 && delta<3{return delta}
        }
        return 60/(settings.gridMode == "fixed" ? settings.manualBPM : (bpm>20 ? bpm : settings.manualBPM))
    }
}
