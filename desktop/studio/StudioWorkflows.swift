import AppKit
import AVFoundation

extension StudioApp {
    func reviewStructure(_ args:[String:Any]) throws {
        try requireIdle();audio.pause()
        let checkedRevision=revision
        try startJob("structureMemory") {result in
            guard self.revision==checkedRevision else {throw StudioError(uiText("Le morceau a changé. Relance la vérification.", "The song has changed. Run the check again."))}
            let recalled=try JSONDecoder().decode(StructureMemoryResult.self,from:Data(contentsOf:result))
            if recalled.proposal != nil {
                try self.prepareAll(args,only:["separate"]) {
                    let preparedRevision=self.revision
                    try self.startJob("structureMemory") {fresh in
                        guard self.revision==preparedRevision else {throw StudioError(uiText("Le morceau a changé. Relance la vérification.", "The song has changed. Run the check again."))}
                        guard let proposal=try JSONDecoder().decode(StructureMemoryResult.self,from:Data(contentsOf:fresh)).proposal else {throw StudioError(uiText("Le morceau a changé pendant la préparation. Relance la vérification.", "The song changed during preparation. Run the check again."))}
                        self.project.structureProposal=proposal;try self.changed(invalidate:false)
                        self.notice=uiText("Préparation du même enregistrement retrouvée. Valide la proposition pour la réutiliser.", "Found a saved preparation for this recording. Approve the suggestion to reuse it.")
                    }
                }
                return
            }
            try self.prepareAll(args,only:["separate","grid","smartgrid","structure","chords"]) {
                let checkedRevision=self.revision
                try self.startJob("structureReview") {result in
                    guard self.revision==checkedRevision else {throw StudioError(uiText("Le morceau a changé. Relance Vérifier et compléter.", "The song has changed. Run Check and complete again."))}
                    self.project.structureProposal=try JSONDecoder().decode(StructureProposal.self,from:Data(contentsOf:result))
                    try self.changed(invalidate:false)
                    self.notice=self.project.structureProposal!.reviewNotice
                }
            }
        }
    }
    func applyStructure(_ args:[String:Any]) throws {
        try requireIdle()
        guard let proposal=project.structureProposal,args["reviewed"] as? Bool == true,
              args["proposalID"] as? String == proposal.id else {throw StudioError(uiText("Valide la proposition affichée dans Pistes & structure.", "Approve the suggestion shown in Tracks & structure."))}
        audio.pause();let checkedRevision=revision
        try startJob("structureApply") {result in
            guard self.revision==checkedRevision else {throw StudioError(uiText("Le morceau a changé. Relance la vérification.", "The song has changed. Run the check again."))}
            let object=try JSONSerialization.jsonObject(with:Data(contentsOf:result)) as? [String:Any] ?? [:]
            guard let value=object["project"] else {throw StudioError(uiText("La proposition n’est pas complète.", "The suggestion is incomplete."))}
            let prepared=try JSONDecoder().decode(StudioProject.self,from:JSONSerialization.data(withJSONObject:value))
            guard prepared.id==self.project.id else {throw StudioError(uiText("La proposition appartient à un autre morceau.", "The suggestion belongs to a different song."))}
            try prepared.validate();self.remember();self.project=prepared
            try self.reloadAudio();try self.changed()
            self.notice=uiText("Proposition enregistrée dans le morceau. Annuler permet de retrouver les repères précédents.", "Suggestion saved in the song. Use Undo to restore the previous markers.")
        }
    }
    func exportStructure(_ args:[String:Any]) throws {
        try requireIdle()
        guard let proposal=project.structureProposal,args["reviewed"] as? Bool == true,
              args["proposalID"] as? String == proposal.id else {throw StudioError(uiText("Valide la proposition affichée dans Pistes & structure.", "Approve the suggestion shown in Tracks & structure."))}
        audio.pause();let checkedRevision=revision
        try startJob("structureExport") {result in
            guard self.revision==checkedRevision else {throw StudioError(uiText("Le morceau a changé pendant l’export. Relance la vérification.", "The song changed during export. Run the check again."))}
            let object=try JSONSerialization.jsonObject(with:Data(contentsOf:result)) as? [String:Any] ?? [:]
            guard let path=object["path"] as? String,let value=object["project"] else {throw StudioError(uiText("L’export de la proposition n’est pas complet.", "The suggested export is incomplete."))}
            var prepared=try JSONDecoder().decode(StudioProject.self,from:JSONSerialization.data(withJSONObject:value))
            guard prepared.id==self.project.id else {throw StudioError(uiText("L’export appartient à un autre morceau.", "The export belongs to another song."))}
            try prepared.validate()
            if prepared.settings.exportGuides {prepared.guideKey=prepared.desiredGuideKey()}
            self.remember();self.project=prepared
            try self.reloadAudio();try self.changed(invalidate:false)
            self.lastExport=path;self.notice=uiText("Proposition appliquée et projet REAPER exporté. Afficher l’export permet de le retrouver.", "Suggestion applied and REAPER project exported. Choose Show export to find it.")
        }
    }
    func snapshot(at url:URL) throws {
        var object=try JSONSerialization.jsonObject(with:JSONEncoder().encode(project)) as! [String:Any]
        object["_root"]=root?.path
        object["_library"]=library.path
        object["_mode"]=audio.mode;object["_rate"]=Double(audio.rate);object["_pitch"]=Double(audio.pitch)
        try JSONSerialization.data(withJSONObject:object,options:[.sortedKeys]).write(to:url,options:.atomic)
    }
    func startJob(_ kind:String,input:URL?=nil,arguments:[String]=[],completion:@escaping(URL) throws -> Void) throws {
        try requireIdle()
        let base=root ?? library.appendingPathComponent(".Imports")
        let folder=base.appendingPathComponent("Analyses/"+UUID().uuidString)
        try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)
        let result=folder.appendingPathComponent("result.json"),snap=folder.appendingPathComponent("project.json")
        try snapshot(at:snap)
        let environment=["generate":".venv-creative","vocalsplit":".venv-creative","structure":".venv-structure","separate":".venv-demucs","drumsep":".venv-demucs","smartgrid":".venv-demucs","lyrics":".venv-words","lyricscorrect":".venv-words","chords":".venv","drums":".venv-drums"]
        let p=Process();p.executableURL=runtime.appendingPathComponent((environment[kind] ?? ".venv")+"/bin/python")
        var safeArguments=arguments
        if let index=safeArguments.firstIndex(of:"--options"),index+1<safeArguments.count {
            let file=folder.appendingPathComponent("options.json")
            try safeArguments[index+1].write(to:file,atomically:true,encoding:.utf8)
            safeArguments[index]="--options-file";safeArguments[index+1]=file.path
        }
        p.arguments=[runtime.appendingPathComponent("worker.py").path,kind,"--output",result.path,"--engine",runtime.path,"--project",snap.path]+safeArguments
        if let input=input{p.arguments! += ["--input",input.path]}
        p.currentDirectoryURL=folder
        var env=ProcessInfo.processInfo.environment;env["PYTHONUNBUFFERED"]="1";env["PYTHONDONTWRITEBYTECODE"]="1";env["HF_HUB_OFFLINE"]="1";env["OMP_NUM_THREADS"]="4"
        env["PATH"]=runtime.appendingPathComponent("import-tools").path+":"+(env["PATH"] ?? "/usr/bin:/bin")
        p.environment=env
        let log=folder.appendingPathComponent("traitement.log");FileManager.default.createFile(atPath:log.path,contents:nil)
        let handle=try FileHandle(forWritingTo:log);p.standardOutput=handle;p.standardError=handle
        let identity=project.id
        jobKind=kind;jobIdentifier=folder.lastPathComponent;jobPlan=[];jobPlanIndex=0
        p.terminationHandler={[weak self] process in
            try? handle.close()
            DispatchQueue.main.async {
                guard let self=self else{return}
                StudioDiagnostics.shared.event("job.finish",["kind":kind,"exit":process.terminationStatus]);let cancelled=self.job == nil
                self.send(["type":"job","task":kind,"jobID":folder.lastPathComponent,"finished":!cancelled && process.terminationStatus==0,"failed":cancelled || process.terminationStatus != 0,"progress":!cancelled && process.terminationStatus==0 ? 100 : 0])
                self.busy=false;self.job=nil;self.jobName=""
                if cancelled {self.notice=uiText("Traitement annulé. Le projet est conservé.", "Task canceled. Your project has been kept.");self.sendState();return}
                guard self.project.id == identity else{self.sendState();return}
                guard process.terminationStatus == 0 else {self.notice=uiText("Le traitement a échoué : ", "Task failed: ")+self.jobDetail();self.sendState();return}
                self.perform{try completion(result);self.sendState()}
            }
        }
        StudioDiagnostics.shared.event("job.start",["kind":kind]);try p.run();job=p;busy=true;jobLog=log;jobStarted=ProcessInfo.processInfo.systemUptime;lastBroadcast=0
        let titles:[String:String]=["prepareReview":uiText("Vérification finale des sections et accords", "Final check of sections and chords"),"structureApply":uiText("Application de la proposition", "Applying suggestion"),"structureMemory":uiText("Recherche d’une préparation mémorisée", "Looking for a saved preparation"),"structureReview":uiText("Comparaison de la structure", "Structure comparison"),"structureExport":uiText("Validation et export REAPER", "REAPER review and export"),"validate":uiText("Vérification du morceau et des médias", "Checking song and media"),"generate":uiText("Création musicale locale", "Creating music locally"),"vocalsplit":uiText("Séparation chant principal et chœurs", "Separating lead and backing vocals"),"smartgrid":uiText("Détection des temps et débuts de mesure", "Detecting beats and downbeats"),"drumsep":uiText("Séparation des éléments de batterie", "Separating drum kit"),"key":uiText("Estimation de la tonalité", "Estimating key"),"lyricsimport":uiText("Import des paroles synchronisées", "Importing synced lyrics"),"lyricsexport":uiText("Export des paroles", "Exporting lyrics"),"stemsexport":uiText("Export des stems", "Exporting stems"),"master":uiText("Normalisation du mix", "Normalizing mix"),"report":uiText("Analyse des niveaux audio", "Analyzing audio levels"),"portable":uiText("Création du projet portable", "Creating portable project"),"sheet":uiText("Création de la fiche PDF", "Creating PDF song sheet"),"guides":uiText("Préparation du click, des appels et du décompte", "Preparing click, announcements and count-in"),"separate":uiText("Séparation des instruments", "Instrument separation"),"structure":uiText("Analyse de la structure", "Analyzing structure"),"grid":uiText("Détection du tempo et des temps", "Detecting tempo and beats"),"reaper":uiText("Création du projet REAPER", "Creating REAPER project"),"lyrics":uiText("Transcription et vérification des paroles", "Transcribing and checking lyrics"),"lyricscorrect":uiText("Correction des paroles et recalage vocal", "Correcting and aligning vocals"),"chords":uiText("Recherche de grille Internet", "Finding an online chord chart"),"drums":uiText("Transcription de la batterie", "Transcribing drums"),"midi":uiText("Export MIDI", "Exporting MIDI"),"decode":uiText("Conversion du fichier audio", "Converting audio file")]
        jobName=kind == "rpp" ? uiText("Import des pistes et régions REAPER", "Importing REAPER tracks and regions") : (titles[kind] ?? kind);notice="";sendState()
    }
    // Stop revokes a queued transport action while guides are still rendering.
    func afterPreparation(_ action:@escaping() throws -> Void)->() throws -> Void {
        let generation=transportGeneration
        return {guard self.transportGeneration==generation else{return};try action()}
    }
    func withGuides(force:Bool=false,_ action:@escaping() throws -> Void) throws {
        guard let root=root else{return}
        if !force,project.guideKey == project.desiredGuideKey(),project.guideFiles.values.allSatisfy({FileManager.default.fileExists(atPath:root.appendingPathComponent($0).path)}) {
            try action();return
        }
        let key=project.desiredGuideKey()
        try startJob("guides") {result in
            guard self.project.desiredGuideKey()==key else {throw StudioError(uiText("Les sections ou les réglages ont changé pendant la préparation. Relance la lecture pour les actualiser.", "Sections or settings changed during preparation. Start playback again to refresh them."))}
            try self.applyGuides(result,key:key)
            try action()
        }
    }
    func reloadAudio() throws {
        guard let root=root else{return}
        let pos=audio.current(),mode=audio.mode
        try audio.load(project,root:root);audio.position=min(pos,project.duration);audio.mode=mode;audio.applyMix()
    }
    func applyGuides(_ result:URL,key:String) throws {
        guard let root=root else{return}
        let obj=try JSONSerialization.jsonObject(with:Data(contentsOf:result)) as? [String:Any] ?? [:]
        guard let mapping=obj["files"] as? [String:String],mapping["click"] != nil,mapping["calls"] != nil else {throw StudioError(uiText("Les pistes de guidage n’ont pas été créées.", "Audio guides were not created."))}
        let timingChanged=project.timingGrid?.version != 1 || (!project.gridLocked && (obj["firstBeatCorrection"] as? Double).map{$0 != project.settings.firstBeat} == true)
        let prefix="Guides/"+UUID().uuidString,folder=root.appendingPathComponent(prefix)
        try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)
        var paths:[String:String]=[:]
        for (name,path) in mapping {
            let source=URL(fileURLWithPath:path).resolvingSymlinksInPath()
            guard source.path.hasPrefix(result.deletingLastPathComponent().resolvingSymlinksInPath().path+"/") else {throw StudioError(uiText("Un guide audio est hors du dossier de traitement.", "An audio guide is outside the processing folder."))}
            let file=UUID().uuidString+".wav";try FileManager.default.copyItem(at:source,to:folder.appendingPathComponent(file));paths[name]=prefix+"/"+file
        }
        let previousGuides=project.tracks.filter{$0.role.hasPrefix("guide_")}
        project.tracks.removeAll{$0.role.hasPrefix("guide_")}
        for (name,title,role) in [("click",uiText("Métronome", "Metronome"),"guide_click"),("calls",uiText("Appels de régions", "Region announcements"),"guide_voice"),("cues","Cues","guide_cue"),("counts",uiText("Décompte des régions", "Region count-in"),"guide_count")] {
            let relative=paths[name]!,url=root.appendingPathComponent(relative)
            let (duration,peaks)=try inspectAudio(url)
            var track=Track(name:title,file:relative,role:role,duration:duration,peaks:peaks)
            if let previous=previousGuides.first(where:{$0.role==role}) {
                track.id=previous.id;track.muted=previous.muted;track.solo=previous.solo
            }
            project.tracks.append(track)
        }
        if !project.gridLocked,let first=obj["firstBeatCorrection"] as? Double {project.settings.firstBeat=first}
        if let grid=obj["timingGrid"] {project.timingGrid=try JSONDecoder().decode(TimingGrid.self,from:JSONSerialization.data(withJSONObject:grid))}
        project.guideFiles=paths;project.guideKey=project.desiredGuideKey()
        try reloadAudio();try changed(invalidate:timingChanged);notice=uiText("Click, appels et décompte prêts.", "Click, announcements and count-in ready.")
        if let warnings=obj["guideWarnings"] as? [[String:Any]], !warnings.isEmpty {
            notice=uiText("Guides prêts · \(warnings.count) annonce(s) sans place avant l’entrée : raccourcis le texte ou le décompte.", "Guides ready · \(warnings.count) announcement(s) have no room before the entry. Shorten the text or count-in.")
        }
    }
    func settingsCommand(_ args:[String:Any]) throws {
        try requireIdle()
        guard let values=args["value"] as? [String:Any] else{return}
        let data=try JSONSerialization.data(withJSONObject:values)
        let settings=try JSONDecoder().decode(GuideSettings.self,from:data);try settings.validate()
        audio.pause();remember()
        if settings.firstBeat != project.settings.firstBeat || settings.gridMode != project.settings.gridMode || settings.beatsPerBar != project.settings.beatsPerBar || settings.manualBPM != project.settings.manualBPM || (settings.gridMode == "fixed" && settings.pulseUnit != project.settings.pulseUnit) {project.gridLocked=true}
        project.settings=settings;audio.project=project;audio.applyMix();try changed()
        try withGuides{self.notice=uiText("Réglages appliqués et guides actualisés.", "Settings applied and guides refreshed.")}
    }
    func decodeFile(_ url:URL,to target:URL) throws {
        let p=Process();p.executableURL=runtime.appendingPathComponent("import-tools/ffmpeg")
        p.arguments=["-nostdin","-hide_banner","-loglevel","error","-y","-protocol_whitelist","file,pipe,crypto,data","-i",url.path,"-map","0:a:0","-vn","-ac","2","-ar","44100","-c:a","pcm_f32le",target.path]
        let pipe=Pipe();p.standardError=pipe;p.standardOutput=FileHandle.nullDevice
        try p.run();let data=pipe.fileHandleForReading.readDataToEndOfFile();p.waitUntilExit()
        guard p.terminationStatus==0 else {throw StudioError(uiText("Format audio illisible ou protégé. ", "Unreadable or protected audio format. ")+(String(data:data.suffix(800),encoding:.utf8) ?? ""))}
    }
    func validatePreparation() throws {
        try requireIdle();audio.pause()
        try withGuides {
            let checkedRevision=self.revision
            try self.startJob("validate") {result in
                guard self.revision==checkedRevision else {throw StudioError(uiText("Le morceau a changé pendant la vérification. Valide à nouveau la préparation.", "The song changed during review. Approve the preparation again."))}
                let obj=try JSONSerialization.jsonObject(with:Data(contentsOf:result)) as? [String:Any] ?? [:]
                let data=try JSONSerialization.data(withJSONObject:obj["preparation"] ?? [:])
                self.project.preparation=try JSONDecoder().decode(Preparation.self,from:data)
                self.notice=uiText("Morceau validé. Tu peux maintenant l’envoyer dans REAPER.", "Song approved. You can now send it to REAPER.")
                try self.changed(invalidate:false)
            }
        }
    }
    func exportRPP(open:Bool=false,preflight:Bool=false) throws {
        try requireIdle()
        guard preflight || project.preparation?.fingerprint != nil else {throw StudioError(uiText("Valide d’abord le morceau dans Valider & envoyer.", "Approve the song in Review & send first."))}
        audio.pause()
        try withGuides {
            try self.startJob("reaper",arguments:preflight ? ["--preflight"] : []) {result in
                let obj=try JSONSerialization.jsonObject(with:Data(contentsOf:result)) as? [String:Any] ?? [:]
                guard let path=obj["path"] as? String else {throw StudioError(uiText("Le projet REAPER n’a pas été créé.", "The REAPER project was not created."))}
                self.lastExport=path
                self.notice=uiText("Projet REAPER prêt : pistes, tempo, transposition, régions, repères et guides conservés.", "REAPER project ready with tracks, tempo, transposition, regions, markers and guides.")
                if open {
                    let file=URL(fileURLWithPath:path)
                    guard let app=NSWorkspace.shared.urlForApplication(withBundleIdentifier:"com.cockos.reaper") ?? (["/Applications/REAPER.app",NSHomeDirectory()+"/Applications/REAPER.app"].first(where:{FileManager.default.fileExists(atPath:$0)}).map{URL(fileURLWithPath:$0)}) else {
                        self.notice=uiText("Projet exporté. Installe REAPER pour l’ouvrir ; Afficher l’export permet de retrouver le dossier.", "Project exported. Install REAPER to open it. Choose Show export to find the folder.")
                        return
                    }
                    NSWorkspace.shared.open([file],withApplicationAt:app,configuration:NSWorkspace.OpenConfiguration()){_,error in
                        if let error=error {DispatchQueue.main.async {self.notice=uiText("Projet exporté. Ouverture de REAPER impossible : ", "Project exported. Could not open REAPER: ")+error.localizedDescription;self.sendState()}}
                    }
                }
            }
        }
    }
    func importRPP(_ url:URL) throws {
        audio.pause()
        try startJob("rpp",input:url) {result in
            let obj=try JSONSerialization.jsonObject(with:Data(contentsOf:result)) as? [String:Any] ?? [:]
            guard let path=obj["project"] as? String else{throw StudioError(uiText("Le projet REAPER n’a pas été importé.", "The REAPER project was not imported."))}
            let from=URL(fileURLWithPath:path).resolvingSymlinksInPath()
            guard from.path.hasPrefix(result.deletingLastPathComponent().resolvingSymlinksInPath().path+"/") else{throw StudioError(uiText("Dossier d’import invalide.", "Invalid import folder."))}
            let imported=try StudioProject.load(from)
            var dest=self.library.appendingPathComponent(self.safeName(imported.name)+".bandstudio")
            if FileManager.default.fileExists(atPath:dest.path){dest=self.library.appendingPathComponent(self.safeName(imported.name)+" "+String(imported.id.prefix(6))+".bandstudio")}
            try FileManager.default.moveItem(at:from,to:dest);try self.load(dest)
            let warnings=obj["warnings"] as? [String] ?? []
            self.notice=uiText("Pistes audio, régions, repères et tempo importés de REAPER. ", "Audio tracks, regions, markers and tempo imported from REAPER. ")+warnings.joined(separator:" ")
        }
    }
    func applyTextAnalysis(_ kind:String,result:URL) throws {
        let obj=try JSONSerialization.jsonObject(with:Data(contentsOf:result)) as? [String:Any] ?? [:]
        if kind == "chords" {
            guard obj["engine"] as? String == "web-reference",let reference=obj["reference"] else{throw StudioError(uiText("La détection audio des accords est désactivée. Recherche une grille Internet.", "Audio chord detection is disabled. Find a chart online."))}
            let value=try JSONDecoder().decode(ChordReference.self,from:JSONSerialization.data(withJSONObject:reference))
            let manual=project.chords.filter{$0.manual}
            let entries=(obj["segments"] as? [[String:Any]] ?? []).compactMap{row -> TimedText? in
                guard let a=row["start"] as? Double,let end=row["end"] as? Double,let label=row["label"] as? String else{return nil}
                let b=min(project.duration,end)
                guard a>=0,b>a,!manual.contains(where:{$0.start<b && $0.end>a}) else{return nil}
                return TimedText(start:a,end:b,text:label,sourceURL:row["sourceURL"] as? String,confidence:row["confidence"] as? Double)
            }
            remember();project.chordReference=value
            if !(obj["segments"] as? [[String:Any]] ?? []).isEmpty {project.chords=(manual+entries).sorted{$0.start<$1.start}}
            project.analysisCompleted(kind)
            try changed(invalidate:!(obj["segments"] as? [[String:Any]] ?? []).isEmpty || project.structureProposal?.status == "proposed")
            notice=value.message;return
        }
        remember()
        if kind == "drums" {
            let pitches=["BD":36,"SD":38,"TT":45,"HH":42,"CY":49]
            let onsets=obj["onsets"] as? [String:[[Double]]] ?? [:]
            project.drumHits=onsets.flatMap{role,notes in notes.compactMap{row -> DrumHit? in
                guard row.count>=2,row[0]>=0,row[0]<=self.project.duration else{return nil}
                return DrumHit(time:row[0],pitch:pitches[role] ?? 38,velocity:max(1,min(127,Int(row[1]*127))))
            }}.sorted{$0.time<$1.time}
        } else {
            var result:[TimedText]=[]
            for row in obj["segments"] as? [[String:Any]] ?? [] {
                let a=row["start"] as? Double ?? row["t"] as? Double ?? 0,b=min(project.duration,row["end"] as? Double ?? 0)
                let text=row["text"] as? String ?? row["label"] as? String ?? ""
                if b>a && a>=0 {
                    var item=TimedText(start:a,end:b,text:text,sourceURL:row["sourceURL"] as? String,confidence:row["confidence"] as? Double)
                    if kind == "lyrics" {
                        item.timingReview=row["timingReview"] as? Bool
                        item.words=(row["words"] as? [[String:Any]] ?? []).compactMap{w in
                            guard let t=w["t"] as? Double,let end=w["end"] as? Double,let word=w["w"] as? String,t>=a,end>t,end<=b+0.1 else{return nil}
                            return TimedWord(start:t,end:end,text:word,timingReview:w["timingReview"] as? Bool)
                        }
                    }
                    result.append(item)
                }
            }
            if kind == "lyrics" {
                let manual=project.lyrics.filter{$0.manual};project.lyrics=manual+result.filter{s in !manual.contains{$0.start<s.end && $0.end>s.start}}
                project.lyrics.sort{$0.start<$1.start}
            } else {
                let manual=project.chords.filter{$0.manual};project.chords=manual+result.filter{s in !manual.contains{$0.start<s.end && $0.end>s.start}}
                project.chords.sort{$0.start<$1.start}
            }
        }
        if kind == "lyrics",let reference=obj["lyricsReference"] {
            project.lyricsReference=try JSONDecoder().decode(LyricsReference.self,from:JSONSerialization.data(withJSONObject:reference))
        }
        project.analysisCompleted(kind)
        try changed();notice=kind == "lyrics" ? (project.lyricsReference?.message ?? uiText("Transcription ajoutée.", "Transcription added.")) : uiText("Analyse ajoutée. Tu peux corriger chaque entrée dans le prompteur.", "Analysis added. Edit individual entries in the teleprompter.")
    }
    func annotation(_ args:[String:Any]) throws {
        guard let kind=args["kind"] as? String,["lyrics","chords"].contains(kind) else{return}
        let id=args["id"] as? String ?? UUID().uuidString
        var entries=kind == "lyrics" ? project.lyrics : project.chords
        if args["delete"] as? Bool == true {entries.removeAll{$0.id==id}}
        else {
            let a=try number(args,"start",range:0...project.duration),b=try number(args,"end",range:0...project.duration)
            guard b>a,let text=args["text"] as? String,!text.isEmpty else{throw StudioError(uiText("Saisis un texte et des temps valides.", "Enter text and valid times."))}
            var words:[TimedWord]?=nil
            if kind == "lyrics",let raw=args["words"] as? [[String:Any]] {
                guard raw.count<=300 else{throw StudioError(uiText("Trop de mots pour cette ligne.", "Too many words for this line."))}
                var previous=a;words=[]
                for row in raw {
                    let start=try number(row,"start",range:a...b),end=try number(row,"end",range:a...b)
                    guard start>=previous,end>start,let word=row["text"] as? String,!word.isEmpty,word.count<=120 else{throw StudioError(uiText("Les mots doivent se suivre sans se chevaucher, dans les limites de la ligne.", "Words must stay in order within the line and cannot overlap."))}
                    words!.append(TimedWord(start:start,end:end,text:word));previous=end
                }
            }
            entries.removeAll{$0.id==id}
            if kind == "chords",args["replaceRange"] as? Bool == true {
                // Preserve the old harmony on either side of the corrected passage.
                entries=entries.flatMap { item -> [TimedText] in
                    guard item.start<b && item.end>a else{return [item]}
                    var tails:[TimedText]=[]
                    if item.start<a {var left=item;left.end=a;tails.append(left)}
                    if item.end>b {var right=item;right.start=b;if !tails.isEmpty{right.id=UUID().uuidString};tails.append(right)}
                    return tails
                }
            }
            entries.append(TimedText(id:id,start:a,end:b,text:String(text.prefix(1000)),manual:true,words:words));entries.sort{$0.start<$1.start}
        }
        remember();if kind == "lyrics"{project.lyrics=entries}else{project.chords=entries};try changed()
    }
    func editStructure(_ command:String,args:[String:Any]) throws {
        guard let id=args["id"] as? String,let index=project.sections.firstIndex(where:{$0.id==id}) else{throw StudioError(uiText("Sélectionne une section dans l’atelier.", "Select a section in the editor."))}
        if command == "splitSection" {
            let point=try number(args,"time",range:0...project.duration),section=project.sections[index]
            guard point>section.start+0.01,point<section.end-0.01 else{throw StudioError(uiText("Place la tête de lecture à l’intérieur de la section à scinder.", "Place the playhead inside the section to split."))}
            remember();var next=section;next.id=UUID().uuidString;next.start=point;next.name += uiText(" · suite", " · continued");next.locked=true;next.origin="manual";next.reviewed=false
            project.sections[index].end=point;project.sections[index].locked=true;project.sections[index].origin="manual";project.sections[index].reviewed=false;project.sections.insert(next,at:index+1)
        } else {
            guard index+1<project.sections.count else{throw StudioError(uiText("Il n’y a pas de section suivante.", "There is no next section."))}
            remember();project.sections[index].end=project.sections[index+1].end;project.sections[index].locked=true;project.sections[index].origin="manual";project.sections[index].reviewed=false;project.sections.remove(at:index+1)
        }
        try changed()
    }
    func editDrum(_ args:[String:Any]) throws {
        let time=try number(args,"time",range:0...project.duration),pitch=Int(try number(args,"pitch",range:0...127)),tolerance=try number(args,"tolerance",range:0.001...1)
        remember();project.drumHits.removeAll{$0.pitch==pitch && abs($0.time-time)<tolerance}
        if args["on"] as? Bool == true{project.drumHits.append(DrumHit(time:time,pitch:pitch,velocity:Int(try number(args,"velocity",range:1...127))));project.drumHits.sort{$0.time<$1.time}}
        try changed()
    }
    func updateSetlist(_ args:[String:Any]) throws {
        guard let name=args["name"] as? String,!name.trimmingCharacters(in:.whitespaces).isEmpty,let paths=args["paths"] as? [String],paths.count<=500 else{throw StudioError(uiText("Donne un nom à ta setlist.", "Enter a name for the setlist."))}
        let allowed=Set(projectList().compactMap{$0["path"]})
        guard paths.allSatisfy({allowed.contains($0)}) else{throw StudioError(uiText("Un morceau de la setlist n’est plus dans la bibliothèque.", "A song in the setlist is no longer in the library."))}
        let id=args["id"] as? String ?? UUID().uuidString
        let item=StudioSetlist(id:id,name:String(name.prefix(120)),paths:paths)
        var updated=setlists
        if let i=updated.firstIndex(where:{$0.id==id}){updated[i]=item}else{updated.append(item)}
        try JSONEncoder().encode(updated).write(to:library.appendingPathComponent("setlists.json"),options:.atomic)
        setlists=updated;notice=uiText("Setlist enregistrée. Chaque morceau s’arrête à sa fin.", "Setlist saved. Playback stops at the end of each song.");sendState()
    }
}

