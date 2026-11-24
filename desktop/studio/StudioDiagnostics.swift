import AppKit

// BEGIN GENERATED COMMUNITY
let studioCommunity: [String:String] = [
    "invite": "https://discord.gg/5UnQPdMUpR",
    "welcome": "https://discord.com/channels/1571210838315106304/1571211032007806986",
    "news": "https://discord.com/channels/1571210838315106304/1571211189483213044",
    "guide": "https://discord.com/channels/1571210838315106304/1571211224513781801",
    "help": "https://discord.com/channels/1571210838315106304/1571211286144884899",
    "bugs": "https://discord.com/channels/1571210838315106304/1571211312518668308",
    "ideas": "https://discord.com/channels/1571210838315106304/1571211338053718186",
    "rules": "https://discord.com/channels/1571210838315106304/1571211472200007680"
]
// END GENERATED COMMUNITY

final class StudioDiagnostics {
    static let shared=StudioDiagnostics()
    let folder=FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/BandStudio")
    private let lock=NSLock()
    func compactDebug()->String {
        lock.lock();defer{lock.unlock()}
        let file=folder.appendingPathComponent("application.log")
        guard (try? file.resourceValues(forKeys:[.isSymbolicLinkKey]).isSymbolicLink) != true,
              let handle=try? FileHandle(forReadingFrom:file) else{return uiText("Aucun événement récent.", "No recent events.")}
        defer{try? handle.close()}
        let size=(try? handle.seekToEnd()) ?? 0
        try? handle.seek(toOffset:size>32_000 ? size-32_000 : 0)
        let data=(try? handle.read(upToCount:32_000)) ?? Data()
        var result=[String]()
        for line in String(decoding:data,as:UTF8.self).split(separator:"\n") {
            guard let value=try? JSONSerialization.jsonObject(with:Data(line.utf8)) as? [String:Any],
                  let event=value["event"] as? String,
                  event.range(of:"^[a-zA-Z][a-zA-Z0-9_.-]{0,50}$",options:.regularExpression) != nil else{continue}
            if event=="command",let command=value["command"] as? String,["supportInfo","copyDiscordReport","openCommunity"].contains(command){continue}
            var parts=[event]
            for key in ["command","task","component","kind","exit","elapsed","line","busy","playing"] {
                if let item=value[key] {
                    let text=String(describing:item)
                    if text.range(of:"^[a-zA-Z0-9_.-]{1,50}$",options:.regularExpression) != nil {parts.append(key+"="+text)}
                }
            }
            result.append(parts.joined(separator:" "))
        }
        return result.isEmpty ? uiText("Aucun événement récent.", "No recent events.") : String(result.suffix(6).joined(separator:"\n").suffix(650))
    }
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
        if command=="supportInfo" {
            var environment="BandStudio 1.1.0 · macOS \(ProcessInfo.processInfo.operatingSystemVersionString)"
            #if arch(arm64)
            environment += " · arm64"
            #else
            environment += " · x86_64"
            #endif
            if let data=try? Data(contentsOf:runtime.appendingPathComponent("build.json")),
               let build=try? JSONSerialization.jsonObject(with:data) as? [String:Any],
               let commit=build["commit"] as? String,commit.range(of:"^[0-9a-f]{40}$",options:.regularExpression) != nil {environment += " · "+commit.prefix(12)}
            send(["type":"supportInfo","environment":environment,"debug":StudioDiagnostics.shared.compactDebug()]);return true
        }
        if command=="openCommunity" {
            if let address=studioCommunity[args["destination"] as? String ?? "invite"],let url=URL(string:address) {
                if !NSWorkspace.shared.open(url){notice=uiText("Impossible d’ouvrir Discord. Réessaie depuis le lien du site BandStudio.", "Could not open Discord. Try the link on the BandStudio website.");sendState()}
            };return true
        }
        if command=="copyDiscordReport" {
            let request=args["request"] as? Int ?? 0
            guard let text=args["text"] as? String,!text.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,text.utf16.count<=2000 else {
                send(["type":"supportCopied","request":request,"ok":false,"message":uiText("Le rapport doit contenir entre 1 et 2 000 caractères.", "The report must be between 1 and 2,000 characters.")]);return true
            }
            NSPasteboard.general.clearContents()
            guard NSPasteboard.general.setString(text,forType:.string) else {
                send(["type":"supportCopied","request":request,"ok":false,"message":uiText("Copie indisponible. Copie le texte sélectionné, puis ouvre le salon des bugs.", "Clipboard unavailable. Copy the selected text and open the bug reports channel.")]);return true
            }
            let opened=studioCommunity["bugs"].flatMap{URL(string:$0)}.map{NSWorkspace.shared.open($0)} ?? false
            send(["type":"supportCopied","request":request,"ok":true,"message":opened ? uiText("Rapport copié. Colle-le dans #rapports-de-bugs et clique sur Envoyer dans Discord.", "Report copied. Paste it into #rapports-de-bugs and send it in Discord.") : uiText("Rapport copié. Ouvre le salon des bugs avec le bouton ci-dessous, puis colle-le.", "Report copied. Open the bug reports channel below and paste it there.")]);return true
        }
        if command=="checkUpdates" {checkUpdates();return true}
        if command=="automaticUpdates" {UserDefaults.standard.set(args["enabled"] as? Bool ?? true,forKey:"automaticUpdates");sendUpdate();if automaticUpdates{checkUpdates()};return true}
        if command=="diagnostic" {
            StudioDiagnostics.shared.event("web.error",["message":String((args["message"] as? String ?? "").prefix(2000)),"line":args["line"] as? Int ?? 0]);return true
        }
        if command=="showLogs" {NSWorkspace.shared.open(StudioDiagnostics.shared.folder);return true}
        if command=="reportBug" {
            var url=URLComponents(string:"https://github.com/herve8940/BandStudio/issues/new")!
            url.queryItems=[URLQueryItem(name:"title",value:"[Bug] "),URLQueryItem(name:"labels",value:"bug"),URLQueryItem(name:"body",value:uiText("## Problème\n\n## Pour reproduire\n1. \n\n## Résultat attendu\n\n## Environnement\nBandStudio 1.1.0 · macOS \(ProcessInfo.processInfo.operatingSystemVersionString)\n\nJoindre si utile le diagnostic exporté depuis Réglages après vérification.", "## Issue\n\n## Steps to reproduce\n1. \n\n## Expected result\n\n## Environment\nBandStudio 1.1.0 · macOS \(ProcessInfo.processInfo.operatingSystemVersionString)\n\nIf helpful, review and attach the diagnostic file exported from Settings."))]
            NSWorkspace.shared.open(url.url!);return true
        }
        if command=="exportDiagnostics" {
            let panel=NSSavePanel();panel.nameFieldStringValue="BandStudio-diagnostic.txt";panel.allowedFileTypes=["txt"]
            if panel.runModal() == .OK,let target=panel.url {
                var text=uiText("BandStudio 1.1.0\nmacOS \(ProcessInfo.processInfo.operatingSystemVersionString)\nVérifie ce fichier avant de le partager. Aucun audio ni projet inclus.\n\n", "BandStudio 1.1.0\nmacOS \(ProcessInfo.processInfo.operatingSystemVersionString)\nReview before sharing. No audio or projects included.\n\n")
                for i in (0...3).reversed(){let file=StudioDiagnostics.shared.folder.appendingPathComponent(i==0 ? "application.log" : "application.log.\(i)");text += (try? String(contentsOf:file,encoding:.utf8)) ?? ""}
                perform{try text.write(to:target,atomically:true,encoding:.utf8);notice=uiText("Diagnostic exporté. Vérifie-le avant de le joindre au signalement.", "Diagnostics exported. Review the file before attaching it to your report.");sendState()}
            };return true
        }
        return false
    }
}
