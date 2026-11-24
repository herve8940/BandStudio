import AppKit

extension StudioApp {
    func startQueue() throws {
        if queueProcess?.isRunning == true { return }
        let process=Process(),input=Pipe(),output=Pipe()
        process.executableURL=runtime.appendingPathComponent(".venv/bin/python")
        process.arguments=[runtime.appendingPathComponent("batch_queue.py").path,"--engine",runtime.path,"--library",library.path]
        process.standardInput=input;process.standardOutput=output;process.standardError=FileHandle.nullDevice
        var environment=ProcessInfo.processInfo.environment
        environment["PYTHONUNBUFFERED"]="1";environment["PYTHONDONTWRITEBYTECODE"]="1"
        process.environment=environment
        try process.run();queueProcess=process;queueInput=input.fileHandleForWriting
        DispatchQueue.global(qos:.utility).async { [weak self] in
            var buffer=Data()
            while true {
                let data=output.fileHandleForReading.availableData
                if data.isEmpty { break }
                buffer.append(data)
                while let newline=buffer.firstIndex(of:10) {
                    let line=buffer.prefix(upTo:newline);buffer.removeSubrange(...newline)
                    guard let value=(try? JSONSerialization.jsonObject(with:line)) as? [String:Any] else {continue}
                    DispatchQueue.main.async { [weak self] in
                        guard let self=self,self.queueProcess === process else {return}
                        self.queueState=value;self.send(value)
                        if value["libraryChanged"] as? Bool == true {self.sendState()}
                    }
                }
            }
            DispatchQueue.main.async { [weak self] in
                guard let self=self,!self.quitting,self.queueProcess === process else{return}
                self.queueProcess=nil;self.queueInput=nil
                self.queueState=["type":"batchQueue","enabled":false,"running":false,"items":self.queueState["items"] ?? [],"status":uiText("File arrêtée", "Queue stopped"),"message":uiText("Les étapes terminées sont conservées. Clique sur Actualiser la file pour la reconnecter.", "Completed steps have been kept. Click Refresh queue to reconnect.")]
                self.send(self.queueState)
            }
        }
    }
    func queueSend(_ message:[String:Any]) throws {
        try startQueue()
        var data=try JSONSerialization.data(withJSONObject:message);data.append(10)
        try queueInput?.write(contentsOf:data)
    }
    func queueHeartbeat(force:Bool=false) {
        guard queueProcess?.isRunning == true else {return}
        let now=ProcessInfo.processInfo.systemUptime
        if !force && now-queuePulse<0.5 {return};queuePulse=now
        try? queueSend(["action":"heartbeat","ready":!busy && !audio.running && !recorder.running && !recordPending])
    }
    func queueCommand(_ args:[String:Any]) throws {
        if args["action"] as? String == "files" {
            let panel=NSOpenPanel();panel.canChooseDirectories=false;panel.allowsMultipleSelection=true
            panel.allowsOtherFileTypes=true;panel.message=uiText("Choisis les morceaux à ajouter à la file. Un projet sera créé par fichier.", "Choose songs for the queue. Each file gets its own project.")
            panel.beginSheetModal(for:window) { [weak self] answer in
                guard let self=self,answer == .OK,!panel.urls.isEmpty else{return}
                self.perform {try self.queueSend(["action":"add","kind":"file","sources":panel.urls.map(\.path),"options":args["options"] ?? [:]])}
            }
        } else if args["action"] as? String == "refresh" {
            try startQueue();send(queueState);queueHeartbeat(force:true)
        } else {
            try queueSend(args);queueHeartbeat(force:true)
        }
    }
    func closeQueue() {
        try? queueInput?.close();queueInput=nil
        // Finish stopping workers before a pending app update can replace their code.
        let deadline=Date().addingTimeInterval(8)
        while queueProcess?.isRunning == true && Date()<deadline {Thread.sleep(forTimeInterval:0.05)}
        if queueProcess?.isRunning == true {queueProcess?.terminate()}
    }
}
