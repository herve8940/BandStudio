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
    var pulseUnit:String?=nil
    var referenceBPM:Double?=nil
    var pulseScale:Double {pulseUnit=="dottedQuarter" ? 1.5 : 1}
    var countBars=2
    var countClick=true
    var countVoice=true
    var countGain:Float=0.8
    var countPan:Float=0
    var countEveryLoop=false
    var countOnSeek=true
    var callsEnabled=true
    var callsGain:Float=0.9
    var cuesGain:Float?=nil
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

    func forNewSong()->GuideSettings {
        var value=self
        value.firstBeat=0;value.gridMode="detected";value.manualBPM=120;value.beatsPerBar=4
        value.pulseUnit=nil;value.referenceBPM=nil
        return value
    }

    func validate() throws {
        guard pulseUnit==nil || ["quarter","dottedQuarter"].contains(pulseUnit!),
              referenceBPM==nil || (referenceBPM!.isFinite && (20...400).contains(referenceBPM!)) else {
            throw StudioError(uiText("Unité de pulsation ou tempo de référence invalide.", "Invalid pulse unit or reference tempo."))
        }
        guard [1,2,3,4].contains(subdivision),(1...12).contains(beatsPerBar),
              (0...8).contains(countBars),(0...32).contains(leadBeats),(1...12).contains(regionCountBeats),(100...360).contains(speechRate),
              ["detected","fixed"].contains(gridMode),["fr","en"].contains(language),
              firstBeat.isFinite,(-30...43200).contains(firstBeat),manualBPM.isFinite,(20...400).contains(manualBPM),
              [clickGain,countGain,callsGain,cuesGain ?? callsGain].allSatisfy({$0.isFinite && (0...1.5).contains($0)}),
              [clickPan,countPan,callsPan].allSatisfy({$0.isFinite && (-1...1).contains($0)}),
              loopStep.isFinite,(0...0.25).contains(loopStep),(1...32).contains(loopEvery),
              loopMaxRate.isFinite,(0.5...1.5).contains(loopMaxRate),voice.count<=120 else {
            throw StudioError(uiText("Un réglage musical est hors limites.", "A music setting is out of range."))
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
    var sourceURL:String?=nil
    var confidence:Double?=nil
    var timingReview:Bool?=nil
}
struct TimedWord:Codable {var start:Double;var end:Double;var text:String;var timingReview:Bool?=nil}
struct ChordSequence:Codable {var kind:String;var chords:[String];var `repeat`:Int}
struct ChartSectionAnchor:Codable {var name:String;var kind:String;var words:[String]}
struct ChordSource:Codable {var title:String;var publisher:String;var url:String;var chords:[String];var transitions:[[String]]?=nil;var sections:[String:[String]]?=nil;var sectionSequences:[ChordSequence]?=nil;var sectionOrder:[String]?=nil;var chordSequence:[String]?=nil;var note:String?=nil;var anchorSchema:Int?=nil;var sectionAnchors:[ChartSectionAnchor]?=nil;var rating:Double?=nil;var ratingCount:Int?=nil}
struct ChordAlignment:Codable {var status:String;var message:String;var subdivision:Int?=nil;var tuningCents:Double?=nil;var uncertainCells:Int?=nil;var orderedSections:Int?=nil;var orderedChart:Bool?=nil;var bassEvidence:Bool?=nil;var chartTranspose:Int?=nil}
struct ChordCheck:Codable {var id:String;var status:String}
struct ChordReference:Codable {var query:String;var status:String;var sources:[ChordSource];var checkedAt:Double;var message:String;var alignment:ChordAlignment?=nil;var selectedURL:String?=nil;var catalogVersion:Int?=nil;var checks:[ChordCheck]?=nil;var selectionMode:String?=nil;var selectionReason:String?=nil;var retryAfter:Double?=nil}
struct StructureSource:Codable {var title:String;var publisher:String;var url:String;var format:String?=nil;var sectionNames:[String]?=nil}
struct StructureSourceCheck:Codable {var publisher:String;var status:String;var format:String;var url:String?=nil}
struct StructureChange:Codable {var id:String;var kind:String;var time:Double;var before:String;var after:String;var reason:String}
struct StructureMemory:Codable {var name:String;var scope:String;var sections:Int;var chords:Int}
struct StructureMemoryResult:Codable {var proposal:StructureProposal?}
struct StructureGrid:Codable {var bpm:Double;var beats:[Double];var downbeats:[Double];var gridLocked:Bool;var gridMode:String;var manualBPM:Double;var firstBeat:Double;var beatsPerBar:Int;var pulseUnit:String?}
struct ReviewPassage:Codable {var id:String;var start:Double;var end:Double;var reason:String}
struct StructureProposal:Codable {
    var sectionTimingVersion:Int?=nil
    var schema:Int;var id:String;var fingerprint:String;var createdAt:Double
    var status:String;var message:String;var sources:[StructureSource];var anchors:Int
    var changes:[StructureChange];var warnings:[String];var sections:[Section]
    var chords:[TimedText];var chordReference:ChordReference?;var chordUpdate:Bool
    var sourceChecks:[StructureSourceCheck]?=nil;var confirmedSections:Int?=nil
    var memory:StructureMemory?=nil;var restoredGrid:StructureGrid?=nil
    var reviewPassages:[ReviewPassage]?=nil;var repeatedGroups:Int?=nil;var transferredPhrases:Int?=nil
    var audioEvidence:[String]?=nil
    var beforeSections:[Section]?=nil
    var hasChanges:Bool {!changes.isEmpty || chordUpdate || memory != nil || restoredGrid != nil}
    var reviewNotice:String {hasChanges ? uiText("Proposition disponible dans Pistes & structure. Les sections actuelles sont conservées jusqu’à ta validation.", "Suggestion available in Tracks & structure. Your current sections stay in place until you approve it.") : uiText("Aucune amélioration proposée — préparation actuelle conservée.", "No improvements suggested. Current preparation retained.")}
}
struct ChordProvider:Codable {
    var id:String;var publisher:String;var domain:String;var template:String?=nil
    static let all:[ChordProvider] = {
        guard let file=Bundle.main.url(forResource:"chord-providers",withExtension:"json"),let data=try? Data(contentsOf:file),let rows=try? JSONDecoder().decode([ChordProvider].self,from:data) else{return []}
        return rows
    }()
    static func searchURL(query:String,kind:String,provider:String="") throws -> URL {
        var site=""
        if !provider.isEmpty {
            guard let entry=all.first(where:{$0.id==provider}) else{throw StudioError(uiText("Source de recherche inconnue.", "Unknown search source."))}
            site=" site:"+entry.domain
        }
        var url=URLComponents(string:"https://www.google.com/search")!
        url.queryItems=[URLQueryItem(name:"q",value:String(query.prefix(300))+(kind == "chords" ? " chords accords" : " lyrics paroles")+site)]
        guard let target=url.url else{throw StudioError(uiText("Recherche invalide.", "Invalid search."))};return target
    }
}
struct DrumHit:Codable {var time:Double;var pitch:Int;var velocity:Int}
struct StudioSetlist:Codable {var id=UUID().uuidString;var name:String;var paths:[String]=[]}
struct CountEvent {var time:Double;var end:Double;var number:Int;var spoken:Bool}
struct CountPlan {var lead:Double;var end:Double;var target:Double;var events:[CountEvent]}

struct TimingBasis:Codable {
    var beats:[Double];var downbeats:[Double];var bpm:Double;var first:Double
    var meter:Int;var mode:String;var locked:Bool;var duration:Double
    func matches(_ p:StudioProject)->Bool {
        return beats==p.beats && downbeats==p.downbeats && bpm==p.pulseBPM && first==p.settings.firstBeat && meter==p.settings.beatsPerBar && mode==p.settings.gridMode && locked==p.gridLocked && abs(duration-p.duration)<0.00001
    }
}
struct MeterChange:Codable {var time:Double;var meter:Int}
struct TimingGrid:Codable {
    var version:Int;var basis:TimingBasis;var beats:[Double];var anchor:Int
    var head:Double;var tail:Double;var detected:Bool
    var filled:Int?=nil;var phaseConfidence:Double?=nil
    func at(_ value:Double)->Double {
        if !detected || beats.count<2{return basis.first+value*60/basis.bpm}
        let index=value+Double(anchor)
        if index<0{return beats[0]+index*head}
        if index>=Double(beats.count-1){return beats.last!+(index-Double(beats.count-1))*tail}
        let i=Int(floor(index));return beats[i]+(index-Double(i))*(beats[i+1]-beats[i])
    }
    func coordinate(_ time:Double)->Double {
        if !detected || beats.count<2{return (time-basis.first)*basis.bpm/60}
        if time<beats[0]{return (time-beats[0])/head-Double(anchor)}
        if time>=beats.last!{return Double(beats.count-1-anchor)+(time-beats.last!)/tail}
        var lo=0,hi=beats.count
        while lo<hi{let mid=(lo+hi)/2;if beats[mid]<=time{lo=mid+1}else{hi=mid}}
        let i=max(0,lo-1);return Double(i-anchor)+(time-beats[i])/(beats[i+1]-beats[i])
    }
}

extension StudioProject {
    var timingBasis:TimingBasis {
        TimingBasis(beats:beats,downbeats:downbeats,bpm:pulseBPM,first:settings.firstBeat,meter:settings.beatsPerBar,mode:settings.gridMode,locked:gridLocked,duration:duration)
    }
    var musicalClock:TimingGrid {
        if let grid=timingGrid,grid.version==1,grid.basis.matches(self){return grid}
        // Until guides are ready, the editor can still display the saved detections.
        // Playback always prepares guides and their completed clock first.
        let raw=Array(Set(beats.filter{$0.isFinite && $0>=0})).sorted()
        let detected=settings.gridMode=="detected" && raw.count>1
        let anchor=detected ? (raw.indices.min{abs(raw[$0]-settings.firstBeat)<abs(raw[$1]-settings.firstBeat)} ?? 0)%settings.beatsPerBar : 0
        return TimingGrid(version:1,basis:timingBasis,beats:raw,anchor:anchor,head:detected ? raw[1]-raw[0] : 60/pulseBPM,tail:detected ? raw[raw.count-1]-raw[raw.count-2] : 60/pulseBPM,detected:detected)
    }
    func guideAudible(_ role:String)->Bool {
        let track=tracks.first{$0.role==role}
        let hasSolo=tracks.contains{$0.solo && $0.role != "source"}
        return !(track?.muted ?? false) && (!hasSolo || (track?.solo ?? false))
    }

    var pulseBPM:Double {settings.gridMode=="fixed" ? settings.manualBPM/settings.pulseScale : bpm>0 ? bpm : settings.manualBPM/settings.pulseScale}
    func countPlan(at position:Double)->CountPlan {
        let clock=musicalClock
        let change=meterChanges?.last(where:{$0.time<=position+0.000001})
        let meter=change?.meter ?? settings.beatsPerBar,n=settings.countBars*meter
        guard n>0 else{return CountPlan(lead:0,end:0,target:position,events:[])}
        let anchor=change.map{Int(round(clock.coordinate($0.time)))} ?? 0
        let at:(Int)->Double={clock.at(Double($0))}
        let target=position<=0 ? Int(ceil(clock.coordinate(0)/Double(meter)-1e-9))*meter : Int(ceil(clock.coordinate(position)-1e-9))
        // Speak the full count through the pickup, including "four" before "one".
        let lead=max(0,position-at(target-n))
        let events=(target-n..<target).map{i in CountEvent(time:at(i)-position+lead,end:at(i+1)-position+lead,number:((i-anchor)%meter+meter)%meter+1,spoken:i>=target-meter)}
        return CountPlan(lead:lead,end:at(target)-position+lead,target:at(target),events:events)
    }

    mutating func applyDetectedGrid(_ result:[String:Any],offset:Double=0,reanalyze:Bool=false) {
        guard !gridLocked, reanalyze || !analysisDone("smartgrid") else{return}
        beats=(result["beats"] as? [Double] ?? []).map{$0+offset}.filter{$0>=0 && $0<duration}
        downbeats=(result["downbeats"] as? [Double] ?? []).map{$0+offset}.filter{$0>=0 && $0<duration}
        bpm=result["bpm"] as? Double ?? 0
        meterChanges=nil
        settings.gridMode="detected"
        settings.pulseUnit=result["pulseUnit"] as? String ?? "quarter"
        settings.firstBeat=(result["firstBeat"] as? Double).map{$0+offset} ?? beats.first ?? 0
        let meter=result["beatsPerBar"] as? Int ?? 4
        settings.beatsPerBar=(2...12).contains(meter) ? meter : 4
        analysisNote=result["gridStatus"] as? String ?? uiText("« 1 » à vérifier à l’écoute · mesures non confirmées", "Check beat 1 by ear · bars unconfirmed")
    }

    enum CodingKeys:String,CodingKey {
        case sectionGridVersion,timingGrid,meterChanges
        case structureProposal,preparation,sessionDuration,capture,version,id,name,tracks,sections,cues,bpm,beats,notes,settings,guideFiles,guideKey,lyrics,lyricsReference,chords,chordReference,drumHits,key,sourceURL,capo,analysesCompleted,gridLocked,downbeats,analysisNote
    }
    init(from decoder:Decoder) throws {
        let d=try decoder.container(keyedBy:CodingKeys.self)
        sectionGridVersion=try d.decodeIfPresent(Int.self,forKey:.sectionGridVersion)
        meterChanges=try d.decodeIfPresent([MeterChange].self,forKey:.meterChanges)
        timingGrid=try d.decodeIfPresent(TimingGrid.self,forKey:.timingGrid)
        structureProposal=try d.decodeIfPresent(StructureProposal.self,forKey:.structureProposal)
        preparation=try d.decodeIfPresent(Preparation.self,forKey:.preparation)
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
        lyricsReference=try d.decodeIfPresent(LyricsReference.self,forKey:.lyricsReference)
        chords=try d.decodeIfPresent([TimedText].self,forKey:.chords) ?? []
        chordReference=try d.decodeIfPresent(ChordReference.self,forKey:.chordReference)
        drumHits=try d.decodeIfPresent([DrumHit].self,forKey:.drumHits) ?? []
        key=try d.decodeIfPresent(String.self,forKey:.key) ?? ""
        capo=try d.decodeIfPresent(Int.self,forKey:.capo) ?? 0
        analysesCompleted=try d.decodeIfPresent([String].self,forKey:.analysesCompleted) ?? []
        gridLocked=try d.decodeIfPresent(Bool.self,forKey:.gridLocked) ?? !beats.isEmpty
        downbeats=try d.decodeIfPresent([Double].self,forKey:.downbeats) ?? []
        analysisNote=try d.decodeIfPresent(String.self,forKey:.analysisNote) ?? ""
        sourceURL=try d.decodeIfPresent(String.self,forKey:.sourceURL) ?? ""
    }
    func desiredGuideKey()->String {
        struct Input:Encodable{var generator=8;var meterChanges:[MeterChange]?=nil;var settings:GuideSettings;var bpm:Double;var beats:[Double];var downbeats:[Double];var gridLocked:Bool;var sections:[Section];var cues:[Cue];var duration:Double}
        var sound=settings
        sound.referenceBPM=nil
        if sound.gridMode=="detected" {sound.pulseUnit=nil}
        sound.clickGain=1;sound.callsGain=1;sound.cuesGain=1;sound.countGain=1
        sound.clickPan=0;sound.callsPan=0;sound.countPan=0
        sound.clickEnabled=true;sound.callsEnabled=true;sound.speakCues=true
        var regions=sections;var markers=cues
        for i in regions.indices {regions[i].reviewed=nil;regions[i].locked=false;regions[i].origin=""}
        for i in markers.indices {markers[i].reviewed=nil}
        let input=Input(meterChanges:meterChanges,settings:sound,bpm:bpm,beats:beats,downbeats:downbeats,gridLocked:gridLocked,sections:regions,cues:markers,duration:duration)
        let enc=JSONEncoder();enc.outputFormatting = .sortedKeys
        return SHA256.hash(data:(try? enc.encode(input)) ?? Data()).map{String(format:"%02x",$0)}.joined()
    }
    func period(at position:Double)->Double {
        let clock=musicalClock,i=floor(clock.coordinate(position)+1e-9)
        return clock.at(i+1)-clock.at(i)
    }
}
