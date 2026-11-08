import Foundation

extension StudioApp {
    func phoneCommand(_ args:[String:Any]) throws {
        if args["on"] as? Bool != true {
            phoneProcess?.terminate();phoneProcess=nil;phoneFolder=nil
            send(["type":"phone","active":false]);return
        }
        if phoneProcess?.isRunning == true {phoneAnnounced=false;updatePhone();return}
        guard root != nil else{throw StudioError("Ouvre d’abord un morceau.")}
        let folder=FileManager.default.temporaryDirectory.appendingPathComponent("bandstudio-phone-"+UUID().uuidString)
        try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
        let process=Process();process.executableURL=runtime.appendingPathComponent(".venv/bin/python")
        process.arguments=[runtime.appendingPathComponent("phone.py").path,"--folder",folder.path]
        process.standardOutput=FileHandle.nullDevice;process.standardError=FileHandle.nullDevice
        process.terminationHandler={[weak self] ended in DispatchQueue.main.async {
            guard let self=self,self.phoneProcess === ended else{return}
            self.phoneProcess=nil;self.phoneFolder=nil;self.send(["type":"phone","active":false,"error":"Le prompteur réseau s’est arrêté. Tu peux le relancer."])
        }}
        try process.run();phoneProcess=process;phoneFolder=folder;phoneRevision = -1;phoneAnnounced=false;phonePulse=0;updatePhone()
    }
    func updatePhone() {
        guard phoneProcess?.isRunning == true,let folder=phoneFolder else{return}
        let now=Date.timeIntervalSinceReferenceDate
        if now-phonePulse<0.25{return};phonePulse=now
        do {
            if phoneRevision != revision {
                let full=try JSONSerialization.jsonObject(with:JSONEncoder().encode(project)) as? [String:Any] ?? [:]
                let keys=Set(["name","sections","lyrics","chords","beats","bpm","settings","key","capo"])
                let publicProject=full.filter{keys.contains($0.key)}
                try JSONSerialization.data(withJSONObject:publicProject).write(to:folder.appendingPathComponent("project.json"),options:.atomic);phoneRevision=revision
            }
            let transport:[String:Any]=["position":audio.current(),"playing":audio.running,"pitch":audio.pitch,"rate":audio.rate,"countRemaining":audio.countRemaining()]
            try JSONSerialization.data(withJSONObject:transport).write(to:folder.appendingPathComponent("transport.json"),options:.atomic)
            if !phoneAnnounced,let data=try? Data(contentsOf:folder.appendingPathComponent("info.json")),var info=try JSONSerialization.jsonObject(with:data) as? [String:Any] {
                info["type"]="phone";info["active"]=true;send(info);phoneAnnounced=true
            }
        } catch {phoneProcess?.terminate();phoneProcess=nil;send(["type":"phone","active":false,"error":error.localizedDescription])}
    }
}
