import PhotosUI
import SwiftUI
import UniformTypeIdentifiers

struct JobsView: View {
    @State private var jobs: [Job] = []
    @State private var error: String?
    @State private var loaded = false
    @State private var showNew = false
    @State private var openJob: Job?

    var body: some View {
        List {
            if let error {
                ErrorBanner(message: error)
            }
            if loaded && jobs.isEmpty && error == nil {
                ContentUnavailableView(
                    "No videos yet",
                    systemImage: "film",
                    description: Text("Tap + to add a long video. Clippy finds the moments most likely to go viral and edits them into vertical clips with captions.")
                )
            }
            ForEach(jobs) { job in
                NavigationLink(value: job) {
                    JobRow(job: job)
                }
            }
            .onDelete(perform: delete)
        }
        .navigationTitle("Clippy")
        .navigationDestination(for: Job.self) { job in
            JobDetailView(jobId: job.id, title: job.sourceName)
        }
        .navigationDestination(item: $openJob) { job in
            JobDetailView(jobId: job.id, title: job.sourceName)
        }
        .toolbar {
            Button {
                showNew = true
            } label: {
                Image(systemName: "plus")
            }
        }
        .sheet(isPresented: $showNew) {
            NewJobView { job in
                jobs.insert(job, at: 0)
                openJob = job
            }
        }
        .refreshable { await load() }
        .task {
            while !Task.isCancelled {
                await load()
                let busy = jobs.contains { $0.isActive }
                try? await Task.sleep(nanoseconds: busy ? 3_000_000_000 : 15_000_000_000)
            }
        }
    }

    private func load() async {
        do {
            jobs = try await APIClient.fromSettings().jobs()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loaded = true
    }

    private func delete(_ offsets: IndexSet) {
        let ids = offsets.map { jobs[$0].id }
        jobs.remove(atOffsets: offsets)
        Task {
            for id in ids {
                try? await APIClient.fromSettings().deleteJob(id)
            }
        }
    }
}

struct JobRow: View {
    let job: Job

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(job.sourceName.isEmpty ? "Video" : job.sourceName)
                .font(.headline)
                .lineLimit(1)
            if job.isActive {
                ProgressView(value: job.progress) {
                    Text(job.message).font(.caption).foregroundStyle(.secondary)
                }
            } else if job.status == "failed" {
                Text(job.error ?? "Failed").font(.caption).foregroundStyle(.red).lineLimit(2)
            } else {
                let kept = job.clips.filter { $0.review == "kept" }.count
                Text("\(job.clips.count) clips" + (kept > 0 ? " - \(kept) kept" : ""))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 2)
    }
}

/// A video picked from Photos, copied into the app's temporary folder.
struct PickedVideo: Transferable {
    let url: URL

    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(contentType: .movie) { video in
            SentTransferredFile(video.url)
        } importing: { received in
            let ext = received.file.pathExtension.isEmpty ? "mov" : received.file.pathExtension
            let destination = FileManager.default.temporaryDirectory
                .appendingPathComponent("upload-\(UUID().uuidString).\(ext)")
            try FileManager.default.copyItem(at: received.file, to: destination)
            return PickedVideo(url: destination)
        }
    }
}

struct NewJobView: View {
    var onCreated: (Job) -> Void
    @Environment(\.dismiss) private var dismiss

    enum Source: String, CaseIterable, Identifiable {
        case link = "Link", photos = "Photos", files = "Files"
        var id: String { rawValue }
    }

    @State private var campaigns: [Campaign] = []
    @State private var campaignId = ""
    @State private var source: Source = .link
    @State private var link = ""
    @State private var photoItem: PhotosPickerItem?
    @State private var pickedFile: URL?
    @State private var pickedName = ""
    @State private var showImporter = false
    @State private var preparing = false
    @State private var uploading = false
    @State private var progress = 0.0
    @State private var error: String?

    private var canStart: Bool {
        switch source {
        case .link: return link.trimmingCharacters(in: .whitespaces).lowercased().hasPrefix("http")
        case .photos, .files: return pickedFile != nil
        }
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Picker("Campaign", selection: $campaignId) {
                        Text("None").tag("")
                        ForEach(campaigns) { campaign in
                            Text(campaign.name).tag(campaign.id)
                        }
                    }
                } footer: {
                    Text("Picking the campaign makes Clippy follow its rules: clip length, hashtags, tags.")
                }

