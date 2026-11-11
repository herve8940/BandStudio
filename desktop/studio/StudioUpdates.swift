import AppKit

extension StudioApp {
    var automaticUpdates:Bool {UserDefaults.standard.object(forKey:"automaticUpdates") as? Bool ?? true}
    func sendUpdate(_ message:String="") {send(["type":"update","automatic":automaticUpdates,"message":message])}
    func checkUpdates() {
        guard !checkingUpdate else{return};checkingUpdate=true;sendUpdate("Vérification des mises à jour…")
        let engine=runtime!,application=Bundle.main.bundleURL
        DispatchQueue.global(qos:.utility).async { [weak self] in
            let process=Process(),output=Pipe()
            process.executableURL=engine.appendingPathComponent(".venv/bin/python")
            process.arguments=[engine.appendingPathComponent("updater.py").path,"check","--engine",engine.path,"--app",application.path]
            process.standardOutput=output;process.standardError=FileHandle.nullDevice
            var message="Impossible de vérifier les mises à jour."
            do {
                try process.run();let data=output.fileHandleForReading.readDataToEndOfFile();process.waitUntilExit()
                if let value=(try? JSONSerialization.jsonObject(with:data)) as? [String:Any]{message=value["message"] as? String ?? message}
            }catch{StudioDiagnostics.shared.event("update.error",["message":error.localizedDescription])}
            let result=message
            DispatchQueue.main.async {self?.checkingUpdate=false;self?.sendUpdate(result)}
        }
    }
    func applyUpdateAfterExit() {
        guard automaticUpdates,let runtime=runtime else{return}
        let pending=FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/BandStudio/Updates/pending.json")
        guard FileManager.default.fileExists(atPath:pending.path) else{return}
        let process=Process();process.executableURL=runtime.appendingPathComponent(".venv/bin/python")
        process.arguments=[runtime.appendingPathComponent("updater.py").path,"apply","--wait-pid",String(ProcessInfo.processInfo.processIdentifier)]
        process.standardOutput=FileHandle.nullDevice;process.standardError=FileHandle.nullDevice
        do{try process.run()}catch{StudioDiagnostics.shared.event("update.schedule.error",["message":error.localizedDescription])}
    }
}
