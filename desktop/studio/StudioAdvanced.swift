import Foundation
import AVFoundation
import AppKit

extension StudioApp {
    func musicSettings(_ args:[String:Any]) throws {
        try requireIdle();remember()
        if args["capo"] != nil {let value=try number(args,"capo",range:0...12);guard value.rounded()==value else{throw StudioError(uiText("Position de capo entière attendue.", "The capo position must be a whole number."))};project.capo=Int(value)}
        if let key=args["key"] as? String {
            guard key.isEmpty || key.range(of:"^[A-G](#|b)?m?$",options:.regularExpression) != nil else{throw StudioError(uiText("Tonalité invalide.", "Invalid key."))}
            project.key=key
        }
        if let locked=args["gridLocked"] as? Bool {project.gridLocked=locked}
        try changed();notice=uiText("Réglages musicaux enregistrés.", "Music settings saved.");sendState()
    }

    func advancedTask(_ args:[String:Any],completion:(() throws -> Void)?=nil) throws {
        try requireIdle()
        guard let root=root,let kind=args["kind"] as? String,["smartgrid","key","lyricsimport","lyricsexport","stemsexport","master","report","portable","sheet"].contains(kind) else{throw StudioError(uiText("Ouvre d’abord un morceau.", "Open a song first."))}
        let options=args["options"] as? [String:Any] ?? [:]
        let reanalyze=options["reanalyze"] as? Bool == true
        if !reanalyze && project.analysisDone(kind) {notice=uiText("Analyse déjà disponible et résultat protégé. Les corrections et validations sont conservées.", "Analysis already exists and is protected. Your corrections and approvals have been kept.");sendState();try completion?();return}
        let optionData=try JSONSerialization.data(withJSONObject:options)
        guard optionData.count<=2_100_000,let json=String(data:optionData,encoding:.utf8) else{throw StudioError(uiText("Paramètres trop volumineux.", "Settings are too large."))}
        if kind == "smartgrid",project.gridLocked {throw StudioError(uiText("Le calage est protégé. Décoche « Protéger le calage » dans Click & cues avant de relancer.", "Timing is locked. Clear Protect timing in the metronome settings before running detection again."))}
        var input:URL?=nil
        var sourceOffset=0.0
        if ["smartgrid","key"].contains(kind) {
            guard let track=project.tracks.first(where:{$0.role=="source"}) ?? project.tracks.first(where:{!$0.role.hasPrefix("guide_")}) else{throw StudioError(uiText("Aucune piste à analyser.", "No track to analyze."))}
            input=try project.audioURL(track,root:root);sourceOffset=track.offset
        }
        let finish:(URL)throws->Void = {result in
            let object=try JSONSerialization.jsonObject(with:Data(contentsOf:result)) as? [String:Any] ?? [:]
            if kind == "smartgrid" {
                self.remember()
                self.project.applyDetectedGrid(object,offset:sourceOffset,reanalyze:reanalyze)
                self.project.analysisCompleted(kind)
                self.audio.pause();try self.reloadAudio();try self.changed();self.notice=self.project.analysisNote
            } else if kind == "key" {
                self.remember();self.project.key=object["key"] as? String ?? "";self.project.analysisCompleted(kind);try self.changed()
                let alternatives=(object["alternatives"] as? [[String:Any]] ?? []).compactMap{$0["key"] as? String}.joined(separator:", ")
                self.notice=uiText("Tonalité proposée : \(self.project.key). Autres hypothèses : \(alternatives). Tu peux la corriger dans le prompteur.", "Suggested key: \(self.project.key). Other possibilities: \(alternatives). You can change it in the teleprompter.")
            } else if kind == "lyricsimport" {
                let rows=try JSONSerialization.data(withJSONObject:object["entries"] ?? [])
                let entries=try JSONDecoder().decode([TimedText].self,from:rows)
                self.remember()
                if options["replace"] as? Bool == true {self.project.lyrics=entries}
                else {self.project.lyrics += entries.filter{e in !self.project.lyrics.contains{$0.start<e.end && $0.end>e.start}}}
                self.project.lyrics.sort{$0.start<$1.start};try self.changed();self.notice=uiText("Paroles importées. Les lignes existantes sont préservées sauf si Remplacer a été choisi.", "Lyrics imported. Existing lines were kept unless you selected Replace.")
            } else {
                self.lastExport=object["path"] as? String ?? ""
                self.notice=kind == "master" ? uiText("Mix normalisé en WAV 24 bits, avec mesures avant/après. Le projet original est conservé.", "Mix normalized to 24-bit WAV, with before and after measurements. Your original project is preserved.") : uiText("Export terminé. Utilise Afficher l’export pour le retrouver.", "Export complete. Choose Show export to find it.")
                if kind == "sheet",self.window != nil {try self.saveAndOpenSheet()}
            }
            try completion?();self.sendState()
        }
        if kind == "master" {
            audio.pause();busy=true;jobName=uiText("Préparation du mix musical", "Preparing music mix");sendState()
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

    func saveAndOpenSheet() throws {
        guard let root=root,let window=window else{return}
        let source=URL(fileURLWithPath:lastExport).resolvingSymlinksInPath()
        let exports=root.appendingPathComponent("Exports").resolvingSymlinksInPath()
        guard source.path.hasPrefix(exports.path+"/"),source.pathExtension.lowercased()=="pdf",
              FileManager.default.fileExists(atPath:source.path) else{throw StudioError(uiText("La fiche PDF est introuvable.", "PDF song sheet not found."))}
        let panel=NSSavePanel();panel.title=uiText("Enregistrer la fiche PDF", "Save PDF song sheet");panel.prompt=uiText("Enregistrer et ouvrir", "Save and open")
        panel.nameFieldStringValue=source.lastPathComponent;panel.allowedFileTypes=["pdf"];panel.canCreateDirectories=true
        panel.message=uiText("Choisis où enregistrer ta fiche. Le PDF s’ouvrira ensuite automatiquement.", "Choose where to save your sheet. The PDF will open automatically.")
        notice=uiText("PDF créé. Choisis où enregistrer ta fiche.", "PDF created. Choose where to save your sheet.")
        panel.beginSheetModal(for:window){answer in
            guard answer == .OK,let target=panel.url else{
                self.notice=uiText("Enregistrement ailleurs annulé. Le PDF reste dans le dossier du morceau.", "Save canceled. The PDF is still in the song folder.");self.sendState();return
            }
            do {
                if target.resolvingSymlinksInPath() != source {try Data(contentsOf:source).write(to:target,options:.atomic)}
                self.lastExport=target.path
                self.notice=NSWorkspace.shared.open(target) ? uiText("PDF enregistré et ouvert.", "PDF saved and opened.") : uiText("PDF enregistré. L’ouverture automatique a échoué ; utilise Afficher l’export pour le retrouver.", "PDF saved. Choose Show export to open it manually.")
            } catch {self.notice=uiText("Impossible d’enregistrer cette copie : ", "Could not save this copy: ")+error.localizedDescription+uiText(" Le PDF original reste dans le dossier du morceau.", " The original PDF is still in the song folder.")}
            self.sendState()
        }
    }
}


extension StudioApp {
    func creativeTask(_ args:[String:Any],completion:(()throws->Void)?=nil) throws {
        try requireIdle()
        guard let root=root,let kind=args["kind"] as? String,["generate","vocalsplit"].contains(kind) else{throw StudioError(uiText("Ouvre un morceau ou crée une session dans Prises.", "Open a song or create a recording project in Takes."))}
        guard project.tracks.count+2<=128 else{throw StudioError(uiText("Le projet atteint sa limite de pistes.", "This project has reached its track limit."))}
        var source:Track?=nil
        if kind=="vocalsplit" {
            source=project.tracks.first(where:{$0.role=="vocals"})
            guard source != nil else{throw StudioError(uiText("Sépare d’abord le chant du morceau avec Demucs.", "Separate the vocals with Demucs first."))}
        }
        let options=args["options"] as? [String:Any] ?? [:]
        let json=String(data:try JSONSerialization.data(withJSONObject:options),encoding:.utf8)!
        let offset=source?.offset ?? 0,sourceGain=source?.gain ?? 0.8,sourcePan=source?.pan ?? 0
        try startJob(kind,input:try source.map{try project.audioURL($0,root:root)},arguments:["--options",json]){result in
            let object=try JSONSerialization.jsonObject(with:Data(contentsOf:result)) as? [String:Any] ?? [:]
            var tracks:[Track]=[]
            for item in object["tracks"] as? [[String:String]] ?? [] {
                guard let path=item["path"],let role=item["role"],["take","vocal_lead","vocal_backing"].contains(role) else{throw StudioError(uiText("Piste créative invalide.", "Invalid generated track."))}
                let source=URL(fileURLWithPath:path).resolvingSymlinksInPath()
                guard source.path.hasPrefix(result.deletingLastPathComponent().resolvingSymlinksInPath().path+"/") else{throw StudioError(uiText("Média généré hors de son dossier.", "Generated media is outside its folder."))}
                let file="Audio/"+UUID().uuidString+"-"+role+".wav";try FileManager.default.copyItem(at:source,to:root.appendingPathComponent(file))
                let(duration,peaks)=try inspectAudio(root.appendingPathComponent(file))
                var track=Track(name:kind=="generate" ? uiText("Accompagnement généré", "Generated accompaniment") : (role=="vocal_lead" ? uiText("Chant principal", "Lead vocals") : uiText("Chœurs", "Backing vocals")),file:file,role:role,duration:duration,offset:offset,gain:kind=="generate" ? 0.8 : sourceGain,pan:sourcePan,muted:kind=="generate" ? self.project.duration>0 : (self.project.tracks.first(where:{$0.role=="vocals"})?.muted ?? false),peaks:peaks)
                if kind=="vocalsplit",let old=self.project.tracks.first(where:{$0.role==role}){track.id=old.id;track.gain=old.gain;track.pan=old.pan;track.muted=old.muted;track.solo=old.solo}
                tracks.append(track)
            }
            guard !tracks.isEmpty else{throw StudioError(uiText("Aucun résultat audio.", "No audio result."))}
            if kind=="vocalsplit",Set(tracks.map(\.role)) != Set(["vocal_lead","vocal_backing"]) {throw StudioError(uiText("Séparation du chant incomplète.", "Vocal separation incomplete."))}
            self.remember()
            if kind=="vocalsplit"{self.project.tracks.removeAll{$0.role.hasPrefix("vocal_")}}
            self.project.tracks += tracks;try self.reloadAudio();self.audio.mode="mix";self.audio.applyMix();try self.changed()
            self.notice=kind=="generate" ? uiText("Accompagnement créé. Sur un morceau existant, la nouvelle piste est muette : active son Solo pour l’écouter. Le tempo généré reste à analyser.", "Accompaniment created. In an existing song the new track starts muted. Solo it to listen. Analyze its tempo separately.") : uiText("Chant principal et chœurs proposés. La piste de chant complète reste disponible en Solo pour comparer.", "Lead and backing vocals are ready to review. Solo the full vocal track to compare.")
            self.sendState()
            if let completion=completion {try completion()}
        }
    }
}
