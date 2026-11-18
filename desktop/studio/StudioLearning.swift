import Foundation

// Keep this schema aligned with cue_feedback.py. Files stay inside the project.
enum StudioLearning {
    static func pick(_ value:[String:Any],_ keys:[String])->[String:Any] {
        value.filter{keys.contains($0.key)}
    }
    static func snapshot(_ p:[String:Any])->[String:Any] {
        let marker=["id","name","start","end","time","reviewed","origin","locked","announce","callText"]
        let tracks=(p["tracks"] as? [[String:Any]] ?? []).filter{!($0["role"] as? String ?? "").hasPrefix("guide_")}
        return ["projectID":p["id"] ?? "", "tracks":tracks.map{pick($0,["id","file","role","offset","duration"])},
                "settings":pick(p["settings"] as? [String:Any] ?? [:],["gridMode","firstBeat","beatsPerBar","manualBPM","pulseUnit","leadBeats","regionCountBeats","regionCountEnabled","countBars","callsEnabled","speakCues","voice","speechRate","language"]),
                "bpm":p["bpm"] ?? 0,"beats":p["beats"] ?? [],"downbeats":p["downbeats"] ?? [],"gridLocked":p["gridLocked"] ?? false,
                "sections":(p["sections"] as? [[String:Any]] ?? []).map{pick($0,marker)},
                "cues":(p["cues"] as? [[String:Any]] ?? []).map{pick($0,marker)}]
    }
    static func record(_ root:URL,_ data:Data) throws {
        let p=try JSONSerialization.jsonObject(with:data) as! [String:Any]
        let after=snapshot(p),file=root.appendingPathComponent("project.json")
        var before:[String:Any]?=nil
        if FileManager.default.fileExists(atPath:file.path) {
            let previous=try JSONSerialization.jsonObject(with:Data(contentsOf:file)) as! [String:Any]
            if previous["id"] as? String == p["id"] as? String {before=snapshot(previous)}
        }
        if let before=before,NSDictionary(dictionary:before).isEqual(to:after){return}
        if before==nil,(after["sections"] as! [[String:Any]]).isEmpty,(after["cues"] as! [[String:Any]]).isEmpty{return}
        let id=UUID().uuidString
        let event:[String:Any]=["schema":1,"id":id,"created":Date().timeIntervalSince1970,
                               "before":before as Any? ?? NSNull(),"after":after,
                               "labelPolicy":"Only currently reviewed markers are references; model predictions are not labels."]
        let folder=root.appendingPathComponent("Learning/events",isDirectory:true)
        try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)
        try JSONSerialization.data(withJSONObject:event,options:[.sortedKeys]).write(to:folder.appendingPathComponent(id+".json"),options:.atomic)
    }
}