                Section {
                    Picker("Source", selection: $source) {
                        ForEach(Source.allCases) { Text($0.rawValue).tag($0) }
                    }
                    .pickerStyle(.segmented)

                    switch source {
                    case .link:
                        TextField("https://youtube.com/watch?v=...", text: $link)
                            .keyboardType(.URL)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                    case .photos:
                        PhotosPicker(selection: $photoItem, matching: .videos) {
                            Label(pickedFile == nil ? "Choose a video" : "Choose a different video",
                                  systemImage: "photo.on.rectangle")
                        }
                    case .files:
                        Button {
                            showImporter = true
                        } label: {
                            Label(pickedFile == nil ? "Choose a file" : "Choose a different file",
                                  systemImage: "folder")
                        }
                    }
                    if source != .link {
                        if preparing {
                            ProgressView("Getting the video ready...")
                        } else if pickedFile != nil {
                            Label(pickedName, systemImage: "checkmark.circle.fill").foregroundStyle(.green)
                        }
                    }
                } header: {
                    Text("Video")
                } footer: {
                    Text(source == .link
                         ? "YouTube, Twitch, Kick, Google Drive and direct video links work. Your computer downloads it."
                         : "The video is sent to your computer over Wi-Fi. Keep the app open until the upload finishes.")
                }

                if uploading {
                    Section {
                        ProgressView(value: progress) {
                            Text("Uploading \(Int(progress * 100))%")
                        }
                    }
                }
                if let error {
                    Section {
                        ErrorBanner(message: error)
                    }
                }
                Section {
                    Text("Only use videos the campaign gives you permission to clip.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("New video")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }.disabled(uploading)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Make clips") { Task { await start() } }
                        .disabled(!canStart || uploading || preparing)
                }
            }
            .interactiveDismissDisabled(uploading)
            .fileImporter(isPresented: $showImporter, allowedContentTypes: [.movie, .video, .mpeg4Movie, .quickTimeMovie]) { result in
                importFile(result)
            }
            .onChange(of: photoItem) { _, item in
                Task { await loadPhoto(item) }
            }
            .task {
                campaigns = (try? await APIClient.fromSettings().campaigns()) ?? []
                if campaignId.isEmpty, let first = campaigns.first {
                    campaignId = first.id
                }
            }
        }
    }

    private func loadPhoto(_ item: PhotosPickerItem?) async {
        guard let item else { return }
        preparing = true
        error = nil
        defer { preparing = false }
        do {
            if let video = try await item.loadTransferable(type: PickedVideo.self) {
                replacePicked(with: video.url, name: "Video from Photos (\(video.url.pathExtension.uppercased()))")
            } else {
                error = "Couldn't load that video."
            }
        } catch {
            self.error = "Couldn't load that video: \(error.localizedDescription)"
        }
    }

    private func importFile(_ result: Result<URL, Error>) {
        switch result {
        case .failure(let failure):
            error = failure.localizedDescription
        case .success(let url):
            preparing = true
            defer { preparing = false }
            let scoped = url.startAccessingSecurityScopedResource()
            defer { if scoped { url.stopAccessingSecurityScopedResource() } }
            let destination = FileManager.default.temporaryDirectory
                .appendingPathComponent("upload-\(UUID().uuidString).\(url.pathExtension)")
            do {
                try FileManager.default.copyItem(at: url, to: destination)
                replacePicked(with: destination, name: url.lastPathComponent)
            } catch {
                self.error = "Couldn't open that file: \(error.localizedDescription)"
            }
        }
    }

    private func replacePicked(with url: URL, name: String) {
        if let old = pickedFile {
            try? FileManager.default.removeItem(at: old)
        }
        pickedFile = url
        pickedName = name
    }

    private func start() async {
        error = nil
        let campaign = campaignId.isEmpty ? nil : campaignId
        do {
            let api = try APIClient.fromSettings()
            let job: Job
            if source == .link {
                job = try await api.createJob(link: link.trimmingCharacters(in: .whitespaces), campaignId: campaign)
            } else {
                guard let file = pickedFile else { return }
                uploading = true
                defer { uploading = false }
                job = try await api.upload(file: file, filename: file.lastPathComponent, campaignId: campaign) { value in
                    progress = value
                }
                try? FileManager.default.removeItem(at: file)
                pickedFile = nil
            }
            onCreated(job)
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
    }
}