extension StudioApp {
    func catalogCall(_ arguments:[String]) throws -> Any {
        let p=Process();p.executableURL=runtime.appendingPathComponent(".venv/bin/python")
        p.arguments=[runtime.appendingPathComponent("catalog.py").path]+arguments
        let pipe=Pipe();p.standardOutput=pipe;p.standardError=FileHandle.nullDevice
        try p.run();let data=pipe.fileHandleForReading.readDataToEndOfFile();p.waitUntilExit()
        guard p.terminationStatus==0 else {throw StudioError(uiText("La bibliothèque n’a pas pu être modifiée. Le projet est conservé.", "Could not update the library. Your project has been kept."))}
        return try JSONSerialization.jsonObject(with:data,options:.fragmentsAllowed)
    }
    func pendingTrashedProjects()->Set<URL> {
        let fm=FileManager.default;let trash=library.appendingPathComponent(".Trash")
        guard trash.resolvingSymlinksInPath()==trash.standardizedFileURL else{return []}
        var hidden=Set<URL>()
        for folder in (try? fm.contentsOfDirectory(at:trash,includingPropertiesForKeys:nil)) ?? [] {
            let receipt=folder.appendingPathComponent("removal.json")
            guard folder.resolvingSymlinksInPath()==folder.standardizedFileURL,
                  receipt.resolvingSymlinksInPath()==receipt.standardizedFileURL,
                  let data=try? Data(contentsOf:receipt),
                  let item=(try? JSONSerialization.jsonObject(with:data)) as? [String:Any],
                  let name=item["name"] as? String, name.hasSuffix(".bandstudio"), !name.contains("/"), !name.contains("\\"),
                  let id=item["projectID"] as? String, !id.isEmpty else{continue}
            if fm.fileExists(atPath:folder.appendingPathComponent(name).path){continue}
            let path=library.appendingPathComponent(name).standardizedFileURL
            guard path.resolvingSymlinksInPath()==path,
                  let data=try? Data(contentsOf:path.appendingPathComponent("project.json")),
                  let project=(try? JSONSerialization.jsonObject(with:data)) as? [String:Any], project["id"] as? String==id else{continue}
            hidden.insert(path)
        }
        return hidden
    }
    func hasTrashedProjects()->Bool {
        if !pendingTrashedProjects().isEmpty{return true}
        let fm=FileManager.default
        let trash=library.appendingPathComponent(".Trash")
        return ((try? fm.contentsOfDirectory(at:trash,includingPropertiesForKeys:nil)) ?? []).contains{folder in
            ((try? fm.contentsOfDirectory(at:folder,includingPropertiesForKeys:nil)) ?? []).contains{$0.pathExtension=="bandstudio"}
        }
    }
    func catalogCommand(_ command:String,_ args:[String:Any]) throws {
        try requireIdle()
        if command=="restoreProject" {
            _ = try catalogCall(["restore",library.path]);notice=uiText("Morceau restauré dans la bibliothèque.", "Song restored to the library.");sendState();return
        }
        guard let path=args["path"] as? String,projectList().contains(where:{$0["path"]==path}) else {throw StudioError(uiText("Morceau hors de la bibliothèque.", "Song outside the library."))}
        if command=="renameProject" {
            guard let name=args["name"] as? String else{throw StudioError(uiText("Donne un nom au morceau.", "Enter a name for the song."))}
            let active=root?.standardizedFileURL.path==URL(fileURLWithPath:path).standardizedFileURL.path
            if active{try save()}
            guard let renamed=try catalogCall(["rename",library.path,path,name]) as? String else{throw StudioError(uiText("Nom du morceau invalide.", "Invalid song name."))}
            if active {
                project.name=renamed;audio.project.name=renamed
                project.preparation=try StudioProject.load(URL(fileURLWithPath:path)).preparation
                audio.project.preparation=project.preparation
                for i in history.indices{history[i].name=renamed;history[i].preparation=nil}
                for i in future.indices{future[i].name=renamed;future[i].preparation=nil}
                revision += 1
            }
            notice=uiText("Morceau renommé.", "Song renamed.");sendState();return
        }
        if command=="deleteProject" {
            let active=root?.standardizedFileURL.path==URL(fileURLWithPath:path).standardizedFileURL.path
            if active{audio.pause()}
            _ = try catalogCall(["remove",library.path,path])
            if active {project=StudioProject();try audio.load(project,root:library);root=nil;history=[];future=[];lastExport="";revision += 1;UserDefaults.standard.removeObject(forKey:"project")}
            notice=uiText("Morceau retiré de la bibliothèque. Tu peux le restaurer depuis Mes morceaux.", "Song removed from the library. Restore it from My songs.");sendState();return
        }
        let panel=NSOpenPanel();panel.allowedFileTypes=["jpg","jpeg","png","webp"];panel.message=uiText("Choisis la pochette du morceau.", "Choose cover art for the song.")
        panel.beginSheetModal(for:window){answer in
            guard answer == .OK,let image=panel.url else{return}
            self.busy=true;self.jobName=uiText("Ajout de la pochette", "Adding cover art");self.sendState()
            DispatchQueue.global(qos:.userInitiated).async {
                let ok=(try? self.catalogCall(["extract",path,image.path,self.runtime.path])) as? Bool ?? false
                DispatchQueue.main.async {self.busy=false;self.jobName="";self.notice=ok ? uiText("Pochette enregistrée.", "Cover art saved.") : uiText("Image illisible. Choisis une image JPG, PNG ou WebP.", "Unreadable image. Choose a JPG, PNG or WebP file.");self.sendState()}
            }
        }
    }
    func analysisPlan()->[String] {
        let fm=FileManager.default
        func available(_ env:String)->Bool {fm.fileExists(atPath:runtime.appendingPathComponent(env+"/bin/python").path)}
        var steps:[String]=[]
        if available(".venv-demucs"),!project.tracks.contains(where:{["drums","bass","vocals","other","guitar","piano"].contains($0.role)}){steps.append("separate")}
        let canSeparate=steps.contains("separate")
        if available(".venv-demucs"),fm.fileExists(atPath:runtime.appendingPathComponent("drumsep/49469ca8.th").path),canSeparate || project.tracks.contains(where:{$0.role=="drums"}) {steps.append("drumsep")}
        if available(".venv-creative"),fm.fileExists(atPath:runtime.appendingPathComponent("creative/UVR_MDXNET_KARA_2.onnx").path),canSeparate || project.tracks.contains(where:{$0.role=="vocals"}) {steps.append("vocalsplit")}
        if !project.gridLocked {
            let libs=runtime.appendingPathComponent(".venv-demucs/lib")
            let smart=((try? fm.contentsOfDirectory(at:libs,includingPropertiesForKeys:nil)) ?? []).contains{fm.fileExists(atPath:$0.appendingPathComponent("site-packages/beat_this").path)}
            steps.append(smart ? "smartgrid" : "grid")
        }
        if available(".venv-structure"){steps.append("structure")}
        if project.key.isEmpty{steps.append("key")}
        if available(".venv-words"){steps.append(project.analysisDone("lyrics") ? "lyricscorrect" : "lyrics")}
        steps=steps.filter{!project.analysisDone($0)}
        // The final pass discovers and aligns chords once, after the sections.
        // Existing choices remain editable and no human validation is invented.
        if project.tracks.contains(where:{$0.role=="source"}),!steps.isEmpty || project.structureProposal?.status != "prepared" || (project.structureProposal?.sectionTimingVersion ?? 0)<1 {steps.append("prepareReview")}
        let needsGuides = !steps.isEmpty || project.guideKey != project.desiredGuideKey()
        if steps.isEmpty,project.tracks.contains(where:{$0.role=="source"}),!project.analysisDone("chords"),
           let ref=project.chordReference,ref.sources.isEmpty,ref.checks?.isEmpty == false,
           Date().timeIntervalSince1970 >= (ref.retryAfter ?? 0) {steps.append("chords")}
        if needsGuides {steps.append("guides")}
        return steps
    }
    func calibrateImportedSong() throws {
        guard !project.analysisDone("grid") else{return}
        let identity=project.id,generation=transportGeneration
        let finish:()throws->Void = {
            guard self.project.id==identity,self.transportGeneration==generation else{return}
            try self.withGuides{
                self.notice=uiText("Import terminé. ", "Import complete. ")+self.project.analysisNote
                self.sendState()
            }
        }
        if analysisPlan().contains("smartgrid") {try advancedTask(["kind":"smartgrid"],completion:finish)}
        else {try runAnalysis("grid",model:"htdemucs",completion:finish)}
    }
    func prepareAll(_ args:[String:Any],only:Set<String>?=nil,completion:(()throws->Void)?=nil) throws {
        try requireIdle()
        guard root != nil,project.tracks.contains(where:{$0.role=="source"}) else {throw StudioError(uiText("Importe le morceau original avant de lancer la préparation complète.", "Import the original song before running complete preparation."))}
        audio.pause()
        let steps=analysisPlan().filter{only?.contains($0) ?? true},identity=project.id,generation=transportGeneration
        func next(_ index:Int) throws {
            guard self.project.id==identity,self.transportGeneration==generation else{return}
            if index==steps.count {
                if let completion=completion {try completion();return}
                self.notice=uiText("Ton morceau est prêt à écouter.", "Your song is ready to hear.")
                self.sendState()
                self.send(["type":"preparationFinished","projectID":identity])
                return
            }
            let kind=steps[index]
            let finish:()throws->Void = {try next(index+1)}
            if kind=="guides" {try self.withGuides(finish)}
            else if kind=="vocalsplit" {try self.creativeTask(["kind":kind],completion:finish)}
            else if kind=="prepareReview" {
                let checkedRevision=self.revision
                try self.startJob(kind) {result in
                    guard self.revision==checkedRevision else{throw StudioError(uiText("Le morceau a changé pendant la vérification finale.", "The song changed during the final check."))}
                    let object=try JSONSerialization.jsonObject(with:Data(contentsOf:result)) as? [String:Any] ?? [:]
                    guard let value=object["project"] else{throw StudioError(uiText("Préparation finale incomplète.", "Final preparation incomplete."))}
                    let prepared=try JSONDecoder().decode(StudioProject.self,from:JSONSerialization.data(withJSONObject:value))
                    guard prepared.id==self.project.id else{throw StudioError(uiText("Préparation d’un autre morceau.", "This preparation belongs to another song."))}
                    try prepared.validate();self.remember();self.project=prepared;try self.reloadAudio();try self.changed(invalidate:false)
                    try finish()
                }
            }
            else if ["smartgrid","key"].contains(kind){try self.advancedTask(["kind":kind],completion:finish)}
            else{try self.runAnalysis(kind,model:args["model"] as? String ?? "htdemucs",language:args["language"] as? String ?? "auto",quality:args["quality"] as? String ?? "standard",completion:finish)}
            if self.busy {self.jobPlan=steps;self.jobPlanIndex=index;self.jobName=uiText("Tout préparer · \(index+1)/\(steps.count) · ", "Prepare everything · \(index+1)/\(steps.count) · ")+self.jobName;self.sendState()}
        }
        try next(0)
    }
}


