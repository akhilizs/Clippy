import Foundation

struct APIError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

private struct ErrorBody: Decodable {
    let detail: String?
}

/// Talks to the Clippy backend running on the user's computer.
final class APIClient {
    let baseURL: URL
    let token: String
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    /// Uses the server address and access code saved in Settings.
    static func fromSettings() throws -> APIClient {
        let defaults = UserDefaults.standard
        return try APIClient(server: defaults.string(forKey: "serverURL") ?? "",
                             token: defaults.string(forKey: "accessCode") ?? "")
    }

    init(server: String, token: String) throws {
        var address = server.trimmingCharacters(in: .whitespacesAndNewlines)
        if address.isEmpty {
            throw APIError(message: "Add your computer's address in Settings first.")
        }
        if !address.lowercased().hasPrefix("http") {
            address = "http://" + address
        }
        while address.hasSuffix("/") {
            address.removeLast()
        }
        guard let url = URL(string: address), url.host != nil else {
            throw APIError(message: "That server address doesn't look right. It should look like http://192.168.1.20:8000")
        }
        baseURL = url
        self.token = token.trimmingCharacters(in: .whitespacesAndNewlines)
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 120
        session = URLSession(configuration: config)
        decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
    }

    // MARK: - Plumbing

    func url(_ path: String, query: [URLQueryItem] = []) -> URL {
        var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty {
            components.queryItems = query
        }
        return components.url!
    }

    private func request(_ method: String, _ path: String, query: [URLQueryItem] = []) -> URLRequest {
        var req = URLRequest(url: url(path, query: query))
        req.httpMethod = method
        req.setValue(token, forHTTPHeaderField: "X-Clippy-Token")
        return req
    }

