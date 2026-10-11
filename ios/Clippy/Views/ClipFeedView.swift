import AVFoundation
import SwiftUI

/// TikTok-style vertical feed: swipe up/down between clips, keep or discard, edit, export.
struct ClipFeedView: View {
    @State private var clips: [Clip]
    @State private var currentId: String?
    @State private var editing: Clip?
    @State private var exporting: Clip?
    var onUpdate: (Clip) -> Void
    @Environment(\.dismiss) private var dismiss

    init(clips: [Clip], startId: String, onUpdate: @escaping (Clip) -> Void) {
        _clips = State(initialValue: clips)
        _currentId = State(initialValue: startId)
        self.onUpdate = onUpdate
    }

    var body: some View {
        ScrollView(.vertical) {
            LazyVStack(spacing: 0) {
                ForEach(clips) { clip in
                    ClipPage(
                        clip: clip,
                        isActive: currentId == clip.id,
                        onReview: { review in Task { await setReview(clip, review) } },
                        onEdit: { editing = clip },
                        onExport: { exporting = clip }
                    )
                    .containerRelativeFrame([.horizontal, .vertical])
                    .id(clip.id)
                }
            }
            .scrollTargetLayout()
        }
        .scrollTargetBehavior(.paging)
        .scrollPosition(id: $currentId)
        .scrollIndicators(.hidden)
        .background(Color.black)
        .ignoresSafeArea(edges: .bottom)
        .overlay(alignment: .topTrailing) {
            Button {
                dismiss()
            } label: {
                Image(systemName: "xmark")
                    .font(.headline)
                    .padding(10)
                    .background(.ultraThinMaterial, in: Circle())
            }
            .padding(.trailing, 16)
        }
        .sheet(item: $editing) { clip in
            ClipEditorView(clip: clip) { updated in
                apply(updated)
            }
        }
        .sheet(item: $exporting) { clip in
            ExportView(clip: clip)
        }
        .task {
            // Keep re-rendering clips up to date.
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 3_000_000_000)
                for clip in clips where clip.isBusy {
                    if let fresh = try? await APIClient.fromSettings().clip(clip.id) {
                        apply(fresh)
                    }
                }
            }
        }
    }

    private func apply(_ clip: Clip) {
        if let index = clips.firstIndex(where: { $0.id == clip.id }) {
            clips[index] = clip
        }
        onUpdate(clip)
    }

    private func setReview(_ clip: Clip, _ review: String) async {
        let newValue = clip.review == review ? "new" : review
        do {
            let updated = try await APIClient.fromSettings().updateClip(clip.id, ClipUpdateInput(review: newValue))
            apply(updated)
            if newValue != "new", let index = clips.firstIndex(where: { $0.id == clip.id }), index + 1 < clips.count {
                withAnimation { currentId = clips[index + 1].id }
            }
        } catch {
            // The page shows the old state; nothing else to do.
        }
    }
}

struct ClipPage: View {
    let clip: Clip
    let isActive: Bool
    var onReview: (String) -> Void
    var onEdit: () -> Void
    var onExport: () -> Void

    @State private var player: AVQueuePlayer?
    @State private var looper: AVPlayerLooper?
    @State private var loadedVersion: Double = -1
    @State private var paused = false

