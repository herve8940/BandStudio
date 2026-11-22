import AppKit
import WebKit
import AVFoundation

final class StudioApp: NSObject, NSApplicationDelegate, WKScriptMessageHandler, WKNavigationDelegate {
    var window:NSWindow!
    var web:WKWebView!
    let audio=StudioAudio()
    let recorder=Recorder()
    var project=StudioProject()
    var root:URL?
    var library:URL!
    var runtime:URL!
    var webRoot:URL!
    var busy=false
    var job:Process?
    var jobName=""
    var jobKind=""
    var jobIdentifier=""
    var jobPlan:[String]=[]
    var jobPlanIndex=0
    var jobLog:URL?
    var jobStarted=0.0
    var notice=""
    var history:[StudioProject]=[]
    var future:[StudioProject]=[]
    var revision=0
    var recordingStart=0.0
    var recordingHost:UInt64=0
    var transportOrigin=0.0
    var transportGeneration=0
    var recordPending=false
    var recordRequest=""
    var pendingImportTitle:String?
    var pendingSourceURL=""
    var pendingArtwork:String?
    var pendingMusicMetadata="{}"
    var artworkBusy=false
    var lastExport=""
    var setlists:[StudioSetlist]=[]
    var pendingProject:URL?
    var timer:Timer?
    var lastBroadcast=0.0
    var quitting=false
    var checkingUpdate=false
    var phoneProcess:Process?
    var phoneFolder:URL?
    var phoneRevision = -1
    var phonePulse=0.0
    var phoneAnnounced=false
    var queueProcess:Process?
    var queueInput:FileHandle?
    var queueState:[String:Any]=["type":"batchQueue","items":[],"enabled":false]
    var queuePulse=0.0

