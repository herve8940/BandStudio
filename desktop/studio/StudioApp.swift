import AppKit
import WebKit
import AVFoundation

final class Recorder {
    let engine=AVAudioEngine()
    var files:[AVAudioFile]=[]
    var paths:[URL]=[]
    private var lastError:Error?
    private let errorLock=NSLock()
    private let pending=DispatchSemaphore(value:16)
    var error:Error? {
        get {errorLock.lock();defer{errorLock.unlock()};return lastError}
        set {errorLock.lock();lastError=newValue;errorLock.unlock()}
    }
    let queue=DispatchQueue(label:"studio.recording")
    var running=false
    func start(root:URL) throws {
        let input=engine.inputNode,format=engine.inputNode.outputFormat(forBus:0)
        guard format.sampleRate > 0,format.channelCount > 0,format.channelCount <= 32 else {
            throw StudioError("Aucune entrée audio disponible. Choisis le périphérique d’entrée dans les réglages Son du Mac.")
        }
        paths=[];files=[];error=nil
        let mono=AVAudioFormat(standardFormatWithSampleRate:format.sampleRate,channels:1)!
        for ch in 0..<Int(format.channelCount) {
            let url=root.appendingPathComponent("Audio/prise-\(UUID().uuidString)-\(ch+1).caf")
            paths.append(url);files.append(try AVAudioFile(forWriting:url,settings:mono.settings))
        }
        input.installTap(onBus:0,bufferSize:2048,format:format){[weak self] buffer,_ in
            guard let self=self else{return}
            guard self.pending.wait(timeout:.now()) == .success else {
                self.error=StudioError("Le disque ne suit pas l’enregistrement. La prise a été arrêtée pour éviter une perte silencieuse.");return
            }
            // Copy before returning from the tap; AVAudioEngine reuses its buffers.
            var copies:[AVAudioPCMBuffer]=[]
            for ch in 0..<Int(format.channelCount) {
                guard let b=AVAudioPCMBuffer(pcmFormat:mono,frameCapacity:buffer.frameLength),
                      let src=buffer.floatChannelData?[ch],let dst=b.floatChannelData?[0] else{self.pending.signal();return}
                b.frameLength=buffer.frameLength;dst.update(from:src,count:Int(buffer.frameLength));copies.append(b)
            }
            self.queue.async {
                defer{self.pending.signal()}
                do {for (i,b) in copies.enumerated() where i < self.files.count{try self.files[i].write(from:b)}}
                catch{self.error=error}
            }
        }
        do {try engine.start();running=true}
        catch{input.removeTap(onBus:0);throw error}
    }
    func stop() throws -> [URL] {
        guard running else{return []}
        engine.inputNode.removeTap(onBus:0);engine.stop();running=false
        queue.sync {files=[]}
        // Finalized files remain available even if a disk/overload error stopped capture.
        return paths
    }
}

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
    var jobLog:URL?
    var notice=""
    var history:[StudioProject]=[]
    var future:[StudioProject]=[]
    var revision=0
    var recordingStart=0.0
    var recordPending=false
    var pendingImportTitle:String?
    var pendingSourceURL=""
    var lastExport=""
    var setlists:[StudioSetlist]=[]
    var pendingProject:URL?
    var timer:Timer?
    var lastBroadcast=0.0
    var quitting=false

    func applicationDidFinishLaunching(_ notification:Notification) {
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
            guard let s=self else{return};s.audio.tick();s.sendTransport()
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
    @objc func about() {NSApp.orderFrontStandardAboutPanel(options:[.applicationName:"BandStudio",.applicationVersion:"0.2 · atelier autonome",.credits:NSAttributedString(string:"Stems, appels, décompte, paroles, accords et projets REAPER\nTraitement local sur ce Mac")])}
    func projectList()->[[String:String]] {
        guard let library=library else{return []}
        return ((try? FileManager.default.contentsOfDirectory(at:library,includingPropertiesForKeys:nil)) ?? [])
            .filter{$0.pathExtension == "bandstudio"}.sorted{$0.lastPathComponent < $1.lastPathComponent}
            .map{["name":$0.deletingPathExtension().lastPathComponent,"path":$0.path]}
    }
    func send(_ value:[String:Any]) {
        guard let web=web,let data=try? JSONSerialization.data(withJSONObject:value),let json=String(data:data,encoding:.utf8) else{return}
        web.evaluateJavaScript("window.studioReceive && window.studioReceive(\(json))",completionHandler:nil)
    }
    func sendTransport() {
        send(["type":"transport","position":audio.current(),"playing":audio.running,"recording":recorder.running,"rate":audio.rate,"pitch":audio.pitch,"loop":audio.loop,"loopStart":audio.loopStart,"loopEnd":audio.loopEnd,"mode":audio.mode,"countRemaining":audio.countRemaining()])
        if job != nil,Date.timeIntervalSinceReferenceDate-lastBroadcast > 2 {
            lastBroadcast=Date.timeIntervalSinceReferenceDate
            send(["type":"job","name":jobName,"detail":jobDetail()])
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
        send(["type":"state","project":object,"duration":project.duration,"loaded":root != nil,"library":projectList(),"setlists":lists,"busy":busy,"job":jobName,"notice":notice,"undo":!history.isEmpty,"redo":!future.isEmpty,"revision":revision,"lastExport":lastExport,"guidesReady":project.guideKey==project.desiredGuideKey()])
        sendTransport()
    }
    func changed() throws {revision += 1;try save();sendState()}
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
            notice=error.localizedDescription;sendState()
        }
    }
    func requireIdle() throws {
        if busy || recorder.running || recordPending {throw StudioError("Termine le traitement ou la prise avant de changer de projet.")}
    }
    func load(_ url:URL) throws {
        try requireIdle()
        let p=try StudioProject.load(url)
        try audio.load(p,root:url);audio.loop=false
        project=p;root=url;history=[];future=[];notice="";lastExport="";revision += 1
        UserDefaults.standard.set(url.path,forKey:"project");sendState()
        let identity=project.id
        DispatchQueue.main.async {[weak self] in
            guard let self=self,self.project.id==identity,!self.busy else{return}
            self.perform{try self.withGuides{self.sendState()}}
        }
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
        let importedTitle=pendingImportTitle,importedURL=pendingSourceURL
        pendingImportTitle=nil;pendingSourceURL=""
        DispatchQueue.global(qos:.userInitiated).async {
            do {
                var p=new ? StudioProject() : current
                let dest:URL
                if new {
                    if let data=try? Data(contentsOf:self.library.appendingPathComponent("defaults.json")),let settings=try? JSONDecoder().decode(GuideSettings.self,from:data){try settings.validate();p.settings=settings}
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
                try p.save(dest)
                DispatchQueue.main.async {
                    self.busy=false
                    self.perform{try self.load(dest);self.notice="Import terminé. Tu peux écouter le morceau ou lancer sa préparation.";self.sendState()}
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
    func runAnalysis(_ kind:String,model:String,language:String="auto",quality:String="standard") throws {
        guard ["grid","structure","separate","lyrics","chords","drums"].contains(kind),["htdemucs","htdemucs_6s","htdemucs_ft"].contains(model) else {throw StudioError("Traitement inconnu.")}
        let desired=kind == "lyrics" ? "vocals" : (kind == "drums" ? "drums" : "source")
        guard let root=root,let source=project.tracks.first(where:{$0.role==desired}) ?? (kind == "drums" ? nil : project.tracks.first(where:{$0.role == "source"})) else {throw StudioError(kind == "drums" ? "Sépare d’abord une piste batterie." : "Importe d’abord un morceau.")}
        try startJob(kind,input:project.audioURL(source,root:root),arguments:["--model",model,"--language",language,"--quality",quality]) {result in
            if ["lyrics","chords","drums"].contains(kind) {try self.applyTextAnalysis(kind,result:result)}
            else{try self.applyAnalysis(kind,result:result);self.notice="Analyse terminée. Les corrections manuelles sont conservées."}
        }
    }
    func applyAnalysis(_ kind:String,result:URL) throws {
        guard let root=root else{return}
        let data=try Data(contentsOf:result)
        let object=try JSONSerialization.jsonObject(with:data) as? [String:Any] ?? [:]
        remember()
        if kind == "grid" {
            project.bpm=object["bpm"] as? Double ?? 0;project.beats=object["beats"] as? [Double] ?? []
        } else if kind == "structure" {
            let raw=try JSONSerialization.data(withJSONObject:object["sections"] ?? [])
            project.applySections(try JSONDecoder().decode([Section].self,from:raw))
        } else {
            var newTracks:[Track]=[]
            let names=["vocals":"Chant","drums":"Batterie","bass":"Basse","guitar":"Guitare","piano":"Piano","other":"Autres instruments"]
            for item in object["tracks"] as? [[String:String]] ?? [] {
                guard let path=item["path"],let role=item["role"] else{continue}
                let source=URL(fileURLWithPath:path).resolvingSymlinksInPath()
                guard source.path.hasPrefix(result.deletingLastPathComponent().resolvingSymlinksInPath().path+"/") else {throw StudioError("Résultat audio invalide.")}
                let relative="Audio/"+UUID().uuidString+"-"+role+".wav"
                try FileManager.default.copyItem(at:source,to:root.appendingPathComponent(relative))
                let (duration,peaks)=try inspectAudio(root.appendingPathComponent(relative))
                newTracks.append(Track(name:names[role] ?? role,file:relative,role:role,duration:duration,peaks:peaks))
            }
            guard !newTracks.isEmpty else{throw StudioError("Aucune piste produite.")}
            project.tracks=project.tracks.filter{$0.role == "source" || $0.role == "take" || $0.role.hasPrefix("guide_")}+newTracks
            try audio.load(project,root:root);audio.mode="mix";audio.applyMix()
        }
        try changed()
    }
    func startRecord() throws {
        try requireIdle();guard root != nil else{throw StudioError("Ouvre d’abord un projet.")}
        guard audio.rate == 1,audio.pitch == 0,!audio.loop else{throw StudioError("Pour enregistrer, remets la vitesse à 100 %, la tonalité à 0 et désactive la boucle.")}
        recordPending=true
        AVCaptureDevice.requestAccess(for:.audio){[weak self] granted in
            DispatchQueue.main.async {
                guard let self=self else{return}
                self.recordPending=false
                if !granted{self.notice="Autorise le microphone pour BandStudio dans Réglages Système → Confidentialité et sécurité.";self.sendState();return}
                self.perform {
                    guard let root=self.root else{return}
                    self.recordingStart=self.audio.current()-(self.audio.running ? 0 : self.audio.plannedCount(at:self.audio.current()));try self.recorder.start(root:root)
                    do {if !self.audio.running{try self.audio.play()}}
                    catch { _ = try? self.recorder.stop();throw error }
                    self.notice="Enregistrement des entrées audio du Mac. Le retour logiciel est désactivé.";self.sendState()
                }
            }
        }
    }
    func stopRecord() throws {
        audio.pause()
        let paths=try recorder.stop();guard let root=root else{return}
        remember()
        for (i,url) in paths.enumerated() {
            let (duration,peaks)=try inspectAudio(url)
            project.tracks.append(Track(name:"Prise · entrée \(i+1)",file:"Audio/"+url.lastPathComponent,role:"take",duration:duration,offset:recordingStart,peaks:peaks))
        }
        try audio.load(project,root:root);audio.mode="mix";audio.applyMix()
        notice=recorder.error?.localizedDescription ?? "Prise enregistrée. Ajuste son départ si ton périphérique ajoute un décalage."
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
        perform {
            if command == "ready" {sendState();return}
            if command == "import" {importSong();return}
            if command == "open" {openProject();return}
            if command == "bandpilot" {
                guard FileManager.default.fileExists(atPath:"/Applications/BandPilot.app") else{throw StudioError("BandPilot n’est pas installé dans Applications.")}
                NSWorkspace.shared.open(URL(fileURLWithPath:"/Applications/BandPilot.app"));return
            }
            if command == "audioSettings" {NSWorkspace.shared.open(URL(string:"x-apple.systempreferences:com.apple.Sound-Settings.extension")!);return}
            if command == "link" {try importURL(args["url"] as? String ?? "");return}
            if command == "library" {
                guard let path=args["path"] as? String,projectList().contains(where:{$0["path"] == path}) else{return}
                try load(URL(fileURLWithPath:path));return
            }
            guard m["projectID"] as? String == project.id else {throw StudioError("Le projet a changé. Recommence ton action.")}
            if command == "cancel" {job?.terminate();job=nil;return}
            if command == "reveal" {if let root=root{NSWorkspace.shared.activateFileViewerSelecting([root])};return}
            if busy && job == nil {throw StudioError("Patiente pendant l’import ou l’export audio.")}
            if recordPending {throw StudioError("Termine l’autorisation du microphone avant de continuer.")}
            if recorder.running && !["stop","record"].contains(command) {throw StudioError("Arrête la prise avant cette modification.")}
            switch command {
            case "play":if audio.running{audio.pause()}else{try withGuides{try self.audio.play()}}
            case "stop":if recorder.running{try stopRecord()}else{audio.pause();audio.position=audio.loop ? audio.loopStart : 0}
            case "record":if recorder.running{try stopRecord()}else{try withGuides{try self.startRecord()}}
            case "seek":try audio.seek(number(args,"time",range:0...project.duration))
            case "rate":
                let r=try number(args,"value",range:0.5...1.5);let pos=audio.current(),playing=audio.running
                audio.pause();audio.position=pos;audio.rate=Float(r);if playing{try audio.play()}
            case "pitch":
                let value=try number(args,"value",range:-12...12);audio.pitch=Float(value);audio.stretch.pitch=Float(value)*100
            case "mode":
                guard let mode=args["value"] as? String,["original","mix","drums","minus"].contains(mode) else{return}
                if mode == "original" && !project.tracks.contains(where:{$0.role == "source"}){throw StudioError("Ce projet ne contient pas de piste originale.")}
                if mode != "original" && !project.tracks.contains(where:{$0.role != "source"}){throw StudioError("Sépare les instruments ou ajoute des pistes pour utiliser le mix.")}
                if ["drums","minus"].contains(mode) && !project.tracks.contains(where:{$0.role == "drums"}){throw StudioError("Sépare les instruments ou ajoute une piste batterie.")}
                audio.mode=mode;audio.applyMix()
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
                if let role=args["role"] as? String,["drums","bass","vocals","guitar","piano","other","take"].contains(role),project.tracks[index].role != "source"{project.tracks[index].role=role}
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
            case "analyze":try runAnalysis(args["kind"] as? String ?? "grid",model:args["model"] as? String ?? "htdemucs",language:args["language"] as? String ?? "auto",quality:args["quality"] as? String ?? "standard")
            case "export":try withGuides{try self.exportAudio()}
            case "exportCues":try exportCues()
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
            case "guides":try withGuides{self.notice="Les guides sont à jour.";self.sendState()}
            case "reaper":try exportRPP()
            case "showExport":if !lastExport.isEmpty{NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath:lastExport)])}
            case "annotation":try annotation(args)
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
    func applicationWillTerminate(_ notification:Notification){quitting=true;timer?.invalidate();audio.pause();job?.terminate()}
}
