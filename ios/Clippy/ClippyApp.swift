import SwiftUI

@main
struct ClippyApp: App {
    var body: some Scene {
        WindowGroup {
            RootView()
        }
    }
}

struct RootView: View {
    @AppStorage("serverURL") private var serverURL = ""
    @State private var tab = 0

    var body: some View {
        TabView(selection: $tab) {
            NavigationStack { JobsView() }
                .tabItem { Label("Clips", systemImage: "film.stack") }
                .tag(0)
            NavigationStack { CampaignsView() }
                .tabItem { Label("Campaigns", systemImage: "megaphone") }
                .tag(1)
            NavigationStack { TrackerView() }
                .tabItem { Label("Tracker", systemImage: "chart.line.uptrend.xyaxis") }
                .tag(2)
            NavigationStack { SettingsView() }
                .tabItem { Label("Settings", systemImage: "gearshape") }
                .tag(3)
        }
        .onAppear {
            if serverURL.isEmpty { tab = 3 }
        }
    }
}
