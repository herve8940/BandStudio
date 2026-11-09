import Foundation
import Darwin

// Opt-in, owner-only local mailbox. No network listener and no arbitrary commands or paths.
extension StudioApp {
    func setBridge(_ on:Bool) throws {
        if !on {
            if let folder=bridgeFolder{try? FileManager.default.removeItem(at:folder.appendingPathComponent("state.json"))}
            bridgeFolder=nil;if bridgeLock>=0{flock(bridgeLock,LOCK_UN);close(bridgeLock);bridgeLock = -1};sendState();return
        }
        guard bridgeFolder==nil else{return}
        let folder=URL(fileURLWithPath:NSHomeDirectory()).appendingPathComponent("Library/Application Support/BandStudio/Bridge")
        try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
        let fd=open(folder.appendingPathComponent("owner.lock").path,O_CREAT|O_RDWR,0o600)
        guard fd>=0 else{throw StudioError("Impossible de créer la connexion locale.")}
        guard flock(fd,LOCK_EX|LOCK_NB)==0 else{close(fd);throw StudioError("Une autre fenêtre BandStudio utilise déjà la connexion BandPilot.")}
        bridgeLock=fd;bridgeFolder=folder;bridgeSession=UUID().uuidString;bridgePulse=0;bridgeProcessed=[]
        for url in (try? FileManager.default.contentsOfDirectory(at:folder,includingPropertiesForKeys:nil)) ?? [] where url.lastPathComponent.hasPrefix("request-") || url.lastPathComponent.hasPrefix("response-"){try? FileManager.default.removeItem(at:url)}
        updateBridge();notice="BandPilot peut maintenant piloter ce lecteur et ses prises sur ce Mac.";sendState()
    }
    func bridgeState()->[String:Any] {
        return ["version":1,"session":bridgeSession,"updated":Date().timeIntervalSince1970,"projectID":project.id,"name":project.name,"loaded":root != nil,"duration":project.duration,"position":recorder.running && project.capture.mode=="live" ? recorder.elapsed : audio.current(),"playing":audio.running,"recording":recorder.running,"pending":recordPending,"busy":busy,"notice":notice,"rate":audio.rate,"pitch":audio.pitch,"loop":audio.loop,"loopStart":audio.loopStart,"loopEnd":audio.loopEnd,"capture":captureState(),"sections":project.sections.map{["name":$0.name,"start":$0.start,"end":$0.end] as [String:Any]},"cues":project.cues.map{["name":$0.name,"time":$0.time] as [String:Any]}]
    }
    func updateBridge() {
        guard let folder=bridgeFolder else{return}
        let now=Date().timeIntervalSince1970
        if now-bridgePulse>=0.25 {
            bridgePulse=now
            if let data=try? JSONSerialization.data(withJSONObject:bridgeState()){try? data.write(to:folder.appendingPathComponent("state.json"),options:.atomic)}
        }
        let urls=(try? FileManager.default.contentsOfDirectory(at:folder,includingPropertiesForKeys:[.fileSizeKey,.isRegularFileKey,.isSymbolicLinkKey,.contentModificationDateKey])) ?? []
        for url in urls where url.lastPathComponent.hasPrefix("response-") {
            if let modified=try? url.resourceValues(forKeys:[.contentModificationDateKey]).contentModificationDate,now-modified.timeIntervalSince1970>60{try? FileManager.default.removeItem(at:url)}
        }
        for url in urls.filter({$0.lastPathComponent.hasPrefix("request-")}).prefix(8) {
            let id=String(url.lastPathComponent.dropFirst(8).dropLast(5))
            guard url.pathExtension=="json",UUID(uuidString:id) != nil else{continue}
            var result:[String:Any]=["ok":false]
            do {
                let info=try url.resourceValues(forKeys:[.fileSizeKey,.isRegularFileKey,.isSymbolicLinkKey])
                guard info.isRegularFile==true,info.isSymbolicLink != true,(info.fileSize ?? 100001)<=100000 else{throw StudioError("Requête locale invalide.")}
                let data=try Data(contentsOf:url);try FileManager.default.removeItem(at:url)
                guard !bridgeProcessed.contains(id) else{throw StudioError("Cette commande a déjà été traitée.")}
                guard bridgeProcessed.count<10000 else{throw StudioError("Reconnecte BandPilot pour ouvrir une nouvelle session de commandes.")}
                bridgeProcessed.insert(id)
                guard let request=try JSONSerialization.jsonObject(with:data) as? [String:Any],request["id"] as? String==id,request["session"] as? String==bridgeSession,
                      let created=request["created"] as? Double,abs(now-created)<10,request["projectID"] as? String==project.id,
                      let args=request["args"] as? [String:Any] else{throw StudioError("Connexion expirée ou projet changé. Actualise BandPilot.")}
                try studioControl(args);result=["ok":true,"state":bridgeState()]
            } catch{result=["ok":false,"error":error.localizedDescription];notice=error.localizedDescription;sendState()}
            try? FileManager.default.removeItem(at:url)
            if let data=try? JSONSerialization.data(withJSONObject:result){try? data.write(to:folder.appendingPathComponent("response-"+id+".json"),options:.atomic)}
        }
    }
    func studioControl(_ args:[String:Any]) throws {
        let action=args["action"] as? String ?? ""
        if action=="stop" {transportGeneration += 1;recordPending=false;recordRequest="";if recorder.running{try stopRecord()}else{audio.pause();audio.position=transportOrigin};sendState();return}
        if action=="record",recorder.running{return}
        if action=="marker" {
            guard root != nil else{throw StudioError("Ouvre un projet.")}
            let at=recorder.running && project.capture.mode=="live" ? recorder.elapsed : audio.current()
            if recorder.running{project.sessionDuration=max(project.sessionDuration,at)}else{try requireIdle()}
            remember();project.cues.append(Cue(time:at,name:String((args["name"] as? String ?? "Repère \(project.cues.count+1)").prefix(120))))
            project.cues.sort{$0.time<$1.time};try changed();return
        }
        try requireIdle()
        switch action {
        case "new":try newSession(args["name"] as? String ?? "Répétition")
        case "configure":guard let value=args["settings"] as? [String:Any] else{throw StudioError("Configuration absente.")};try setCapture(value)
        case "record":if project.capture.mode=="live"{try startRecord()}else{try withGuides(afterPreparation{try self.startRecord()})}
        case "play":if !audio.running{transportOrigin=audio.position;try withGuides(afterPreparation{try self.audio.play()})}
        case "pause":audio.pause()
        case "start":try audio.seek(0)
        case "end":try audio.seek(project.duration)
        case "seek":try audio.seek(try number(args,"time",range:0...max(0,project.duration)))
        case "back","forward":try audio.seek(audio.current()+(action=="back" ? -1 : 1)*project.period(at:audio.current())*Double(project.settings.beatsPerBar))
        case "previous","next":
            let at=audio.current(),points=Array(Set([0,project.duration]+project.sections.map(\.start)+project.cues.map(\.time))).sorted()
            try audio.seek(action=="previous" ? (points.last(where:{$0<at-0.05}) ?? 0) : (points.first(where:{$0>at+0.05}) ?? project.duration))
        case "loop":try audio.configureLoop(on:args["on"] as? Bool ?? false,start:try number(args,"start",range:0...max(0,project.duration)),end:try number(args,"end",range:0...max(0,project.duration)))
        default:throw StudioError("Commande de lecteur inconnue.")
        }
        sendState()
    }
}
