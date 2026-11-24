import Foundation

// Set once at launch. Worker processes inherit the same language.
enum StudioLanguage {
    static var current = "fr"

    static func configure() {
        let saved = UserDefaults.standard.string(forKey: "BandStudioUILanguage")
        let system = Locale.preferredLanguages.first ?? "en"
        if let saved = saved, ["fr", "en"].contains(saved) { current = saved }
        else { current = system.lowercased().hasPrefix("fr") ? "fr" : "en" }
        setenv("BANDSTUDIO_UI_LANGUAGE", current, 1)
    }
}

func uiText(_ french: String, _ english: String) -> String {
    StudioLanguage.current == "en" ? english : french
}