extension StudioApp {
    func artworkCommand(_ args:[String:Any]) throws {
        guard let path=args["path"] as? String else{return}
        guard !artworkBusy,projectList().contains(where:{$0["path"]==path}) else {
            send(["type":"artworkResult","path":path,"message":uiText("Ce morceau n’est pas disponible pour la recherche.", "This song is unavailable for search.")]);return
        }
        let payload=try JSONSerialization.data(withJSONObject:args)
        guard let text=String(data:payload,encoding:.utf8),text.utf8.count<4096 else {throw StudioError(uiText("Recherche trop longue.", "Search too long."))}
        artworkBusy=true
        // Keep playback/import/analysis available while the separate helper uses
        // the network. Space helpers as well as requests to respect MusicBrainz.
        DispatchQueue.global(qos:.utility).asyncAfter(deadline:.now()+1.1) {
            var result:[String:Any]=[:]
            do {
                let p=Process();p.executableURL=self.runtime.appendingPathComponent(".venv/bin/python")
                p.arguments=[self.runtime.appendingPathComponent("artwork.py").path,self.library.path,self.runtime.path,text]
                let pipe=Pipe();p.standardOutput=pipe;p.standardError=FileHandle.nullDevice
                try p.run();let data=pipe.fileHandleForReading.readDataToEndOfFile();p.waitUntilExit()
                result=(try? JSONSerialization.jsonObject(with:data)) as? [String:Any] ?? ["message":uiText("Recherche indisponible. Réessaie plus tard.", "Search unavailable. Try again later.")]
            } catch {result=["message":uiText("Recherche indisponible. Réessaie plus tard.", "Search unavailable. Try again later.")]}
            let response=result
            DispatchQueue.main.async {
                self.artworkBusy=false
                var message=response;message["type"]="artworkResult";message["path"]=path;self.send(message)
            }
        }
    }
}


