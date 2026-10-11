import SwiftUI

struct CampaignsView: View {
    @State private var campaigns: [Campaign] = []
    @State private var error: String?
    @State private var showNew = false
    @State private var loaded = false

    var body: some View {
        List {
            if let error {
                ErrorBanner(message: error)
            }
            if loaded && campaigns.isEmpty && error == nil {
                ContentUnavailableView(
                    "No campaigns yet",
                    systemImage: "megaphone",
                    description: Text("Tap + and paste the rules of a Whop clipping campaign. Clippy reads the required hashtags, tags and clip length for you.")
                )
            }
            ForEach(campaigns) { campaign in
                NavigationLink(value: campaign) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(campaign.name).font(.headline)
                        HStack(spacing: 12) {
                            if let cpm = campaign.requirements.cpmUsd {
                                Label("\(money(cpm)) / 1K views", systemImage: "dollarsign.circle")
                            }
                            if !campaign.requirements.requiredHashtags.isEmpty {
                                Label("\(campaign.requirements.requiredHashtags.count) tags", systemImage: "number")
                            }
                        }
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    }
                }
            }
            .onDelete(perform: delete)
        }
        .navigationTitle("Campaigns")
        .navigationDestination(for: Campaign.self) { campaign in
            CampaignDetailView(campaign: campaign) { updated in
                if let index = campaigns.firstIndex(where: { $0.id == updated.id }) {
                    campaigns[index] = updated
                }
            }
        }
        .toolbar {
            Button {
                showNew = true
            } label: {
                Image(systemName: "plus")
            }
        }
        .sheet(isPresented: $showNew) {
            CampaignEditorView(campaign: nil) { created in
                campaigns.insert(created, at: 0)
            }
        }
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        do {
            campaigns = try await APIClient.fromSettings().campaigns()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loaded = true
    }

    private func delete(_ offsets: IndexSet) {
        let ids = offsets.map { campaigns[$0].id }
        campaigns.remove(atOffsets: offsets)
        Task {
            for id in ids {
                try? await APIClient.fromSettings().deleteCampaign(id)
            }
        }
    }
}

struct CampaignDetailView: View {
    @State var campaign: Campaign
    var onChange: (Campaign) -> Void
    @State private var editing = false

    var body: some View {
        let req = campaign.requirements
        List {
            Section("Must include in every post") {
                if req.requiredHashtags.isEmpty && req.requiredMentions.isEmpty && req.creditText == nil {
                    Text("Nothing required").foregroundStyle(.secondary)
                }
                if !req.requiredHashtags.isEmpty {
                    ChipList(items: req.requiredHashtags)
                }
                if !req.requiredMentions.isEmpty {
                    ChipList(items: req.requiredMentions)
                }
                if let credit = req.creditText {
                    LabeledContent("Credit", value: credit)
                }
            }
            Section("Clip rules") {
                LabeledContent("Length", value: lengthText(req))
                if !req.platforms.isEmpty {
                    LabeledContent("Platforms", value: req.platforms.map { Platform.name(for: $0) }.joined(separator: ", "))
                }
                if let cpm = req.cpmUsd {
                    LabeledContent("Pays", value: "\(money(cpm)) per 1,000 views")
                }
                ForEach(req.banned, id: \.self) { rule in
                    IssueRow(issue: Issue(level: "warning", message: "Not allowed: \(rule)"))
                }
                ForEach(req.notes, id: \.self) { note in
                    IssueRow(issue: Issue(level: "info", message: note))
                }
            }
            if let source = campaign.sourceUrl, !source.isEmpty {
                Section("Source footage") {
                    Text(source).textSelection(.enabled)
                }
            }
            Section("Rules as pasted") {
                Text(campaign.rulesText.isEmpty ? "No rules pasted" : campaign.rulesText)
                    .font(.callout)
                    .textSelection(.enabled)
            }
        }
        .navigationTitle(campaign.name)
        .toolbar {
            Button("Edit") { editing = true }
        }
        .sheet(isPresented: $editing) {
            CampaignEditorView(campaign: campaign) { updated in
                campaign = updated
                onChange(updated)
            }
        }
    }

    private func lengthText(_ req: CampaignRequirements) -> String {
        switch (req.minSeconds, req.maxSeconds) {
        case let (min?, max?): return "\(min)-\(max) seconds"
        case let (min?, nil): return "at least \(min) seconds"
        case let (nil, max?): return "up to \(max) seconds"
        default: return "Not specified (Clippy aims for 20-45 s)"
        }
    }
}

struct CampaignEditorView: View {
    let campaign: Campaign?
    var onSaved: (Campaign) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var rules = ""
    @State private var source = ""
    @State private var cpm = ""
    @State private var saving = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("Name") {
                    TextField("e.g. Podcast clips - Whop", text: $name)
                }
                Section {
                    TextEditor(text: $rules)
                        .frame(minHeight: 180)
                } header: {
                    Text("Campaign rules")
                } footer: {
                    Text("Paste everything from the campaign page on Whop: requirements, hashtags, tags, length, platforms. Clippy turns it into a checklist.")
                }
                Section("Optional") {
                    TextField("Link to the source footage", text: $source)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    if campaign == nil {
                        TextField("Pay per 1,000 views (e.g. 1.50)", text: $cpm)
                            .keyboardType(.decimalPad)
                    }
                }
                if let error {
                    ErrorBanner(message: error)
                }
            }
            .navigationTitle(campaign == nil ? "New campaign" : "Edit campaign")
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
                            .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty)
                    }
                }
            }
            .interactiveDismissDisabled(saving)
            .onAppear {
                if let campaign {
                    name = campaign.name
                    rules = campaign.rulesText
                    source = campaign.sourceUrl ?? ""
                }
            }
        }
    }

    private func save() async {
        saving = true
        defer { saving = false }
        do {
            let api = try APIClient.fromSettings()
            let saved: Campaign
            if let campaign {
                saved = try await api.updateCampaign(campaign.id, CampaignUpdateInput(
                    name: name, rulesText: rules, sourceUrl: source))
            } else {
                let pay = Double(cpm.replacingOccurrences(of: ",", with: "."))
                saved = try await api.createCampaign(CampaignInput(
                    name: name, rulesText: rules, sourceUrl: source.isEmpty ? nil : source, cpmUsd: pay))
            }
            onSaved(saved)
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
    }
}
