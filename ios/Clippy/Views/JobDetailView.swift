import SwiftUI

struct JobDetailView: View {
    let jobId: String
    let title: String
    @State private var job: Job?
    @State private var error: String?
    @State private var feedStart: Clip?
    @State private var thumbnails: APIClient?

    private let columns = [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let error {
                    ErrorBanner(message: error)
                }
                if let job {
                    header(job)
                    if !job.clips.isEmpty {
                        LazyVGrid(columns: columns, spacing: 12) {
                            ForEach(job.clips) { clip in
                                Button {
                                    feedStart = clip
                                } label: {
                                    ClipCard(clip: clip, thumbnailURL: thumbnails?.thumbnailURL(clip))
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                } else if error == nil {
                    ProgressView().frame(maxWidth: .infinity)
                }
            }
            .padding()
        }
        .navigationTitle(title.isEmpty ? "Video" : title)
        .navigationBarTitleDisplayMode(.inline)
        .fullScreenCover(item: $feedStart) { clip in
            ClipFeedView(clips: job?.clips ?? [clip], startId: clip.id) { updated in
                replace(updated)
            }
        }
        .task {
            thumbnails = try? APIClient.fromSettings()
            while !Task.isCancelled {
                await load()
                let busy = job.map { $0.isActive || $0.clips.contains { $0.isBusy } } ?? true
                try? await Task.sleep(nanoseconds: busy ? 3_000_000_000 : 10_000_000_000)
            }
        }
    }

    @ViewBuilder
    private func header(_ job: Job) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if job.isActive {
                ProgressView(value: job.progress) {
                    Text(job.message).font(.subheadline)
                }
                Text("You can leave this screen. Long videos take a while: roughly a few minutes per hour of video.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else if job.status == "failed" {
                ErrorBanner(message: job.error ?? "Something went wrong.")
                Button("Try again") {
                    Task { await retry() }
                }
                .buttonStyle(.borderedProminent)
            } else {
                Text(job.message).font(.subheadline)
                if let first = job.clips.first(where: { $0.isReady }) {
                    Button {
                        feedStart = first
                    } label: {
                        Label("Review clips", systemImage: "play.rectangle.on.rectangle")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                }
            }
        }
    }

    private func load() async {
        do {
            job = try await APIClient.fromSettings().job(jobId)
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func retry() async {
        do {
            job = try await APIClient.fromSettings().retryJob(jobId)
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func replace(_ clip: Clip) {
        guard var current = job, let index = current.clips.firstIndex(where: { $0.id == clip.id }) else { return }
        current.clips[index] = clip
        job = current
    }
}

struct ClipCard: View {
    let clip: Clip
    let thumbnailURL: URL?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ZStack {
                Rectangle().fill(Color.black.opacity(0.85))
                if clip.isReady, let thumbnailURL {
                    AsyncImage(url: thumbnailURL) { image in
                        image.resizable().scaledToFill()
                    } placeholder: {
                        ProgressView().tint(.white)
                    }
                } else if clip.isBusy {
                    ProgressView("Editing").tint(.white).foregroundStyle(.white)
                } else {
                    Image(systemName: "exclamationmark.triangle").foregroundStyle(.orange)
                }
            }
            .aspectRatio(9 / 16, contentMode: .fit)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(alignment: .topLeading) {
                ScoreBadge(score: clip.score).padding(6)
            }
            .overlay(alignment: .topTrailing) {
                if clip.review == "kept" {
                    Image(systemName: "checkmark.circle.fill").foregroundStyle(.green).padding(6)
                } else if clip.review == "discarded" {
                    Image(systemName: "xmark.circle.fill").foregroundStyle(.gray).padding(6)
                }
            }
            .overlay(alignment: .bottomTrailing) {
                if let duration = clip.duration {
                    Text(timeString(duration))
                        .font(.caption2.bold())
                        .padding(4)
                        .background(.black.opacity(0.6), in: RoundedRectangle(cornerRadius: 4))
                        .foregroundStyle(.white)
                        .padding(6)
                }
            }
            .opacity(clip.review == "discarded" ? 0.45 : 1)

            Text(clip.hook)
                .font(.subheadline.weight(.semibold))
                .lineLimit(2)
        }
    }
}
