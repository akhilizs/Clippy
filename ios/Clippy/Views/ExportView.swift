import Photos
import SwiftUI
import UserNotifications

/// Step-by-step: check rules -> save video -> copy caption -> post -> log the link for Whop.
struct ExportView: View {
    let clip: Clip
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL

    @State private var fileURL: URL?
    @State private var downloading = false
    @State private var savedToPhotos = false
    @State private var copied = false
    @State private var platform: Platform = .tiktok
    @State private var postURL = ""
    @State private var logging = false
    @State private var logged = false
    @State private var error: String?

    private var errors: [Issue] { clip.issues.filter { $0.level == "error" } }

    var body: some View {
        NavigationStack {
            Form {
                Section("1. Check the campaign rules") {
                    if clip.issues.isEmpty {
                        Label("No campaign rules to check", systemImage: "checkmark.circle")
                            .foregroundStyle(.secondary)
                    } else if errors.isEmpty {
                        Label("Passes the campaign checks", systemImage: "checkmark.seal.fill")
                            .foregroundStyle(.green)
                    }
                    ForEach(clip.issues) { IssueRow(issue: $0) }
                }

                Section("2. Get the video") {
                    Button {
                        Task { await saveToPhotos() }
                    } label: {
                        HStack {
                            Label(savedToPhotos ? "Saved to Photos" : "Save to Photos",
                                  systemImage: savedToPhotos ? "checkmark.circle.fill" : "square.and.arrow.down")
                            Spacer()
                            if downloading { ProgressView() }
                        }
                    }
                    .disabled(downloading)
                    if let fileURL {
                        ShareLink(item: fileURL) {
                            Label("Share to an app...", systemImage: "square.and.arrow.up")
                        }
                    }
                }

                Section {
                    Text(clip.postCaption.isEmpty ? clip.hook : clip.postCaption)
                        .font(.callout)
                        .textSelection(.enabled)
                    Button {
                        UIPasteboard.general.string = clip.postCaption.isEmpty ? clip.hook : clip.postCaption
                        copied = true
                    } label: {
                        Label(copied ? "Copied" : "Copy caption", systemImage: copied ? "checkmark" : "doc.on.doc")
                    }
                } header: {
                    Text("3. Copy the caption")
                }

                Section {
                    Button("Open TikTok") { open("tiktok://", fallback: "https://www.tiktok.com/upload") }
                    Button("Open Instagram") { open("instagram://camera", fallback: "https://www.instagram.com/") }
                    Button("Open YouTube") { open("youtube://", fallback: "https://studio.youtube.com/") }
                } header: {
                    Text("4. Post it")
                } footer: {
                    Text("Post from the account you linked to Whop. Pick the video you just saved and paste the caption.")
                }

                Section {
                    Picker("Platform", selection: $platform) {
                        ForEach(Platform.allCases) { Text($0.name).tag($0) }
                    }
                    TextField("Paste the link to your post", text: $postURL)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    Button {
                        Task { await logSubmission() }
                    } label: {
                        Label(logged ? "Saved to Tracker" : "Save to Tracker + remind me",
                              systemImage: logged ? "checkmark.circle.fill" : "bell.badge")
                    }
                    .disabled(logging || logged || !postURL.lowercased().hasPrefix("http"))
                } header: {
                    Text("5. Submit on Whop")
                } footer: {
                    Text("Paste the same link into the campaign on Whop right away. Views only count once it's submitted. Clippy reminds you to screenshot your views after 1, 3 and 7 days in case of disputes.")
                }

                if let error {
                    ErrorBanner(message: error)
                }
            }
            .navigationTitle("Export")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
            .task { await download() }
        }
    }

    private func open(_ app: String, fallback: String) {
        guard let appURL = URL(string: app), let webURL = URL(string: fallback) else { return }
        openURL(appURL) { accepted in
            if !accepted { openURL(webURL) }
        }
    }

    @discardableResult
    private func download() async -> URL? {
        if let fileURL { return fileURL }
        downloading = true
        defer { downloading = false }
        do {
            let url = try await APIClient.fromSettings().downloadVideo(clip)
            fileURL = url
            return url
        } catch {
            self.error = error.localizedDescription
            return nil
        }
    }

    private func saveToPhotos() async {
        guard let url = await download() else { return }
        let status = await PHPhotoLibrary.requestAuthorization(for: .addOnly)
        guard status == .authorized || status == .limited else {
            error = "Allow Clippy to add to Photos in the iPhone Settings app."
            return
        }
        do {
            try await PHPhotoLibrary.shared().performChanges {
                PHAssetChangeRequest.creationRequestForAssetFromVideo(atFileURL: url)
            }
            savedToPhotos = true
        } catch {
            self.error = "Couldn't save to Photos: \(error.localizedDescription)"
        }
    }

    private func logSubmission() async {
        logging = true
        defer { logging = false }
        do {
            _ = try await APIClient.fromSettings().createSubmission(
                SubmissionInput(clipId: clip.id, platform: platform.rawValue, url: postURL.trimmingCharacters(in: .whitespaces)))
            logged = true
            await scheduleReminders()
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func scheduleReminders() async {
        let center = UNUserNotificationCenter.current()
        let allowed = (try? await center.requestAuthorization(options: [.alert, .sound])) ?? false
        guard allowed else { return }
        let checkpoints: [(String, Double)] = [("24 hours", 1), ("3 days", 3), ("7 days", 7)]
        for (label, days) in checkpoints {
            let content = UNMutableNotificationContent()
            content.title = "Screenshot your views"
            content.body = "\"\(clip.hook)\" has been up for \(label). Take a screenshot of the views and update Tracker."
            content.sound = .default
            let trigger = UNTimeIntervalNotificationTrigger(timeInterval: days * 86_400, repeats: false)
            let request = UNNotificationRequest(identifier: "\(clip.id)-\(label)", content: content, trigger: trigger)
            try? await center.add(request)
        }
    }
}
