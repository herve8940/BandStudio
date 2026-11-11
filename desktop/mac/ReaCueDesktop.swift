import AppKit
import WebKit

// A small native shell. Python owns the localhost API; REAPER owns all audio.
final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKDownloadDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var process: Process?
    var localOrigin: URL?
    var stdoutPipe: Pipe?
    var startupData = Data()
    var booted = false
    var ending = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        let menu = NSMenu()
        let root = NSMenuItem(); menu.addItem(root)
        let appMenu = NSMenu(); root.submenu = appMenu
        appMenu.addItem(withTitle: "À propos de ReaCue Desktop", action: #selector(about), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Quitter ReaCue Desktop", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let edit = NSMenuItem(); menu.addItem(edit); edit.submenu = NSMenu(title:"Édition")
        for (name, action, key) in [("Annuler","undo:","z"),("Couper","cut:","x"),("Copier","copy:","c"),("Coller","paste:","v"),("Tout sélectionner","selectAll:","a")] {
            edit.submenu?.addItem(withTitle:name, action:Selector(action), keyEquivalent:key)
        }
        let view = NSMenuItem();menu.addItem(view);view.submenu=NSMenu(title:"Affichage")
        let reload=view.submenu!.addItem(withTitle:"Actualiser",action:#selector(reloadPage),keyEquivalent:"r");reload.target=self
        NSApp.mainMenu = menu
        window = NSWindow(contentRect:NSRect(x:0,y:0,width:1340,height:920), styleMask:[.titled,.closable,.miniaturizable,.resizable], backing:.buffered, defer:false)
        window.title = "ReaCue Desktop · Test Mac"
        window.minSize = NSSize(width:780,height:620)
        window.setFrameAutosaveName("ReaCueDesktopPreview")
        window.appearance = NSAppearance(named:.darkAqua)
        window.backgroundColor = NSColor(calibratedRed:0.043,green:0.067,blue:0.13,alpha:1)
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        web = WKWebView(frame:.zero,configuration:config)
        web.navigationDelegate=self
        window.contentView=web
        window.center();window.makeKeyAndOrderFront(nil);NSApp.activate(ignoringOtherApps:true)
        web.loadHTMLString("<html><body style='background:#0b1121;color:#e5ebfa;font:18px -apple-system;padding:60px'><h1>ReaCue</h1><p>Démarrage de l’atelier…</p></body></html>",baseURL:nil)
        launchServer()
    }
    @objc func about(){NSApp.orderFrontStandardAboutPanel(options:[.applicationName:"ReaCue Desktop",.applicationVersion:"2.0.0 preview 1",.credits:NSAttributedString(string:"Interface Mac de test · REAPER & BandPilot\nBase ReaCue de701dc · fonctions existantes conservées")])}
    @objc func reloadPage(){web.reload()}
    func launchServer(){
        guard let resources=Bundle.main.resourceURL else {fail("Ressources de l’application introuvables.");return}
        guard let data=try? Data(contentsOf:resources.appendingPathComponent("desktop.json")),
              let config=(try? JSONSerialization.jsonObject(with:data)) as? [String:String],
              let relative=config["engine"] else {fail("Configuration de lancement introuvable.");return}
        let engine=Bundle.main.bundleURL.deletingLastPathComponent().appendingPathComponent(relative)
        let python=engine.appendingPathComponent(".venv/bin/python")
        guard FileManager.default.isExecutableFile(atPath:python.path) else {fail("L’environnement Python ReaCue installé est introuvable. Reconstruis l’application avec tools/build_desktop_mac.py --runtime /chemin/vers/ReaCue.");return}
        let p=Process();p.executableURL=python;p.arguments=["-m","reacue_mcp.desktop"];p.currentDirectoryURL=engine
        var env=ProcessInfo.processInfo.environment;env["PYTHONUNBUFFERED"]="1";env["PYTHONDONTWRITEBYTECODE"]="1"
        p.environment=env
        let out=Pipe();stdoutPipe=out;p.standardOutput=out
        let logURL=FileManager.default.temporaryDirectory.appendingPathComponent("reacue-desktop-\(ProcessInfo.processInfo.processIdentifier).log")
        FileManager.default.createFile(atPath:logURL.path,contents:nil)
        p.standardError=try? FileHandle(forWritingTo:logURL)
        out.fileHandleForReading.readabilityHandler={ [weak self] handle in
            let data=handle.availableData
            if data.isEmpty {handle.readabilityHandler=nil;return}
            DispatchQueue.main.async {
                guard let self=self, !self.booted else{return}
                self.startupData.append(data)
                guard let end=self.startupData.firstIndex(of:10) else{return}
                do {
                    let obj=try JSONSerialization.jsonObject(with:self.startupData[..<end]) as? [String:Any]
                    guard let str=obj?["url"] as? String, let url=URL(string:str),url.host=="127.0.0.1",url.scheme=="http" else{throw NSError(domain:"ReaCue",code:1)}
                    self.booted=true;self.localOrigin=url;self.web.load(URLRequest(url:url))
                } catch {self.fail("Le service local n’a pas démarré correctement. Diagnostic : \(logURL.path)")}
            }
        }
        p.terminationHandler={ [weak self] process in DispatchQueue.main.async {
            guard let self=self, !self.ending else{return}
            self.fail("Le service ReaCue s’est arrêté (code \(process.terminationStatus)). Diagnostic : \(logURL.path)")
        }}
        process=p
        do {try p.run()}catch{fail(error.localizedDescription)}
    }
    func fail(_ message:String){
        let alert=NSAlert();alert.messageText="ReaCue Desktop";alert.informativeText=message;alert.alertStyle = .warning
        alert.beginSheetModal(for:window)
    }
    func webView(_ webView:WKWebView,decidePolicyFor action:WKNavigationAction,decisionHandler:@escaping(WKNavigationActionPolicy)->Void){
        guard let url=action.request.url else{decisionHandler(.cancel);return}
        if url.scheme=="about" {decisionHandler(.allow);return}
        if let base=localOrigin,url.scheme==base.scheme,url.host==base.host,url.port==base.port {
            decisionHandler(action.shouldPerformDownload ? .download : .allow);return
        }
        decisionHandler(.cancel)
        if action.navigationType == .linkActivated, ["https","http"].contains(url.scheme ?? "") {NSWorkspace.shared.open(url)}
    }
    func webView(_ webView:WKWebView,navigationAction:WKNavigationAction,didBecome download:WKDownload){download.delegate=self}
    func download(_ download:WKDownload,decideDestinationUsing response:URLResponse,suggestedFilename:String,completionHandler:@escaping(URL?)->Void){
        let panel=NSSavePanel();panel.nameFieldStringValue=suggestedFilename
        panel.beginSheetModal(for:window){result in completionHandler(result == .OK ? panel.url : nil)}
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender:NSApplication)->Bool{true}
    func applicationWillTerminate(_ notification:Notification){
        ending=true;stdoutPipe?.fileHandleForReading.readabilityHandler=nil
        if process?.isRunning == true {process?.terminate()}
    }
}
let app=NSApplication.shared
let delegate=AppDelegate();app.delegate=delegate
app.run()
