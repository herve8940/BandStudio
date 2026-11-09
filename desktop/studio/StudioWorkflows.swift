import AppKit
import AVFoundation

extension StudioApp {
    func snapshot(at url:URL) throws {
        var object=try JSONSerialization.jsonObject(with:JSONEncoder().encode(project)) as! [String:Any]
        object["_root"]=root?.path
        object["_mode"]=audio.mode
        try JSONSerialization.data(withJSONObject:object,options:[.sortedKeys]).write(to:url,options:.atomic)
    }
    func startJob(_ kind:String,input:URL?=nil,arguments:[String]=[],completion:@escaping(URL) throws -> Void) throws {
        try requireIdle()
        let base=root ?? library.appendingPathComponent(".Imports")
        let folder=base.appendingPathComponent("Analyses/"+UUID().uuidString)
        try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)
        let result=folder.appendingPathComponent("result.json"),snap=folder.appendingPathComponent("project.json")
        try snapshot(at:snap)
        let environment=["generate":".venv-creative","vocalsplit":".venv-creative","structure":".venv-structure","separate":".venv-demucs","drumsep":".venv-demucs","smartgrid":".venv-demucs","lyrics":".venv-words","chords":".venv-chords","drums":".venv-drums"]
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
        p.terminationHandler={[weak self] process in
            try? handle.close()
            DispatchQueue.main.async {
                guard let self=self else{return}
                let cancelled=self.job == nil
                self.busy=false;self.job=nil;self.jobName=""
                if cancelled {self.notice="Traitement annulé. Le projet est conservé.";self.sendState();return}
                guard self.project.id == identity else{self.sendState();return}
                guard process.terminationStatus == 0 else {self.notice="Le traitement a échoué : "+self.jobDetail();self.sendState();return}
                self.perform{try completion(result);self.sendState()}
            }
        }
        try p.run();job=p;busy=true;jobLog=log
        let titles=["generate":"Création musicale locale","vocalsplit":"Séparation chant principal et chœurs","smartgrid":"Détection des temps et débuts de mesure","drumsep":"Séparation des éléments de batterie","key":"Estimation de la tonalité","lyricsimport":"Import des paroles synchronisées","lyricsexport":"Export des paroles","stemsexport":"Export des stems","master":"Normalisation du mix","report":"Analyse des niveaux audio","portable":"Création du projet portable","sheet":"Création de la fiche PDF","guides":"Préparation du click, des appels et du décompte","separate":"Séparation des instruments","structure":"Analyse de la structure","grid":"Détection du tempo et des temps","link":"Import du lien","reaper":"Création du projet REAPER","lyrics":"Transcription des paroles","chords":"Détection des accords","drums":"Transcription de la batterie","midi":"Export MIDI","decode":"Conversion du fichier audio"]
        jobName=kind == "rpp" ? "Import des pistes et régions REAPER" : (titles[kind] ?? kind);notice="";sendState()
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
            guard self.project.desiredGuideKey()==key else {throw StudioError("Les sections ou les réglages ont changé pendant la préparation. Relance la lecture pour les actualiser.")}
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
        guard let mapping=obj["files"] as? [String:String],mapping["click"] != nil,mapping["calls"] != nil else {throw StudioError("Les pistes de guidage n’ont pas été créées.")}
        let prefix="Guides/"+UUID().uuidString,folder=root.appendingPathComponent(prefix)
        try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)
        var paths:[String:String]=[:]
        for (name,path) in mapping {
            let source=URL(fileURLWithPath:path).resolvingSymlinksInPath()
            guard source.path.hasPrefix(result.deletingLastPathComponent().resolvingSymlinksInPath().path+"/") else {throw StudioError("Un guide audio est hors du dossier de traitement.")}
            let file=UUID().uuidString+".wav";try FileManager.default.copyItem(at:source,to:folder.appendingPathComponent(file));paths[name]=prefix+"/"+file
        }
        project.tracks.removeAll{$0.role.hasPrefix("guide_")}
        for (name,title,role) in [("click","Métronome","guide_click"),("calls","Appels de régions","guide_voice"),("counts","Décompte des régions","guide_count")] {
            let relative=paths[name]!,url=root.appendingPathComponent(relative)
            let (duration,peaks)=try inspectAudio(url)
            project.tracks.append(Track(name:title,file:relative,role:role,duration:duration,peaks:peaks))
        }
        project.guideFiles=paths;project.guideKey=key
        try reloadAudio();try changed();notice="Click, appels et décompte prêts."
    }
    func settingsCommand(_ args:[String:Any]) throws {
        try requireIdle()
        guard let values=args["value"] as? [String:Any] else{return}
        let data=try JSONSerialization.data(withJSONObject:values)
        let settings=try JSONDecoder().decode(GuideSettings.self,from:data);try settings.validate()
        audio.pause();remember()
        if settings.firstBeat != project.settings.firstBeat || settings.gridMode != project.settings.gridMode || settings.beatsPerBar != project.settings.beatsPerBar || settings.manualBPM != project.settings.manualBPM {project.gridLocked=true}
        project.settings=settings;audio.project=project;audio.applyMix();try changed()
        try withGuides{self.notice="Réglages appliqués et guides actualisés."}
    }
    func importURL(_ value:String) throws {
        guard let u=URL(string:value),["http","https"].contains(u.scheme ?? ""),u.host != nil else {throw StudioError("Colle un lien HTTP ou HTTPS vers un morceau ou une vidéo.")}
        try startJob("link",arguments:["--url",value]) {result in
            let data=try JSONSerialization.jsonObject(with:Data(contentsOf:result)) as? [String:Any] ?? [:]
            guard let path=data["audio"] as? String else {throw StudioError("Aucun audio reçu.")}
            self.pendingImportTitle=data["title"] as? String;self.pendingSourceURL=value
            self.importFiles([URL(fileURLWithPath:path)],new:true)
        }
    }
    func decodeFile(_ url:URL,to target:URL) throws {
        let p=Process();p.executableURL=runtime.appendingPathComponent("import-tools/ffmpeg")
        p.arguments=["-nostdin","-hide_banner","-loglevel","error","-y","-protocol_whitelist","file,pipe,crypto,data","-i",url.path,"-map","0:a:0","-vn","-ac","2","-ar","44100","-c:a","pcm_f32le",target.path]
        let pipe=Pipe();p.standardError=pipe;p.standardOutput=FileHandle.nullDevice
        try p.run();let data=pipe.fileHandleForReading.readDataToEndOfFile();p.waitUntilExit()
        guard p.terminationStatus==0 else {throw StudioError("Format audio illisible ou protégé. "+(String(data:data.suffix(800),encoding:.utf8) ?? ""))}
    }
    func exportRPP() throws {
        try withGuides {
            try self.startJob("reaper") {result in
                let obj=try JSONSerialization.jsonObject(with:Data(contentsOf:result)) as? [String:Any] ?? [:]
                guard let path=obj["path"] as? String else{return}
                self.lastExport=path;self.notice="Projet REAPER créé avec les pistes, les régions, les repères et les guides. Le bouton Afficher l’export ouvre son dossier."
            }
        }
    }
    func importRPP(_ url:URL) throws {
        audio.pause()
        try startJob("rpp",input:url) {result in
            let obj=try JSONSerialization.jsonObject(with:Data(contentsOf:result)) as? [String:Any] ?? [:]
            guard let path=obj["project"] as? String else{throw StudioError("Le projet REAPER n’a pas été importé.")}
            let from=URL(fileURLWithPath:path).resolvingSymlinksInPath()
            guard from.path.hasPrefix(result.deletingLastPathComponent().resolvingSymlinksInPath().path+"/") else{throw StudioError("Dossier d’import invalide.")}
            let imported=try StudioProject.load(from)
            var dest=self.library.appendingPathComponent(self.safeName(imported.name)+".bandstudio")
            if FileManager.default.fileExists(atPath:dest.path){dest=self.library.appendingPathComponent(self.safeName(imported.name)+" "+String(imported.id.prefix(6))+".bandstudio")}
            try FileManager.default.moveItem(at:from,to:dest);try self.load(dest)
            let warnings=obj["warnings"] as? [String] ?? []
            self.notice="Pistes audio, régions, repères et tempo importés de REAPER. "+warnings.joined(separator:" ")
        }
    }
    func applyTextAnalysis(_ kind:String,result:URL) throws {
        let obj=try JSONSerialization.jsonObject(with:Data(contentsOf:result)) as? [String:Any] ?? [:]
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
                    var item=TimedText(start:a,end:b,text:text)
                    if kind == "lyrics" {
                        item.words=(row["words"] as? [[String:Any]] ?? []).compactMap{w in
                            guard let t=w["t"] as? Double,let end=w["end"] as? Double,let word=w["w"] as? String,t>=a,end>t,end<=b+0.1 else{return nil}
                            return TimedWord(start:t,end:end,text:word)
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
        try changed();notice="Analyse ajoutée. Tu peux corriger chaque entrée dans le prompteur."
    }
    func annotation(_ args:[String:Any]) throws {
        guard let kind=args["kind"] as? String,["lyrics","chords"].contains(kind) else{return}
        let id=args["id"] as? String ?? UUID().uuidString
        var entries=kind == "lyrics" ? project.lyrics : project.chords
        if args["delete"] as? Bool == true {entries.removeAll{$0.id==id}}
        else {
            let a=try number(args,"start",range:0...project.duration),b=try number(args,"end",range:0...project.duration)
            guard b>a,let text=args["text"] as? String,!text.isEmpty else{throw StudioError("Saisis un texte et des temps valides.")}
            var words:[TimedWord]?=nil
            if kind == "lyrics",let raw=args["words"] as? [[String:Any]] {
                guard raw.count<=300 else{throw StudioError("Trop de mots pour cette ligne.")}
                var previous=a;words=[]
                for row in raw {
                    let start=try number(row,"start",range:a...b),end=try number(row,"end",range:a...b)
                    guard start>=previous,end>start,let word=row["text"] as? String,!word.isEmpty,word.count<=120 else{throw StudioError("Les mots doivent se suivre sans se chevaucher, dans les limites de la ligne.")}
                    words!.append(TimedWord(start:start,end:end,text:word));previous=end
                }
            }
            entries.removeAll{$0.id==id};entries.append(TimedText(id:id,start:a,end:b,text:String(text.prefix(1000)),manual:true,words:words));entries.sort{$0.start<$1.start}
        }
        remember();if kind == "lyrics"{project.lyrics=entries}else{project.chords=entries};try changed()
    }
    func editStructure(_ command:String,args:[String:Any]) throws {
        guard let id=args["id"] as? String,let index=project.sections.firstIndex(where:{$0.id==id}) else{throw StudioError("Sélectionne une section dans l’atelier.")}
        if command == "splitSection" {
            let point=try number(args,"time",range:0...project.duration),section=project.sections[index]
            guard point>section.start+0.01,point<section.end-0.01 else{throw StudioError("Place la tête de lecture à l’intérieur de la section à scinder.")}
            remember();var next=section;next.id=UUID().uuidString;next.start=point;next.name += " · suite";next.locked=true;next.origin="manual"
            project.sections[index].end=point;project.sections[index].locked=true;project.sections[index].origin="manual";project.sections.insert(next,at:index+1)
        } else {
            guard index+1<project.sections.count else{throw StudioError("Il n’y a pas de section suivante.")}
            remember();project.sections[index].end=project.sections[index+1].end;project.sections[index].locked=true;project.sections[index].origin="manual";project.sections.remove(at:index+1)
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
        guard let name=args["name"] as? String,!name.trimmingCharacters(in:.whitespaces).isEmpty,let paths=args["paths"] as? [String],paths.count<=500 else{throw StudioError("Donne un nom à ta setlist.")}
        let allowed=Set(projectList().compactMap{$0["path"]})
        guard paths.allSatisfy({allowed.contains($0)}) else{throw StudioError("Un morceau de la setlist n’est plus dans la bibliothèque.")}
        let id=args["id"] as? String ?? UUID().uuidString
        let item=StudioSetlist(id:id,name:String(name.prefix(120)),paths:paths)
        var updated=setlists
        if let i=updated.firstIndex(where:{$0.id==id}){updated[i]=item}else{updated.append(item)}
        try JSONEncoder().encode(updated).write(to:library.appendingPathComponent("setlists.json"),options:.atomic)
        setlists=updated;notice="Setlist enregistrée. Chaque morceau s’arrête à sa fin.";sendState()
    }
}