    func applicationDidFinishLaunching(_ notification:Notification) {
        StudioDiagnostics.shared.event("startup",["version":"1.1.0","os":ProcessInfo.processInfo.operatingSystemVersionString])
        NSApp.setActivationPolicy(.regular)
        let resources=Bundle.main.resourceURL!
        webRoot=resources.appendingPathComponent("web")
        let config=(try? JSONSerialization.jsonObject(with:Data(contentsOf:resources.appendingPathComponent("studio.json")))) as? [String:String] ?? [:]
        runtime=URL(fileURLWithPath:config["runtime"] ?? resources.appendingPathComponent("Engine").path)
        library=URL(fileURLWithPath:config["library"] ?? NSHomeDirectory()+"/Music/BandStudio")
        do{try FileManager.default.createDirectory(at:library,withIntermediateDirectories:true)}catch{notice=error.localizedDescription}
        if let data=try? Data(contentsOf:library.appendingPathComponent("setlists.json")),let lists=try? JSONDecoder().decode([StudioSetlist].self,from:data){setlists=lists}
        let menu=NSMenu();let appItem=NSMenuItem();menu.addItem(appItem);appItem.submenu=NSMenu()
        appItem.submenu!.addItem(withTitle:"À propos de BandStudio",action:#selector(about),keyEquivalent:"")
        appItem.submenu!.addItem(.separator())
        appItem.submenu!.addItem(withTitle:"Quitter BandStudio",action:#selector(NSApplication.terminate(_:)),keyEquivalent:"q")
        let file=NSMenuItem();menu.addItem(file);file.submenu=NSMenu(title:"Fichier")
        for (title,selector,key) in [("Importer un morceau",#selector(importSong),"n"),("Ouvrir un projet",#selector(openProject),"o"),("Enregistrer",#selector(saveAction),"s")] {
            let i=file.submenu!.addItem(withTitle:title,action:selector,keyEquivalent:key);i.target=self
        }
        let edit=NSMenuItem();menu.addItem(edit);edit.submenu=NSMenu(title:"Édition")
        for (title,action,key) in [("Couper","cut:","x"),("Copier","copy:","c"),("Coller","paste:","v"),("Tout sélectionner","selectAll:","a")] {
            edit.submenu!.addItem(withTitle:title,action:Selector(action),keyEquivalent:key)
        }
        NSApp.mainMenu=menu
        window=NSWindow(contentRect:NSRect(x:0,y:0,width:1360,height:900),styleMask:[.titled,.closable,.miniaturizable,.resizable],backing:.buffered,defer:false)
        window.title="BandStudio";window.minSize=NSSize(width:960,height:660)
        window.appearance=NSAppearance(named:.darkAqua);window.setFrameAutosaveName("BandStudio")
        let cfg=WKWebViewConfiguration();cfg.websiteDataStore = .nonPersistent()
        cfg.userContentController.add(self,name:"studio")
        web=WKWebView(frame:.zero,configuration:cfg);web.navigationDelegate=self
        window.contentView=web;window.center();window.makeKeyAndOrderFront(nil)
        web.loadFileURL(webRoot.appendingPathComponent("index.html"),allowingReadAccessTo:webRoot)
        NSApp.activate(ignoringOtherApps:true)
        timer=Timer.scheduledTimer(withTimeInterval:0.1,repeats:true){[weak self] _ in
            guard let s=self else{return};s.audio.tick();s.sendTransport();s.updatePhone();s.queueHeartbeat()
            if s.recorder.running && ((s.project.capture.mode=="punch" && s.audio.current()>=s.project.capture.punchEnd) || s.recorder.elapsed>=43100){s.perform{try s.stopRecord()}}
            if s.recorder.running, let error=s.recorder.error {s.notice=error.localizedDescription;try? s.stopRecord()}
        }
        if let requested=pendingProject {
            perform{try load(requested)};pendingProject=nil
        } else if let last=UserDefaults.standard.string(forKey:"project"),FileManager.default.fileExists(atPath:last) {
            do{try load(URL(fileURLWithPath:last))}catch{notice=error.localizedDescription}
        } else if let first=projectList().first, let path=first["path"] {
            do{try load(URL(fileURLWithPath:path))}catch{notice=error.localizedDescription}
        }
    }
    @objc func about() {NSApp.orderFrontStandardAboutPanel(options:[.applicationName:"BandStudio",.applicationVersion:"1.1.0 · préparation pour REAPER",.credits:NSAttributedString(string:"Stems, appels, décompte, paroles, accords et projets REAPER\nTraitement local sur ce Mac")])}
    func projectList()->[[String:String]] {
        guard let library=library else{return []}
        return ((try? FileManager.default.contentsOfDirectory(at:library,includingPropertiesForKeys:nil)) ?? [])
            .filter{$0.pathExtension == "bandstudio" && $0.resolvingSymlinksInPath().deletingLastPathComponent()==library.resolvingSymlinksInPath() && FileManager.default.fileExists(atPath:$0.appendingPathComponent("project.json").path)}.sorted{$0.lastPathComponent < $1.lastPathComponent}
            .map{url in
                var item=["name":url.deletingPathExtension().lastPathComponent,"path":url.path]
                if let data=try? Data(contentsOf:url.appendingPathComponent("project.json")),let p=(try? JSONSerialization.jsonObject(with:data)) as? [String:Any],let name=p["name"] as? String {item["name"]=name}
                if let data=try? Data(contentsOf:url.appendingPathComponent("Artwork.jpg")),data.count<=512_000 {item["artwork"]="data:image/jpeg;base64,"+data.base64EncodedString()}
                if let data=try? Data(contentsOf:url.appendingPathComponent("Artwork.json")),data.count<=128_000,let art=(try? JSONSerialization.jsonObject(with:data)) as? [String:Any] {
                    for key in ["title","artist","album","artworkStatus","artworkMessage"] {if let value=art[key] as? String {item[key]=value}}
                }
                return item
            }
    }
    func send(_ value:[String:Any]) {
        guard let web=web,let data=try? JSONSerialization.data(withJSONObject:value),let json=String(data:data,encoding:.utf8) else{return}
        web.evaluateJavaScript("window.studioReceive && window.studioReceive(\(json))",completionHandler:nil)
    }
    func sendTransport() {
        send(["type":"transport","position":recorder.running && project.capture.mode=="live" ? recorder.elapsed : audio.current(),"captureElapsed":recorder.elapsed,"meters":recorder.meters,"playing":audio.running,"recording":recorder.running,"rate":audio.rate,"pitch":audio.pitch,"loop":audio.loop,"loopStart":audio.loopStart,"loopEnd":audio.loopEnd,"mode":audio.mode,"countRemaining":audio.countRemaining()])
        if job != nil,Date.timeIntervalSinceReferenceDate-lastBroadcast > 2 {
            lastBroadcast=Date.timeIntervalSinceReferenceDate
            var progress:[String:Any]=["type":"job","name":jobName,"detail":jobDetail(),"elapsed":max(0,ProcessInfo.processInfo.systemUptime-jobStarted)]
            if let url=jobLog?.deletingLastPathComponent().appendingPathComponent("progress.json"),
               let data=try? Data(contentsOf:url),let status=(try? JSONSerialization.jsonObject(with:data)) as? [String:Any] {
                for key in ["stage","device","fallback","progress","progressLabel","progressBasis","indeterminate","passIndex","passCount","passProgress","completed","total","finished","failed"] {progress[key]=status[key]}
            }
            progress["task"]=jobKind;progress["jobID"]=jobIdentifier;progress["plan"]=jobPlan;progress["planIndex"]=jobPlanIndex
            send(progress)
        }
    }
    func jobDetail()->String {
        guard let url=jobLog,let f=try? FileHandle(forReadingFrom:url) else{return "Traitement local en cours…"}
        defer{try? f.close()}
        let end=(try? f.seekToEnd()) ?? 0;try? f.seek(toOffset:end > 2048 ? end-2048 : 0)
        let str=String(data:(try? f.readToEnd()) ?? Data(),encoding:.utf8) ?? ""
        return str.components(separatedBy:CharacterSet.newlines.union(CharacterSet(charactersIn:"\r"))).filter{!$0.isEmpty}.last ?? "Chargement du modèle…"
    }
    func sendState() {
        let object=(try? JSONSerialization.jsonObject(with:JSONEncoder().encode(project))) ?? [:]
        let lists=(try? JSONSerialization.jsonObject(with:JSONEncoder().encode(setlists))) ?? []
        let providers=ChordProvider.all.map{["id":$0.id,"publisher":$0.publisher,"domain":$0.domain,"automatic":$0.template != nil] as [String:Any]}
        send(["type":"state","project":object,"duration":project.duration,"loaded":root != nil,"library":projectList(),"analysisPlan":analysisPlan(),"trashAvailable":hasTrashedProjects(),"setlists":lists,"busy":busy,"job":jobName,"jobTask":jobKind,"jobID":jobIdentifier,"jobPlan":jobPlan,"jobPlanIndex":jobPlanIndex,"notice":notice,"undo":!history.isEmpty,"redo":!future.isEmpty,"revision":revision,"lastExport":lastExport,"guidesReady":project.guideKey==project.desiredGuideKey(),"chordProviders":providers])
        sendTransport()
    }
    func changed(invalidate:Bool=true) throws {
        if invalidate {project.preparation?.fingerprint=nil;project.preparation?.validatedAt=nil;project.structureProposal=nil}
        revision += 1;try save();sendState()
    }
    func savePlayback() throws {
        project.preparation=Preparation(rate:Double(audio.rate),pitch:Double(audio.pitch),mode:audio.mode)
        try changed()
    }
    func remember() {history.append(project);if history.count > 80{history.removeFirst()};future=[]}
    func save() throws {if let root=root {try project.save(root)}}
    @objc func saveAction(){perform{try self.save();self.notice="Projet enregistré sur ce Mac.";self.sendState()}}
    func perform(_ work:() throws -> Void) {
        let before=project,oldRoot=root,oldHistory=history,oldFuture=future,oldRevision=revision
        do{try work()}catch{
            // A rejected edit must not leave an invalid in-memory project behind.
            if project.id==before.id,root==oldRoot {
                let modified=(try? JSONEncoder().encode(project)) != (try? JSONEncoder().encode(before))
                project=before;history=oldHistory;future=oldFuture;revision=oldRevision
                if modified{try? reloadAudio();try? save()}
            }
            StudioDiagnostics.shared.event("error",["message":error.localizedDescription]);notice=error.localizedDescription;sendState()
        }
    }
    func requireIdle() throws {
        if busy || recorder.running || recordPending {throw StudioError("Termine le traitement ou la prise avant de changer de projet.")}
    }
    func load(_ url:URL,prepareGuides:Bool=true) throws {
        try requireIdle()
        var p=try StudioProject.load(url)
        if p.sectionGridVersion==1 {
            let migration=Process();migration.executableURL=runtime.appendingPathComponent(".venv/bin/python")
            migration.arguments=[runtime.appendingPathComponent("section_grid_rollback.py").path,"--rollback",url.path]
            migration.standardOutput=FileHandle.nullDevice;let errors=Pipe();migration.standardError=errors
            try migration.run();let detail=errors.fileHandleForReading.readDataToEndOfFile();migration.waitUntilExit()
            guard migration.terminationStatus==0 else {throw StudioError("La restauration des sections n’a pas abouti. "+(String(data:detail,encoding:.utf8) ?? ""))}
            p=try StudioProject.load(url)
        }
        try audio.load(p,root:url);audio.loop=false
        project=p;root=url;history=[];future=[];notice="";lastExport="";revision += 1
        audio.rate=1;audio.pitch=0;audio.stretch.pitch=0
        if let prep=p.preparation {audio.rate=Float(prep.rate);audio.pitch=Float(prep.pitch);audio.mode=prep.mode;audio.stretch.pitch=Float(prep.pitch)*100;audio.applyMix()}
        UserDefaults.standard.set(url.path,forKey:"project");sendState()
        let identity=project.id
        if prepareGuides {DispatchQueue.main.async {[weak self] in
            guard let self=self,self.project.id==identity,!self.busy,self.project.duration>0 else{return}
            self.perform{try self.withGuides{
                self.sendState()
                if !self.project.analysisDone("lyricscorrect"),FileManager.default.fileExists(atPath:self.runtime.appendingPathComponent(".venv-words/bin/python").path) {
                    try self.runAnalysis("lyricscorrect",model:"htdemucs",language:"auto")
                }
            }}
        }}
    }
    func safeName(_ raw:String)->String {
        let clean=raw.components(separatedBy:CharacterSet(charactersIn:"/:\0")).joined(separator:"-")
        return String(clean.prefix(120)).isEmpty ? "Morceau" : String(clean.prefix(120))
    }
    @objc func importSong() {chooseAudio(new:true)}
    func chooseAudio(new:Bool) {
        perform {
            try requireIdle()
            let panel=NSOpenPanel();panel.canChooseDirectories=false;panel.allowsMultipleSelection = !new
            // FFmpeg probes the file itself; do not hide uncommon supported formats by extension.
            panel.allowsOtherFileTypes=true
            panel.message=new ? "Choisis le morceau à travailler." : "Choisis les pistes à ajouter, alignées au début du morceau."
            panel.beginSheetModal(for:window){[weak self] answer in
                guard let self=self,answer == .OK else{return}
                self.importFiles(panel.urls,new:new)
            }
        }
    }
    func importFiles(_ urls:[URL],new:Bool) {
        guard !urls.isEmpty else{return}
        busy=true;audio.pause();notice="Import des fichiers audio…";sendState()
        let current=project,currentRoot=root
        let importedTitle=pendingImportTitle,importedURL=pendingSourceURL,artwork=pendingArtwork,metadata=pendingMusicMetadata
        pendingImportTitle=nil;pendingSourceURL="";pendingArtwork=nil;pendingMusicMetadata="{}"
        DispatchQueue.global(qos:.userInitiated).async {
            do {
                var p=new ? StudioProject() : current
                let dest:URL
                if new {
                    if let data=try? Data(contentsOf:self.library.appendingPathComponent("defaults.json")),let settings=try? JSONDecoder().decode(GuideSettings.self,from:data){try settings.validate();p.settings=settings}
                    p.settings=p.settings.forNewSong()
                    p.name=self.safeName(importedTitle ?? urls[0].deletingPathExtension().lastPathComponent)
                    p.sourceURL=importedURL
                    var candidate=self.library.appendingPathComponent(p.name+".bandstudio")
                    if FileManager.default.fileExists(atPath:candidate.path){candidate=self.library.appendingPathComponent(p.name+" "+String(p.id.prefix(6))+".bandstudio")}
                    dest=candidate
                } else {guard let existing=currentRoot else{throw StudioError("Importe d’abord un morceau.")};dest=existing}
                try FileManager.default.createDirectory(at:dest.appendingPathComponent("Audio"),withIntermediateDirectories:true)
                for u in urls {
                    // Decode to native PCM once: inference and playback use the same exact timeline.
                    let relative="Audio/"+UUID().uuidString+".wav"
                    let target=dest.appendingPathComponent(relative)
                    try self.decodeFile(u,to:target)
                    let (duration,peaks)=try inspectAudio(target)
                    let name=u.deletingPathExtension().lastPathComponent
                    let role=new ? "source" : Self.role(name)
                    p.tracks.append(Track(name:new ? "Original" : name,file:relative,role:role,duration:duration,peaks:peaks))
                }
                if new {_ = try? self.catalogCall(["extract",dest.path,artwork ?? urls[0].path,self.runtime.path])}
                p.preparation?.fingerprint=nil;p.preparation?.validatedAt=nil;try p.save(dest)
                if new {_ = try? self.catalogCall(["seed",dest.path,urls[0].path,self.runtime.path,metadata])}
                DispatchQueue.main.async {
                    self.busy=false
                    self.perform{
                        try self.load(dest,prepareGuides:!new)
                        if new {try self.calibrateImportedSong()}
                        else {self.notice="Pistes importées.";self.sendState()}
                    }
                }
            } catch {DispatchQueue.main.async{self.busy=false;self.notice=error.localizedDescription;self.sendState()}}
        }
    }
    static func role(_ name:String)->String {
        let n=name.lowercased()
        for (role,words) in [("drums",["drum","batterie"]),("bass",["bass","basse"]),("vocals",["vocal","chant","voix"]),("guitar",["guitar","guitare"]),("piano",["piano","clavier"])] {
            if words.contains(where:{n.contains($0)}){return role}
        };return "other"
    }
    @objc func openProject() {
        perform {
            try requireIdle();let panel=NSOpenPanel();panel.canChooseDirectories=true;panel.canChooseFiles=true
            panel.allowedFileTypes=["bandstudio","rpp"];panel.directoryURL=library;panel.message="Ouvre un projet BandStudio ou importe les pistes audio, régions et repères d’un projet REAPER."
            panel.beginSheetModal(for:window){[weak self] answer in
                guard let self=self,answer == .OK,let url=panel.url else{return}
                self.perform{if url.pathExtension.lowercased()=="rpp"{try self.importRPP(url)}else{try self.load(url)}}
            }
        }
    }
    func runAnalysis(_ kind:String,model:String,language:String="auto",quality:String="standard",reanalyze:Bool=false,chordSource:String="",completion:(() throws -> Void)?=nil) throws {
        guard ["grid","structure","separate","drumsep","lyrics","lyricscorrect","chords","drums"].contains(kind),["htdemucs","htdemucs_6s","htdemucs_ft"].contains(model) else {throw StudioError("Traitement inconnu.")}
        if !reanalyze && project.analysisDone(kind) {notice="Analyse déjà disponible et résultat protégé. Les corrections et validations sont conservées.";sendState();try completion?();return}
        if kind == "grid" && project.gridLocked {throw StudioError("Le calage est protégé. Décoche « Protéger le calage » dans Click & cues avant de relancer.")}
        let desired=["lyrics","lyricscorrect"].contains(kind) ? (project.tracks.contains{$0.role=="vocal_lead"} ? "vocal_lead" : "vocals") : (["drums","drumsep"].contains(kind) ? "drums" : "source")
        guard let root=root,let source=project.tracks.first(where:{$0.role==desired}) ?? (["drums","drumsep"].contains(kind) ? nil : project.tracks.first(where:{$0.role == "source"})) else {throw StudioError(["drums","drumsep"].contains(kind) ? "Sépare d’abord une piste batterie." : "Importe d’abord un morceau.")}
        if !chordSource.isEmpty && (kind != "chords" || project.chordReference?.sources.contains(where:{$0.url==chordSource}) != true) {throw StudioError("Choisis une grille trouvée pour ce morceau.")}
        try startJob(kind,input:project.audioURL(source,root:root),arguments:["--model",model,"--language",language,"--quality",quality]+(reanalyze ? ["--reanalyze"] : [])+(chordSource.isEmpty ? [] : ["--chord-source",chordSource])) {result in
            if ["lyrics","lyricscorrect","chords","drums"].contains(kind) {try self.applyTextAnalysis(kind == "lyricscorrect" ? "lyrics" : kind,result:result)}
            else{try self.applyAnalysis(kind,result:result,reanalyze:reanalyze);self.notice="Analyse terminée. Vérifie les nouvelles propositions à l’écoute."}
            try completion?()
        }
    }
    func applyAnalysis(_ kind:String,result:URL,reanalyze:Bool=false) throws {
        guard let root=root else{return}
        let data=try Data(contentsOf:result)
        let object=try JSONSerialization.jsonObject(with:data) as? [String:Any] ?? [:]
        remember()
        if kind == "grid" {
            project.applyDetectedGrid(object,offset:project.tracks.first(where:{$0.role=="source"})?.offset ?? 0,reanalyze:reanalyze)
            audio.pause();try reloadAudio()
        } else if kind == "structure" {
            let raw=try JSONSerialization.data(withJSONObject:object["sections"] ?? [])
            project.applySections(try JSONDecoder().decode([Section].self,from:raw))
        } else {
            var newTracks:[Track]=[]
            let names=["vocals":"Chant","drums":"Batterie","bass":"Basse","guitar":"Guitare","piano":"Piano","other":"Autres instruments","drum_kick":"Grosse caisse","drum_snare":"Caisse claire","drum_toms":"Toms","drum_cymbals":"Cymbales et charleston"]
            for item in object["tracks"] as? [[String:String]] ?? [] {
                guard let path=item["path"],let role=item["role"] else{continue}
                let source=URL(fileURLWithPath:path).resolvingSymlinksInPath()
                guard source.path.hasPrefix(result.deletingLastPathComponent().resolvingSymlinksInPath().path+"/") else {throw StudioError("Résultat audio invalide.")}
                let relative="Audio/"+UUID().uuidString+"-"+role+".wav"
                try FileManager.default.copyItem(at:source,to:root.appendingPathComponent(relative))
                let (duration,peaks)=try inspectAudio(root.appendingPathComponent(relative))
                var track=Track(name:names[role] ?? role,file:relative,role:role,duration:duration,offset:kind == "drumsep" ? (project.tracks.first(where:{$0.role=="drums"})?.offset ?? 0) : 0,peaks:peaks)
                if kind=="drumsep",let parent=project.tracks.first(where:{$0.role=="drums"}){track.gain=parent.gain;track.pan=parent.pan;track.muted=parent.muted}
                if kind=="drumsep",let old=project.tracks.first(where:{$0.role==role}){track.id=old.id;track.gain=old.gain;track.pan=old.pan;track.muted=old.muted;track.solo=old.solo}
                newTracks.append(track)
            }
            guard !newTracks.isEmpty else{throw StudioError("Aucune piste produite.")}
            if kind=="drumsep",Set(newTracks.map(\.role)) != Set(["drum_kick","drum_snare","drum_toms","drum_cymbals"]) {throw StudioError("Séparation de batterie incomplète.")}
            if kind == "drumsep" {project.tracks=project.tracks.filter{!$0.role.hasPrefix("drum_")}+newTracks}
            else {project.tracks=project.tracks.filter{$0.role == "source" || $0.role == "take" || $0.role.hasPrefix("guide_")}+newTracks}
            try audio.load(project,root:root);audio.mode="mix";audio.applyMix()
        }
        project.analysisCompleted(kind)
        try changed()
    }
    func exportAudio() throws {
        try requireIdle();guard root != nil else{return};audio.pause()
        let panel=NSSavePanel();panel.allowedFileTypes=["wav"];panel.nameFieldStringValue=project.name+" - mix.wav"
        panel.beginSheetModal(for:window){[weak self] answer in
            guard let self=self,answer == .OK,let url=panel.url else{return}
            self.busy=true;self.notice="Export du mix…";self.sendState()
            let start=self.audio.loop ? self.audio.loopStart : 0,end=self.audio.loop ? self.audio.loopEnd : self.project.duration
            DispatchQueue.global(qos:.userInitiated).async {
                let temporary=url.deletingLastPathComponent().appendingPathComponent(".bandstudio-export-"+UUID().uuidString+".wav")
                defer{try? FileManager.default.removeItem(at:temporary)}
                do{try self.audio.render(to:temporary,start:start,end:end,includeCount:self.project.settings.exportCount)
                    if FileManager.default.fileExists(atPath:url.path) {
                        _ = try FileManager.default.replaceItemAt(url,withItemAt:temporary)
                    } else {try FileManager.default.moveItem(at:temporary,to:url)}
                    DispatchQueue.main.async{self.busy=false;self.notice="Export audio terminé.";self.sendState()}
                }catch{DispatchQueue.main.async{self.busy=false;self.notice=error.localizedDescription;self.sendState()}}
            }
        }
    }
    func exportCues() throws {
        guard root != nil else{return}
        let panel=NSSavePanel();panel.allowedFileTypes=["csv"];panel.nameFieldStringValue=project.name+" - repères.csv"
        panel.beginSheetModal(for:window){[weak self] result in
            guard let self=self,result == .OK,let url=panel.url else{return}
            self.perform {
                func q(_ s:String)->String {"\""+s.replacingOccurrences(of:"\"",with:"\"\"")+"\""}
                var rows=["type,debut_secondes,fin_secondes,nom"]
                rows += self.project.sections.map{"section,\($0.start),\($0.end),"+q($0.name)}
                rows += self.project.cues.map{"cue,\($0.time),\($0.time),"+q($0.name)}
                try rows.joined(separator:"\n").write(to:url,atomically:true,encoding:.utf8)
                self.notice="Repères exportés.";self.sendState()
            }
        }
    }
    func userContentController(_ controller:WKUserContentController,didReceive message:WKScriptMessage) {
        guard message.frameInfo.isMainFrame,message.frameInfo.request.url?.standardizedFileURL.path == webRoot.appendingPathComponent("index.html").standardizedFileURL.path,
              let m=message.body as? [String:Any],let command=m["command"] as? String else{return}
        let args=m["args"] as? [String:Any] ?? [:]
        if command == "batchQueue" {perform{try queueCommand(args)};return}
        if supportCommand(command,args){return}
        if command != "ready" {StudioDiagnostics.shared.event("command",["command":command,"playing":audio.running,"position":audio.current(),"busy":busy])}
        perform {
            if command == "artwork" {try artworkCommand(args);return}
            if command == "ready" {sendState();sendUpdate();try startQueue();send(queueState);if automaticUpdates{checkUpdates()};return}
            if command == "import" {importSong();return}
            if command == "open" {openProject();return}
            if ["bandpilot","bridge","studioControl","record","newSession","captureSettings"].contains(command) {
                throw StudioError("BandStudio prépare les morceaux. L’enregistrement se poursuit dans REAPER.")
            }
            if command == "audioSettings" {NSWorkspace.shared.open(URL(string:"x-apple.systempreferences:com.apple.Sound-Settings.extension")!);return}
            if ["renameProject","deleteProject","restoreProject","projectArtwork"].contains(command) {try catalogCommand(command,args);return}
            if command == "library" {
                guard let path=args["path"] as? String,projectList().contains(where:{$0["path"] == path}) else{return}
                try load(URL(fileURLWithPath:path));return
            }
            guard m["projectID"] as? String == project.id else {throw StudioError("Le projet a changé. Recommence ton action.")}
            if command == "chordSourceOpen" {
                guard let link=args["url"] as? String,project.chordReference?.sources.contains(where:{$0.url==link}) == true,
                      let url=URL(string:link),url.scheme=="https",url.host != nil,url.user==nil,url.password==nil else{throw StudioError("Source d’accords invalide.")}
                guard NSWorkspace.shared.open(url) else{throw StudioError("Impossible d’ouvrir la grille.")};return
            }
            if command == "referenceSearch" {
                guard root != nil,let kind=args["kind"] as? String,["chords","lyrics"].contains(kind),
                      let query=args["query"] as? String,!query.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty else{throw StudioError("Précise le titre du morceau.")}
                let target=try ChordProvider.searchURL(query:query,kind:kind,provider:args["provider"] as? String ?? "")
                guard NSWorkspace.shared.open(target) else{throw StudioError("Impossible d’ouvrir le navigateur.")}
                return
            }
            if command == "cancel" {transportGeneration += 1;job?.terminate();job=nil;return}
            if command == "reveal" {if let root=root{NSWorkspace.shared.activateFileViewerSelecting([root])};return}
            if busy && job == nil {throw StudioError("Patiente pendant l’import ou l’export audio.")}
            if busy && !["stop","seek","play","loop","showExport","save"].contains(command) {
                throw StudioError("Termine ou annule le traitement avant de modifier la préparation.")
            }
            if recordPending && !["stop","studioControl"].contains(command) {throw StudioError("Termine l’autorisation du microphone avant de continuer.")}
            if recorder.running && !["stop","record","studioControl"].contains(command) {throw StudioError("Arrête la prise avant cette modification.")}
            switch command {
            case "creative":try creativeTask(args)
            case "captureSettings":try setCapture(args)
            case "newSession":try newSession(args["name"] as? String ?? "Répétition")

            case "play":if audio.running{audio.pause()}else{transportOrigin=audio.position;try withGuides(afterPreparation{try self.audio.play()})}
            case "stop":transportGeneration += 1;recordPending=false;recordRequest="";if recorder.running{try stopRecord()}else{audio.pause();audio.position=audio.loop ? audio.loopStart : 0}
            case "record":if recorder.running{try stopRecord()}else if project.capture.mode=="live"{try startRecord()}else{try withGuides(afterPreparation{try self.startRecord()})}
            case "seek":try audio.seek(number(args,"time",range:0...project.duration))
            case "rate":
                let r=try number(args,"value",range:0.5...1.5);let pos=audio.current(),playing=audio.running
                audio.pause();audio.position=pos;audio.rate=Float(r);try savePlayback();if playing{try audio.play()}
            case "pitch":
                let value=try number(args,"value",range:-12...12);audio.pitch=Float(value);audio.configureTimeEffects();try savePlayback()
            case "mode":
                guard let mode=args["value"] as? String,Listening.valid(mode) else{return}
                if mode == "original" && !project.tracks.contains(where:{$0.role == "source"}){throw StudioError("Ce projet ne contient pas de piste originale.")}
                if mode != "original" && !project.tracks.contains(where:{$0.role != "source"}){throw StudioError("Sépare les instruments ou ajoute des pistes pour utiliser le mix.")}
                if let instrument=Listening.target(mode),!project.tracks.contains(where:{Listening.matches($0.role,instrument)}){throw StudioError("Sépare cet instrument ou ajoute sa piste avant d’utiliser ce mode.")}
                audio.mode=mode;audio.applyMix();try savePlayback()
            case "loop":try audio.configureLoop(on:args["on"] as? Bool ?? false,start:number(args,"start",range:0...project.duration),end:number(args,"end",range:0...project.duration))
            case "track":
                guard let id=args["id"] as? String,let index=project.tracks.firstIndex(where:{$0.id == id}) else{return}
                remember()
                if let name=args["name"] as? String,!name.isEmpty{project.tracks[index].name=String(name.prefix(120))}
                if args["gain"] != nil{project.tracks[index].gain=Float(try number(args,"gain",range:0...2))}
                if args["pan"] != nil{project.tracks[index].pan=Float(try number(args,"pan",range:-1...1))}
                if let muted=args["muted"] as? Bool{project.tracks[index].muted=muted}
                if let solo=args["solo"] as? Bool{project.tracks[index].solo=solo}
                if args["offset"] != nil {
                    project.tracks[index].offset=try number(args,"offset",range:-120...43200)
                    try project.validate();try reloadAudio()
                }
                if let role=args["role"] as? String,["drums","drum_kick","drum_snare","drum_toms","drum_cymbals","vocal_lead","vocal_backing","bass","vocals","guitar","piano","other","take"].contains(role),project.tracks[index].role != "source"{project.tracks[index].role=role}
                audio.project=project;audio.applyMix();try changed()
            case "section":
                let start=try number(args,"start",range:0...project.duration),end=try number(args,"end",range:0...project.duration)
                guard end > start,let name=args["name"] as? String,!name.trimmingCharacters(in:.whitespaces).isEmpty else {throw StudioError("Donne un nom et une plage valide à la section.")}
                let id=args["id"] as? String ?? UUID().uuidString
                guard !project.sections.contains(where:{$0.id != id && $0.start < end && $0.end > start}) else{throw StudioError("Cette section chevauche une autre section. Ajuste ses limites.")}
                remember();project.sections.removeAll{$0.id == id}
                project.sections.append(Section(id:id,start:start,end:end,name:String(name.prefix(120)),locked:args["locked"] as? Bool ?? true,origin:"manual",callText:args["callText"] as? String,announce:args["announce"] as? Bool))
                project.sections.sort{$0.start < $1.start};try changed()
            case "deleteSection":remember();project.sections.removeAll{$0.id == args["id"] as? String};try changed()
            case "splitSection","mergeSection":try editStructure(command,args:args)
            case "cue":
                let time=try number(args,"time",range:0...project.duration)
                guard let name=args["name"] as? String,!name.isEmpty else{return}
                remember();let id=args["id"] as? String ?? UUID().uuidString;project.cues.removeAll{$0.id == id}
                project.cues.append(Cue(id:id,time:time,name:String(name.prefix(160)),callText:args["callText"] as? String,announce:args["announce"] as? Bool));project.cues.sort{$0.time < $1.time};try changed()
            case "deleteCue":remember();project.cues.removeAll{$0.id == args["id"] as? String};try changed()
            case "notes":remember();project.notes=String((args["value"] as? String ?? "").prefix(20000));try changed()
            case "save":try save();notice="Projet enregistré.";sendState()
            case "undo","redo":
                try requireIdle()
                if command == "undo",let previous=history.popLast(){future.append(project);project=previous}
                if command == "redo",let next=future.popLast(){history.append(project);project=next}
                if let root=root{try audio.load(project,root:root)};try changed()
            case "addTracks":chooseAudio(new:false)
            case "prepareAll":try prepareAll(args)
            case "analyze":try runAnalysis(args["kind"] as? String ?? "grid",model:args["model"] as? String ?? "htdemucs",language:args["language"] as? String ?? "auto",quality:args["quality"] as? String ?? "standard",reanalyze:args["reanalyze"] as? Bool == true,chordSource:args["sourceURL"] as? String ?? "")
            case "export":try withGuides{try self.exportAudio()}
            case "exportCues":try exportCues()
            case "guideMix":try guideMix(args)
            case "moveMarker","reviewMarker":try editMarker(args,review:command=="reviewMarker")
            case "audition":
                let start=try number(args,"start",range:0...project.duration),end=try number(args,"end",range:0...project.duration)
                guard end>start+0.05 else{throw StudioError("Choisis un passage à écouter.")}
                audio.pause();audio.loop=true;audio.loopStart=start;audio.loopEnd=end;audio.position=start
                try withGuides(afterPreparation{try self.audio.play(withCount:false)})
            case "settings":try settingsCommand(args)
            case "saveDefaults":
                try JSONEncoder().encode(project.settings).write(to:library.appendingPathComponent("defaults.json"),options:.atomic)
                notice="Les futurs imports utiliseront les réglages actuels de ce morceau.";sendState()
            case "setlist":try updateSetlist(args)
            case "drumHit":try editDrum(args)
            case "deleteTrack":
                guard let id=args["id"] as? String,let t=project.tracks.first(where:{$0.id==id}),!t.role.hasPrefix("guide_") else{return}
                guard project.tracks.filter({!$0.role.hasPrefix("guide_")}).count>1 else{throw StudioError("Conserve au moins une piste audio dans le morceau.")}
                remember();project.tracks.removeAll{$0.id==id}
                project.sections=project.sections.compactMap{s in var x=s;x.end=min(x.end,self.project.duration);return x.start<x.end ? x:nil}
                project.cues.removeAll{$0.time>self.project.duration};project.beats.removeAll{$0>self.project.duration}
                project.lyrics.removeAll{$0.end>self.project.duration};project.chords.removeAll{$0.end>self.project.duration};project.drumHits.removeAll{$0.time>self.project.duration}
                try reloadAudio();try changed()
            case "guides":try requireIdle();audio.pause();try withGuides(force:true){self.notice="Les guides ont été recalculés.";self.sendState()}
            case "validateProject":
                guard args["reviewed"] as? Bool == true else {throw StudioError("Confirme l’écoute et les repères dans Valider & envoyer.")}
                try validatePreparation()
            case "reviewStructure":try reviewStructure(args)
            case "dismissStructure":
                try requireIdle()
                guard let proposal=project.structureProposal,args["proposalID"] as? String == proposal.id else {throw StudioError("Cette proposition n’est plus disponible.")}
                if let root=root {try StudioLearning.keepStructure(root,proposal)}
                project.structureProposal=nil;try changed(invalidate:false);notice="Parcours actuel conservé."
            case "exportStructure":try exportStructure(args)
            case "applyStructure":try applyStructure(args)
            case "reaper":try exportRPP(open:args["open"] as? Bool ?? false)
            case "showExport":if !lastExport.isEmpty{NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath:lastExport)])}
            case "annotation":try annotation(args)
            case "studioTask":try advancedTask(args)
            case "musicSettings":try musicSettings(args)
            case "phone":try phoneCommand(args)
            case "midi":try startJob("midi"){result in
                let obj=try JSONSerialization.jsonObject(with:Data(contentsOf:result)) as? [String:Any] ?? [:]
                self.lastExport=obj["path"] as? String ?? "";self.notice="Fichier MIDI de batterie créé. Afficher l’export permet de le retrouver."
            }
            default:break
            }
            sendTransport()
        }
    }
    func number(_ args:[String:Any],_ key:String,range:ClosedRange<Double>) throws -> Double {
        guard let value=args[key] as? Double,value.isFinite,range.contains(value) else{throw StudioError("Valeur invalide : "+key)};return value
    }
    func webView(_ webView:WKWebView,didFinish navigation:WKNavigation!){sendState()}
    func webView(_ webView:WKWebView,decidePolicyFor action:WKNavigationAction,decisionHandler:@escaping(WKNavigationActionPolicy)->Void) {
        let allowed=action.request.url?.standardizedFileURL.path == webRoot.appendingPathComponent("index.html").standardizedFileURL.path
        decisionHandler(allowed ? .allow : .cancel)
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender:NSApplication)->Bool{true}
    func application(_ application:NSApplication,open urls:[URL]) {
        guard let url=urls.first, url.isFileURL,url.pathExtension=="bandstudio" else{return}
        if window == nil{pendingProject=url}else{perform{try load(url)}}
    }
    func applicationShouldTerminate(_ sender:NSApplication)->NSApplication.TerminateReply {
        if recorder.running {do{try stopRecord()}catch{notice=error.localizedDescription;sendState();return .terminateCancel}}
        if busy {
            let alert=NSAlert();alert.messageText="Un traitement est en cours";alert.informativeText="Arrêter le traitement et quitter ? Le projet enregistré sera conservé."
            alert.addButton(withTitle:"Continuer à travailler");alert.addButton(withTitle:"Arrêter et quitter")
            if alert.runModal() != .alertSecondButtonReturn{return .terminateCancel}
        }
        do{try save()}catch{notice=error.localizedDescription;sendState();return .terminateCancel}
        return .terminateNow
    }
    func applicationWillTerminate(_ notification:Notification){quitting=true;closeQueue();applyUpdateAfterExit();timer?.invalidate();audio.pause();job?.terminate();phoneProcess?.terminate()}
}
