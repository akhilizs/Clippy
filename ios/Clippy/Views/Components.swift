import SwiftUI

func timeString(_ seconds: Double) -> String {
    let total = max(0, Int(seconds.rounded()))
    let hours = total / 3600
    let minutes = (total % 3600) / 60
    let secs = total % 60
    if hours > 0 {
        return String(format: "%d:%02d:%02d", hours, minutes, secs)
    }
    return String(format: "%d:%02d", minutes, secs)
}

func preciseTime(_ seconds: Double) -> String {
    let minutes = Int(seconds) / 60
    let rest = seconds - Double(minutes * 60)
    return String(format: "%d:%04.1f", minutes, rest)
}

func money(_ value: Double) -> String {
    String(format: "$%.2f", value)
}

func compactNumber(_ value: Int) -> String {
    switch value {
    case 1_000_000...: return String(format: "%.1fM", Double(value) / 1_000_000)
    case 10_000...: return String(format: "%.0fK", Double(value) / 1_000)
    case 1_000...: return String(format: "%.1fK", Double(value) / 1_000)
    default: return "\(value)"
    }
}

struct ScoreBadge: View {
    let score: Int

    var color: Color {
        switch score {
        case 85...: return .orange
        case 70..<85: return .pink
        default: return .gray
        }
    }

    var body: some View {
        Label("\(score)", systemImage: "flame.fill")
            .font(.caption.bold())
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(color.opacity(0.9), in: Capsule())
            .foregroundStyle(.white)
    }
}

struct ErrorBanner: View {
    let message: String

    var body: some View {
        Label(message, systemImage: "exclamationmark.triangle.fill")
            .font(.callout)
            .foregroundStyle(.red)
    }
}

struct IssueRow: View {
    let issue: Issue

    var body: some View {
        Label {
            Text(issue.message)
        } icon: {
            switch issue.level {
            case "error": Image(systemName: "xmark.octagon.fill").foregroundStyle(.red)
            case "warning": Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.orange)
            default: Image(systemName: "info.circle").foregroundStyle(.secondary)
            }
        }
        .font(.callout)
    }
}

/// Wraps tags/hashtags onto multiple lines.
struct ChipList: View {
    let items: [String]

    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack { chips }
            VStack(alignment: .leading, spacing: 6) { chips }
        }
    }

    @ViewBuilder private var chips: some View {
        ForEach(items, id: \.self) { item in
            Text(item)
                .font(.callout.weight(.medium))
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(Color.accentColor.opacity(0.15), in: Capsule())
        }
    }
}