    private func send(_ req: URLRequest) async throws -> Data {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: req)
        } catch {
            throw APIError(message: Self.friendly(error))
        }
        try Self.check(response, data)
        return data
    }

    private static func check(_ response: URLResponse, _ data: Data) throws {
        guard let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) else { return }
        if let body = try? JSONDecoder().decode(ErrorBody.self, from: data), let detail = body.detail {
            throw APIError(message: detail)
        }
        throw APIError(message: "The backend answered with error \(http.statusCode).")
    }

    static func friendly(_ error: Error) -> String {
        if let urlError = error as? URLError {
            switch urlError.code {
            case .cannotConnectToHost, .cannotFindHost, .timedOut, .networkConnectionLost, .notConnectedToInternet:
                return "Can't reach your computer. Check that the Clippy backend window is open and your phone is on the same Wi-Fi."
            case .cancelled:
                return "Cancelled."
            default:
                break
            }
        }
        return error.localizedDescription
    }

    private func decode<T: Decodable>(_ data: Data) throws -> T {
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError(message: "Unexpected answer from the backend. Make sure the app and backend are up to date.")
        }
    }

    private func get<T: Decodable>(_ path: String) async throws -> T {
        try decode(try await send(request("GET", path)))
    }

    private func send<T: Decodable, B: Encodable>(_ method: String, _ path: String, _ body: B) async throws -> T {
        var req = request(method, path)
        req.httpBody = try encoder.encode(body)
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        return try decode(try await send(req))
    }

    private func sendEmpty<T: Decodable>(_ method: String, _ path: String) async throws -> T {
        try decode(try await send(request(method, path)))
    }

    private func delete(_ path: String) async throws {
        _ = try await send(request("DELETE", path))
    }

    // MARK: - Status

    func health() async throws -> Health {
        try await get("health")
    }

    func checkAccess() async throws {
        _ = try await send(request("GET", "auth/check"))
    }

    // MARK: - Campaigns

    func campaigns() async throws -> [Campaign] {
        try await get("campaigns")
    }

    func createCampaign(_ input: CampaignInput) async throws -> Campaign {
        try await send("POST", "campaigns", input)
    }

    func updateCampaign(_ id: String, _ input: CampaignUpdateInput) async throws -> Campaign {
        try await send("PUT", "campaigns/\(id)", input)
    }

    func deleteCampaign(_ id: String) async throws {
        try await delete("campaigns/\(id)")
    }

    // MARK: - Jobs

    func jobs() async throws -> [Job] {
        try await get("jobs")
    }

    func job(_ id: String) async throws -> Job {
        try await get("jobs/\(id)")
    }

    func createJob(link: String, campaignId: String?) async throws -> Job {
        try await send("POST", "jobs", JobInput(sourceUrl: link, campaignId: campaignId))
    }

    func retryJob(_ id: String) async throws -> Job {
        try await sendEmpty("POST", "jobs/\(id)/retry")
    }

    func deleteJob(_ id: String) async throws {
        try await delete("jobs/\(id)")
    }

    /// Streams the file straight from disk, so even multi-GB videos don't fill the phone's memory.
    func upload(file: URL, filename: String, campaignId: String?,
                progress: @escaping (Double) -> Void) async throws -> Job {
        var query = [URLQueryItem(name: "filename", value: filename)]
        if let campaignId {
            query.append(URLQueryItem(name: "campaign_id", value: campaignId))
        }
        var req = request("POST", "jobs/upload", query: query)
        req.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 600
        let delegate = UploadProgressDelegate(onProgress: progress)
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.upload(for: req, fromFile: file, delegate: delegate)
        } catch {
            throw APIError(message: Self.friendly(error))
        }
        try Self.check(response, data)
        return try decode(data)
    }

    // MARK: - Clips

    func clip(_ id: String) async throws -> Clip {
        try await get("clips/\(id)")
    }

    func updateClip(_ id: String, _ input: ClipUpdateInput) async throws -> Clip {
        try await send("PATCH", "clips/\(id)", input)
    }

    func regenerateCaption(_ id: String) async throws -> Clip {
        try await sendEmpty("POST", "clips/\(id)/caption")
    }

    /// The token goes in the query so AVPlayer and AsyncImage can load it; `v` busts caches after a re-render.
    func videoURL(_ clip: Clip) -> URL {
        url("clips/\(clip.id)/video", query: [URLQueryItem(name: "token", value: token),
                                              URLQueryItem(name: "v", value: String(Int(clip.updatedAt)))])
    }

    func thumbnailURL(_ clip: Clip) -> URL {
        url("clips/\(clip.id)/thumbnail", query: [URLQueryItem(name: "token", value: token),
                                                  URLQueryItem(name: "v", value: String(Int(clip.updatedAt)))])
    }

    /// Downloads the finished MP4 to a temporary file (needed for Photos and the share sheet).
    func downloadVideo(_ clip: Clip) async throws -> URL {
        let tempURL: URL
        let response: URLResponse
        do {
            (tempURL, response) = try await session.download(from: videoURL(clip))
        } catch {
            throw APIError(message: Self.friendly(error))
        }
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw APIError(message: "Couldn't download the clip (error \(http.statusCode)).")
        }
        let destination = FileManager.default.temporaryDirectory
            .appendingPathComponent("clippy-\(clip.id)-v\(clip.variant).mp4")
        try? FileManager.default.removeItem(at: destination)
        try FileManager.default.moveItem(at: tempURL, to: destination)
        return destination
    }

    // MARK: - Submissions

    func submissions() async throws -> [Submission] {
        try await get("submissions")
    }

    func createSubmission(_ input: SubmissionInput) async throws -> Submission {
        try await send("POST", "submissions", input)
    }

    func updateSubmission(_ id: String, _ input: SubmissionUpdateInput) async throws -> Submission {
        try await send("PATCH", "submissions/\(id)", input)
    }

    func deleteSubmission(_ id: String) async throws {
        try await delete("submissions/\(id)")
    }
}

final class UploadProgressDelegate: NSObject, URLSessionTaskDelegate {
    private let onProgress: (Double) -> Void

    init(onProgress: @escaping (Double) -> Void) {
        self.onProgress = onProgress
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didSendBodyData bytesSent: Int64,
                    totalBytesSent: Int64, totalBytesExpectedToSend: Int64) {
        guard totalBytesExpectedToSend > 0 else { return }
        let fraction = Double(totalBytesSent) / Double(totalBytesExpectedToSend)
        DispatchQueue.main.async { self.onProgress(fraction) }
    }
}
