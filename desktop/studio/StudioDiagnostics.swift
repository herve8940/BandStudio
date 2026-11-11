import AppKit

final class StudioDiagnostics {
    static let shared=StudioDiagnostics()
    let folder=FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/BandStudio")
    private let lock=NSLock()
    func event(_ name:String,_ fields:[String:Any]=[:]) {
        lock.lock();defer{lock.unlock()}
        do {
            try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)
            let file=folder.appendingPathComponent("application.log")
            if let size=(try? FileManager.default.attributesOfItem(atPath:file.path)[.size]) as? NSNumber,size.intValue>1_000_000 {
                for i in stride(from:3,through:1,by:-1) {
                    let to=folder.appendingPathComponent("application.log.\(i)"),from=folder.appendingPathComponent(i==1 ? "application.log" : "application.log.\(i-1)")
                    try? FileManager.default.removeItem(at:to);try? FileManager.default.moveItem(at:from,to:to)
                }
            }
            var values=fields;values["event"]=name;values["time"]=ISO8601DateFormatter().string(from:Date())
            var text=String(data:try JSONSerialization.data(withJSONObject:values,options:[.sortedKeys,.withoutEscapingSlashes]),encoding:.utf8)!
            text=text.replacingOccurrences(of:NSHomeDirectory(),with:"<home>")
            text=text.replacingOccurrences(of:"https?://[^\\s\\\"<>]+",with:"<url>",options:.regularExpression)
            text=text.replacingOccurrences(of:"(?i)(token|password|secret|authorization|api[_-]?key)[\\\"\\s:=]+[^,\\s\\\"}]+",with:"$1=<redacted>",options:.regularExpression)
            let data=(String(text.prefix(4000))+"\n").data(using:.utf8)!
            if !FileManager.default.fileExists(atPath:file.path){FileManager.default.createFile(atPath:file.path,contents:nil)}
            let handle=try FileHandle(forWritingTo:file);defer{try? handle.close()};try handle.seekToEnd();try handle.write(contentsOf:data)
        } catch { NSLog("BandStudio diagnostic unavailable: %@",error.localizedDescription) }
    }
}

extension StudioApp {
    func supportCommand(_ command:String,_ args:[String:Any])->Bool {
        if command=="checkUpdates" {checkUpdates();return true}
        if command=="automaticUpdates" {UserDefaults.standard.set(args["enabled"] as? Bool ?? true,forKey:"automaticUpdates");sendUpdate();if automaticUpdates{checkUpdates()};return true}
        if command=="diagnostic" {
            StudioDiagnostics.shared.event("web.error",["message":String((args["message"] as? String ?? "").prefix(2000)),"line":args["line"] as? Int ?? 0]);return true
        }
        if command=="showLogs" {NSWorkspace.shared.open(StudioDiagnostics.shared.folder);return true}
        if command=="reportBug" {
            var url=URLComponents(string:"https://github.com/herve8940/BandStudio/issues/new")!
            url.queryItems=[URLQueryItem(name:"title",value:"[Bug] "),URLQueryItem(name:"labels",value:"bug"),URLQueryItem(name:"body",value:"## Problème\n\n## Pour reproduire\n1. \n\n## Résultat attendu\n\n## Environnement\nBandStudio 1.1.0 · macOS \(ProcessInfo.processInfo.operatingSystemVersionString)\n\nJoindre si utile le diagnostic exporté depuis Réglages après vérification.")]
            NSWorkspace.shared.open(url.url!);return true
        }
        if command=="exportDiagnostics" {
            let panel=NSSavePanel();panel.nameFieldStringValue="BandStudio-diagnostic.txt";panel.allowedFileTypes=["txt"]
            if panel.runModal() == .OK,let target=panel.url {
                var text="BandStudio 1.1.0\nmacOS \(ProcessInfo.processInfo.operatingSystemVersionString)\nVérifie ce fichier avant de le partager. Aucun audio ni projet inclus.\n\n"
                for i in (0...3).reversed(){let file=StudioDiagnostics.shared.folder.appendingPathComponent(i==0 ? "application.log" : "application.log.\(i)");text += (try? String(contentsOf:file,encoding:.utf8)) ?? ""}
                perform{try text.write(to:target,atomically:true,encoding:.utf8);notice="Diagnostic exporté. Vérifie-le avant de le joindre au signalement.";sendState()}
            };return true
        }
        return false
    }
}
