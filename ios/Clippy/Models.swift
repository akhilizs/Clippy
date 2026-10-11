import Foundation

// Mirrors the backend's JSON (snake_case is converted automatically by APIClient).

struct Health: Codable {
    var ok: Bool
    var version: String
    var ai: String
    var whisperModel: String
}

struct CampaignRequirements: Codable, Hashable {
    var requiredHashtags: [String] = []
    var requiredMentions: [String] = []
    var creditText: String?
    var minSeconds: Int?
    var maxSeconds: Int?
    var platforms: [String] = []
    var banned: [String] = []
    var notes: [String] = []
    var cpmUsd: Double?
}

struct Campaign: Codable, Identifiable, Hashable {
    var id: String
    var name: String
    var rulesText: String
    var sourceUrl: String?
    var requirements: CampaignRequirements
    var createdAt: Double
}

struct Issue: Codable, Hashable, Identifiable {
    var level: String  // error | warning | info
    var message: String
    var id: String { level + message }
}

struct Clip: Codable, Identifiable, Hashable {
    var id: String
    var jobId: String
    var rank: Int
    var start: Double
    var end: Double
    var score: Int
    var hook: String
    var title: String
    var reason: String
    var renderStatus: String  // pending | rendering | ready | failed
    var review: String        // new | kept | discarded
    var duration: Double?
    var variant: Int
    var layout: String?
    var postCaption: String
    var issues: [Issue]
    var error: String?
    var updatedAt: Double

    var isReady: Bool { renderStatus == "ready" }
    var isBusy: Bool { renderStatus == "pending" || renderStatus == "rendering" }
    var errorCount: Int { issues.filter { $0.level == "error" }.count }
}

struct Job: Codable, Identifiable, Hashable {
    var id: String
    var campaignId: String?
    var sourceUrl: String?
    var sourceName: String
    var status: String  // queued | downloading | transcribing | finding | rendering | done | failed
    var progress: Double
    var message: String
    var error: String?
    var sourceDuration: Double?
    var createdAt: Double
    var clips: [Clip] = []

    var isActive: Bool { status != "done" && status != "failed" }
}

struct ViewSnapshot: Codable, Hashable {
    var at: Double
    var views: Int
}

struct Submission: Codable, Identifiable, Hashable {
    var id: String
    var clipId: String?
    var campaignId: String?
    var platform: String
    var url: String
    var views: Int
    var snapshots: [ViewSnapshot]
    var estimatedEarningsUsd: Double?
    var createdAt: Double
}

// Request bodies. nil fields are left out of the JSON, so the backend keeps its current value.

struct CampaignInput: Encodable {
    var name: String
    var rulesText: String
    var sourceUrl: String?
    var cpmUsd: Double?
}

struct CampaignUpdateInput: Encodable {
    var name: String?
    var rulesText: String?
    var sourceUrl: String?
    var reparse: Bool = false
}

struct JobInput: Encodable {
    var sourceUrl: String
    var campaignId: String?
}

struct ClipUpdateInput: Encodable {
    var hook: String?
    var start: Double?
    var end: Double?
    var review: String?
    var postCaption: String?
    var rerender: Bool = false
    var newVariant: Bool = false
}

struct SubmissionInput: Encodable {
    var clipId: String?
    var campaignId: String?
    var platform: String
    var url: String
    var views: Int = 0
}

struct SubmissionUpdateInput: Encodable {
    var url: String?
    var platform: String?
    var views: Int?
}

enum Platform: String, CaseIterable, Identifiable {
    case tiktok, instagram, youtube, x
    var id: String { rawValue }
    var name: String {
        switch self {
        case .tiktok: return "TikTok"
        case .instagram: return "Instagram Reels"
        case .youtube: return "YouTube Shorts"
        case .x: return "X"
        }
    }
    static func name(for raw: String) -> String { Platform(rawValue: raw)?.name ?? raw.capitalized }
}
