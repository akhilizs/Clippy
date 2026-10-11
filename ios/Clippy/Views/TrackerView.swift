import SwiftUI

struct TrackerView: View {
    @State private var submissions: [Submission] = []
    @State private var error: String?
    @State private var loaded = false
    @State private var editing: Submission?
    @State private var viewsText = ""

    private var totalViews: Int { submissions.reduce(0) { $0 + $1.views } }
    private var totalEarnings: Double { submissions.reduce(0) { $0 + ($1.estimatedEarningsUsd ?? 0) } }

    var body: some View {
        List {
            if let error {
                ErrorBanner(message: error)
            }
            if !submissions.isEmpty {
                Section {
                    HStack {
                        stat("Posts", "\(submissions.count)")
                        stat("Views", compactNumber(totalViews))
                        stat("Est. earned", money(totalEarnings))
                    }
                } footer: {
                    Text("Estimates use each campaign's pay per 1,000 views. Whop's own numbers decide what you're paid.")
                }
            }
            if loaded && submissions.isEmpty && error == nil {
                ContentUnavailableView(
                    "Nothing posted yet",
                    systemImage: "chart.line.uptrend.xyaxis",
                    description: Text("After you post a clip, use Export, then step 5, to log the link here and get reminders to screenshot your views.")
                )
            }
            ForEach(submissions) { submission in
                Button {
                    viewsText = submission.views > 0 ? "\(submission.views)" : ""
                    editing = submission
                } label: {
                    SubmissionRow(submission: submission)
                }
                .buttonStyle(.plain)
                .swipeActions {
                    Button(role: .destructive) {
                        Task { await delete(submission) }
                    } label: {
                        Label("Delete", systemImage: "trash")
                    }
                    if let url = URL(string: submission.url) {
                        Link(destination: url) {
                            Label("Open", systemImage: "safari")
                        }
                        .tint(.blue)
                    }
                }
            }
        }
        .navigationTitle("Tracker")
        .refreshable { await load() }
        .task { await load() }
        .alert("Update views", isPresented: Binding(get: { editing != nil }, set: { if !$0 { editing = nil } })) {
            TextField("Views", text: $viewsText)
                .keyboardType(.numberPad)
            Button("Save") {
                if let submission = editing {
                    Task { await updateViews(submission) }
                }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Enter the current view count from the app (or from Whop).")
        }
    }

    private func stat(_ title: String, _ value: String) -> some View {
        VStack(spacing: 2) {
            Text(value).font(.title3.bold())
            Text(title).font(.caption).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    private func load() async {
        do {
            submissions = try await APIClient.fromSettings().submissions()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loaded = true
    }

    private func updateViews(_ submission: Submission) async {
        let digits = viewsText.filter(\.isNumber)
        guard let views = Int(digits) else { return }
        do {
            let updated = try await APIClient.fromSettings().updateSubmission(submission.id, SubmissionUpdateInput(views: views))
            if let index = submissions.firstIndex(where: { $0.id == updated.id }) {
                submissions[index] = updated
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func delete(_ submission: Submission) async {
        submissions.removeAll { $0.id == submission.id }
        try? await APIClient.fromSettings().deleteSubmission(submission.id)
    }
}

struct SubmissionRow: View {
    let submission: Submission

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(Platform.name(for: submission.platform)).font(.headline)
                Text(submission.url)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                Text(Date(timeIntervalSince1970: submission.createdAt), style: .relative)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 4) {
                Text("\(compactNumber(submission.views)) views").font(.subheadline.bold())
                if let earned = submission.estimatedEarningsUsd {
                    Text(money(earned)).font(.caption).foregroundStyle(.green)
                }
            }
        }
        .contentShape(Rectangle())
    }
}