    var body: some View {
        VStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    ScoreBadge(score: clip.score)
                    if let duration = clip.duration {
                        Text(timeString(duration)).font(.caption.bold()).foregroundStyle(.white.opacity(0.8))
                    }
                    if clip.errorCount > 0 {
                        Label("\(clip.errorCount) rule issue\(clip.errorCount == 1 ? "" : "s")",
                              systemImage: "exclamationmark.triangle.fill")
                            .font(.caption.bold())
                            .foregroundStyle(.orange)
                    }
                    Spacer()
                }
                if !clip.reason.isEmpty {
                    Text(clip.reason)
                        .font(.caption)
                        .foregroundStyle(.white.opacity(0.75))
                        .lineLimit(2)
                }
            }
            .padding(.horizontal)
            .padding(.trailing, 50)

            ZStack {
                Color.black
                if clip.isReady, let player {
                    PlayerLayerView(player: player)
                        .onTapGesture {
                            paused.toggle()
                            if paused {
                                player.pause()
                            } else {
                                player.play()
                            }
                        }
                    if paused {
                        Image(systemName: "play.fill")
                            .font(.system(size: 54))
                            .foregroundStyle(.white.opacity(0.8))
                            .allowsHitTesting(false)
                    }
                } else if clip.isBusy {
                    ProgressView("Editing this clip...")
                        .tint(.white)
                        .foregroundStyle(.white)
                } else if clip.renderStatus == "failed" {
                    VStack(spacing: 8) {
                        Image(systemName: "exclamationmark.triangle").font(.largeTitle)
                        Text(clip.error ?? "This clip failed to render.")
                            .multilineTextAlignment(.center)
                    }
                    .foregroundStyle(.white)
                    .padding()
                }
            }
            .aspectRatio(9 / 16, contentMode: .fit)
            .clipShape(RoundedRectangle(cornerRadius: 14))
            .frame(maxWidth: .infinity)

            HStack(spacing: 0) {
                action("Keep", clip.review == "kept" ? "checkmark.circle.fill" : "checkmark.circle",
                       tint: clip.review == "kept" ? .green : .white) { onReview("kept") }
                action("Skip", clip.review == "discarded" ? "xmark.circle.fill" : "xmark.circle",
                       tint: clip.review == "discarded" ? .red : .white) { onReview("discarded") }
                action("Edit", "slider.horizontal.3", tint: .white, action: onEdit)
                action("Export", "square.and.arrow.up", tint: .white, action: onExport)
                    .disabled(!clip.isReady)
            }
            .padding(.bottom, 24)
        }
        .padding(.top, 8)
        .background(Color.black)
        .onAppear { preparePlayer() }
        .onDisappear { player?.pause() }
        .onChange(of: isActive) { _, active in
            if active && !paused {
                player?.play()
            } else {
                player?.pause()
            }
        }
        .onChange(of: clip.updatedAt) { _, _ in preparePlayer() }
        .onChange(of: clip.renderStatus) { _, _ in preparePlayer() }
    }

    private func action(_ title: String, _ icon: String, tint: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 4) {
                Image(systemName: icon).font(.title2)
                Text(title).font(.caption)
            }
            .frame(maxWidth: .infinity)
            .foregroundStyle(tint)
        }
    }

    private func preparePlayer() {
        guard clip.isReady, loadedVersion != clip.updatedAt, let api = try? APIClient.fromSettings() else { return }
        loadedVersion = clip.updatedAt
        player?.pause()
        let newPlayer = AVQueuePlayer()
        looper = AVPlayerLooper(player: newPlayer, templateItem: AVPlayerItem(url: api.videoURL(clip)))
        player = newPlayer
        if isActive && !paused {
            newPlayer.play()
        }
    }
}

/// A bare video layer (no system controls) so vertical swipes go to the feed, not the player.
struct PlayerLayerView: UIViewRepresentable {
    let player: AVPlayer

    final class PlayerUIView: UIView {
        override class var layerClass: AnyClass { AVPlayerLayer.self }
        var playerLayer: AVPlayerLayer { layer as! AVPlayerLayer }
    }

    func makeUIView(context: Context) -> PlayerUIView {
        let view = PlayerUIView()
        view.playerLayer.videoGravity = .resizeAspect
        view.playerLayer.player = player
        view.backgroundColor = .black
        return view
    }

    func updateUIView(_ uiView: PlayerUIView, context: Context) {
        if uiView.playerLayer.player !== player {
            uiView.playerLayer.player = player
        }
    }
}
