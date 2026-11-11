import Foundation
import AVFoundation

extension StudioApp {
    func musicSettings(_ args:[String:Any]) throws {
        try requireIdle();remember()
        if args["capo"] != nil {let value=try number(args,"capo",range:0...12);guard value.rounded()==value else{throw StudioError("Position de capo entière attendue.")};project.capo=Int(value)}
        if let key=args["key"] as? String {
            guard key.isEmpty || key.range(of:"^[A-G](#|b)?m?$",options:.regularExpression) != nil else{throw StudioError("Tonalité invalide.")}
            project.key=key
        }
        if let locked=args["gridLocked"] as? Bool {project.gridLocked=locked}
        try changed();notice="Réglages musicaux enregistrés.";sendState()
    }

    func advancedTask(_ args:[String:Any],completion:(() throws -> Void)?=nil) throws {
        try requireIdle()
        guard let root=root,let kind=args["kind"] as? String,["smartgrid","key","lyricsimport","lyricsexport","stemsexport","master","report","portable","sheet"].contains(kind) else{throw StudioError("Ouvre d’abord un morceau.")}
        let options=args["options"] as? [String:Any] ?? [:]
        let optionData=try JSONSerialization.data(withJSONObject:options)
        guard optionData.count<=2_100_000,let json=String(data:optionData,encoding:.utf8) else{throw StudioError("Paramètres trop volumineux.")}
        if kind == "smartgrid",project.gridLocked {throw StudioError("Le calage est protégé. Déverrouille-le dans Guidage avant une nouvelle analyse.")}
        var input:URL?=nil
        var sourceOffset=0.0
        if ["smartgrid","key"].contains(kind) {
            guard let track=project.tracks.first(where:{$0.role=="source"}) ?? project.tracks.first(where:{!$0.role.hasPrefix("guide_")}) else{throw StudioError("Aucune piste à analyser.")}
            input=try project.audioURL(track,root:root);sourceOffset=track.offset
        }
        let finish:(URL)throws->Void = {result in
            let object=try JSONSerialization.jsonObject(with:Data(contentsOf:result)) as? [String:Any] ?? [:]
            if kind == "smartgrid" {
                self.remember()
                self.project.beats=(object["beats"] as? [Double] ?? []).map{$0+sourceOffset}.filter{$0>=0 && $0<self.project.duration}
                self.project.downbeats=(object["downbeats"] as? [Double] ?? []).map{$0+sourceOffset}.filter{$0>=0 && $0<self.project.duration}
                self.project.bpm=object["bpm"] as? Double ?? 0
                self.project.settings.gridMode="detected"
                if let first=object["firstBeat"] as? Double,let meter=object["beatsPerBar"] as? Int,(2...12).contains(meter) {
                    self.project.settings.firstBeat=max(0,first+sourceOffset);self.project.settings.beatsPerBar=meter
                }
                self.project.analysisNote=object["gridStatus"] as? String ?? "Analyse rythmique terminée."
                self.audio.pause();try self.reloadAudio();try self.changed();self.notice=self.project.analysisNote
            } else if kind == "key" {
                self.remember();self.project.key=object["key"] as? String ?? "";try self.changed()
                let alternatives=(object["alternatives"] as? [[String:Any]] ?? []).compactMap{$0["key"] as? String}.joined(separator:", ")
                self.notice="Tonalité proposée : \(self.project.key). Autres hypothèses : \(alternatives). Tu peux la corriger dans le prompteur."
            } else if kind == "lyricsimport" {
                let rows=try JSONSerialization.data(withJSONObject:object["entries"] ?? [])
                let entries=try JSONDecoder().decode([TimedText].self,from:rows)
                self.remember()
                if options["replace"] as? Bool == true {self.project.lyrics=entries}
                else {self.project.lyrics += entries.filter{e in !self.project.lyrics.contains{$0.start<e.end && $0.end>e.start}}}
                self.project.lyrics.sort{$0.start<$1.start};try self.changed();self.notice="Paroles importées. Les lignes existantes sont préservées sauf si Remplacer a été choisi."
            } else {
                self.lastExport=object["path"] as? String ?? ""
                self.notice=kind == "master" ? "Mix normalisé en WAV 24 bits, avec mesures avant/après. Le projet original est conservé." : "Export terminé. Utilise Afficher l’export pour le retrouver."
            }
            try completion?();self.sendState()
        }
        if kind == "master" {
            audio.pause();busy=true;jobName="Préparation du mix musical";sendState()
            let temp=root.appendingPathComponent("Analyses/master-"+UUID().uuidString+".wav")
            try FileManager.default.createDirectory(at:temp.deletingLastPathComponent(),withIntermediateDirectories:true)
            var copy=project;copy.settings.exportGuides=false;copy.settings.exportCount=false
            let mode=audio.mode,rate=audio.rate,pitch=audio.pitch
            DispatchQueue.global(qos:.userInitiated).async {
                do {
                    let render=StudioAudio();try render.load(copy,root:root);render.mode=mode;render.rate=rate;render.pitch=pitch;render.applyMix()
                    try render.render(to:temp,start:0,end:copy.duration,includeCount:false)
                    DispatchQueue.main.async {
                        self.busy=false;self.jobName="";self.perform{try self.startJob(kind,input:temp,arguments:["--options",json],completion:finish)}
                    }
                } catch {DispatchQueue.main.async{self.busy=false;self.jobName="";self.notice=error.localizedDescription;self.sendState()}}
            }
        } else {try startJob(kind,input:input,arguments:["--options",json],completion:finish)}
    }
}