extension StudioApp {
    func guideMix(_ args:[String:Any]) throws {
        guard let key=args["key"] as? String,["clickGain","callsGain","cuesGain","countGain"].contains(key) else{throw StudioError(uiText("Volume inconnu.", "Unknown volume."))}
        let gain=Float(try number(args,"value",range:0...1.5));remember()
        switch key {
        case "clickGain":project.settings.clickGain=gain;if gain>0{project.settings.clickEnabled=true}
        case "callsGain":project.settings.callsGain=gain;if gain>0{project.settings.callsEnabled=true}
        case "cuesGain":project.settings.cuesGain=gain;if gain>0{project.settings.speakCues=true}
        default:project.settings.countGain=gain
        }
        audio.project=project;audio.applyMix();try changed()
    }
    func editMarker(_ args:[String:Any],review:Bool) throws {
        guard let kind=args["kind"] as? String,let id=args["id"] as? String else{throw StudioError(uiText("Sélectionne un repère.", "Select a marker."))}
        audio.pause()
        if kind=="cue",let i=project.cues.firstIndex(where:{$0.id==id}) {
            let at=review ? project.cues[i].time : try number(args,"time",range:0...project.duration)
            remember();project.cues[i].time=at;project.cues[i].reviewed=review
            project.cues.sort{$0.time<$1.time}
        } else if kind=="section",let i=project.sections.firstIndex(where:{$0.id==id}) {
            let at=review ? project.sections[i].start : try number(args,"time",range:0...project.duration)
            if !review {
                guard at<project.sections[i].end-0.01,(i==0 || at>project.sections[i-1].start+0.01) else{throw StudioError(uiText("Le début doit rester entre les sections voisines.", "The start must stay between the neighboring sections."))}
                if i>0,abs(project.sections[i-1].end-project.sections[i].start)>=0.001,at<project.sections[i-1].end {throw StudioError(uiText("Cette position chevauche la section précédente.", "This position overlaps the previous section."))}
            }
            remember()
            if !review {
                if i>0,abs(project.sections[i-1].end-project.sections[i].start)<0.001 {
                    project.sections[i-1].end=at;project.sections[i-1].locked=true;project.sections[i-1].origin="manual";project.sections[i-1].reviewed=false
                }
                project.sections[i].start=at;project.sections[i].origin="manual"
            }
            project.sections[i].locked=true;project.sections[i].reviewed=review
        } else {throw StudioError(uiText("Ce repère n’existe plus.", "This marker no longer exists."))}
        try changed()
    }
}
