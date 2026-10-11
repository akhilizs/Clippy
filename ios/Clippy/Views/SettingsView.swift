import SwiftUI

struct SettingsView: View {
    @AppStorage("serverURL") private var serverURL = ""
    @AppStorage("accessCode") private var accessCode = ""
    @State private var testing = false
    @State private var result: String?
    @State private var resultOK = false

    var body: some View {
        Form {
            Section {
                TextField("http://192.168.1.20:8000", text: $serverURL)
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                TextField("Access code", text: $accessCode)
                    .textInputAutocapitalization(.characters)
                    .autocorrectionDisabled()
            } header: {
                Text("Your computer")
            } footer: {
                Text("Start the backend on your computer (run.sh on Mac, run.bat on Windows). Its window shows the server address and access code to type here. Your phone and computer must be on the same Wi-Fi.")
            }

            Section {
                Button {
                    Task { await test() }
                } label: {
                    if testing {
                        ProgressView()
                    } else {
                        Text("Test connection")
                    }
                }
                .disabled(testing || serverURL.isEmpty)
                if let result {
                    Label(result, systemImage: resultOK ? "checkmark.circle.fill" : "xmark.circle.fill")
                        .foregroundStyle(resultOK ? .green : .red)
                }
            }

            Section("How to use Clippy") {
                VStack(alignment: .leading, spacing: 8) {
                    Text("1. Campaigns tab: add the Whop campaign and paste its rules.")
                    Text("2. Clips tab: tap + and add the campaign's video (link, Photos or Files).")
                    Text("3. Swipe through the clips. Keep the good ones, tweak the hook if you like.")
                    Text("4. Export: save to Photos, copy the caption, post it.")
                    Text("5. Paste the post link into the campaign on Whop right away, then log it in Tracker.")
                }
                .font(.callout)
            }

            Section("About") {
                LabeledContent("Version", value: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "-")
                Text("Only clip videos a campaign allows you to use, and never buy views - Whop bans accounts for fake engagement.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Settings")
    }

    private func test() async {
        testing = true
        defer { testing = false }
        do {
            let api = try APIClient(server: serverURL, token: accessCode)
            let health = try await api.health()
            try await api.checkAccess()
            resultOK = true
            result = health.ai == "offline"
                ? "Connected. AI is off (no API key on the computer), so clips use the loudest moments."
                : "Connected. AI clip picker: \(health.ai)"
        } catch {
            resultOK = false
            result = error.localizedDescription
        }
    }
}