extension StudioApp {
    func creativeTask(_ args:[String:Any]) throws {
        try requireIdle()
        guard let root=root,let kind=args["kind"] as? String,["generate","vocalsplit"].contains(kind) else{throw StudioError("Ouvre un morceau ou crée une session dans Prises.")}
        guard project.tracks.count+2<=128 else{throw StudioError("Le projet atteint sa limite de pistes.")}
        var source:Track?=nil
        if kind=="vocalsplit" {
            source=project.tracks.first(where:{$0.role=="vocals"})
            guard source != nil else{throw StudioError("Sépare d’abord le chant du morceau avec Demucs.")}
        }
        let options=args["options"] as? [String:Any] ?? [:]
        let json=String(data:try JSONSerialization.data(withJSONObject:options),encoding:.utf8)!
        let offset=source?.offset ?? 0,sourceGain=source?.gain ?? 0.8,sourcePan=source?.pan ?? 0
        try startJob(kind,input:try source.map{try project.audioURL($0,root:root)},arguments:["--options",json]){result in
            let object=try JSONSerialization.jsonObject(with:Data(contentsOf:result)) as? [String:Any] ?? [:]
            var tracks:[Track]=[]
            for item in object["tracks"] as? [[String:String]] ?? [] {
                guard let path=item["path"],let role=item["role"],["take","vocal_lead","vocal_backing"].contains(role) else{throw StudioError("Piste créative invalide.")}
                let source=URL(fileURLWithPath:path).resolvingSymlinksInPath()
                guard source.path.hasPrefix(result.deletingLastPathComponent().resolvingSymlinksInPath().path+"/") else{throw StudioError("Média généré hors de son dossier.")}
                let file="Audio/"+UUID().uuidString+"-"+role+".wav";try FileManager.default.copyItem(at:source,to:root.appendingPathComponent(file))
                let(duration,peaks)=try inspectAudio(root.appendingPathComponent(file))
                tracks.append(Track(name:kind=="generate" ? "Accompagnement généré" : (role=="vocal_lead" ? "Chant principal" : "Chœurs"),file:file,role:role,duration:duration,offset:offset,gain:kind=="generate" ? 0.8 : sourceGain,pan:sourcePan,muted:kind=="generate" && self.project.duration>0,peaks:peaks))
            }
            guard !tracks.isEmpty else{throw StudioError("Aucun résultat audio.")}
            self.remember()
            if kind=="vocalsplit"{self.project.tracks.removeAll{$0.role.hasPrefix("vocal_")}}
            self.project.tracks += tracks;try self.reloadAudio();self.audio.mode="mix";self.audio.applyMix();try self.changed()
            self.notice=kind=="generate" ? "Accompagnement créé. Sur un morceau existant, la nouvelle piste est muette : active son Solo pour l’écouter. Le tempo généré reste à analyser." : "Chant principal et chœurs proposés. La piste de chant complète reste disponible en Solo pour comparer."
            self.sendState()
        }
    }
}
