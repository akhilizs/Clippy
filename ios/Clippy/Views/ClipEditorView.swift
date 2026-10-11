import SwiftUI

struct ClipEditorView: View {
    let clip: Clip
    var onSaved: (Clip) -> Void
    @Environment(\.dismiss) private var dismiss

    @State private var hook = ""
    @State private var start = 0.0
    @State private var end = 0.0
    @State private var caption = ""
    @State private var newVariant = false
    @State private var saving = false
    @State private var writing = false
    @State private var issues: [Issue] = []
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Hook text", text: $hook, axis: .vertical)
                        .lineLimit(1...3)
                } header: {
                    Text("Hook (shown for the first 3 seconds)")
                } footer: {
                    Text("Short and curious works best: 3-8 words that make people stay. Keep it honest.")
                }

                Section {
                    Stepper(value: $start, in: 0...max(0, end - 3), step: 0.5) {
                        LabeledContent("Starts at", value: preciseTime(start))
                    }
                    Stepper(value: $end, in: (start + 3)...(start + 600), step: 0.5) {
                        LabeledContent("Ends at", value: preciseTime(end))
                    }
                    Text("About \(Int(end - start)) seconds before pauses are cut out.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } header: {
                    Text("Timing in the original video")
                }

                Section {
                    Toggle("Make a fresh variant", isOn: $newVariant)
                } footer: {
                    Text("Changes the zoom and caption colour so a repost of the same moment isn't flagged as a duplicate.")
                }

                Section {
                    TextEditor(text: $caption)
                        .frame(minHeight: 110)
                    Button {
                        Task { await writeCaption() }
                    } label: {
                        if writing {
                            ProgressView()
                        } else {
                            Label("Write a new caption with AI", systemImage: "sparkles")
                        }
                    }
                    .disabled(writing)
                    ForEach(issues) { IssueRow(issue: $0) }
                } header: {
                    Text("Post caption")
                }

                if let error {
                    ErrorBanner(message: error)
                }
            }
            .navigationTitle("Edit clip")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    if saving {
                        ProgressView()
                    } else {
                        Button("Save") { Task { await save() } }
                    }
                }
            }
            .onAppear {
                hook = clip.hook
                start = clip.start
                end = clip.end
                caption = clip.postCaption
                issues = clip.issues
            }
        }
    }

    private func writeCaption() async {
        writing = true
        defer { writing = false }
        do {
            let updated = try await APIClient.fromSettings().regenerateCaption(clip.id)
            caption = updated.postCaption
            issues = updated.issues
            onSaved(updated)
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func save() async {
        saving = true
        defer { saving = false }
        var input = ClipUpdateInput()
        if hook != clip.hook { input.hook = hook }
        if start != clip.start { input.start = start }
        if end != clip.end { input.end = end }
        if caption != clip.postCaption { input.postCaption = caption }
        input.newVariant = newVariant
        do {
            let updated = try await APIClient.fromSettings().updateClip(clip.id, input)
            onSaved(updated)
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
    }
}
