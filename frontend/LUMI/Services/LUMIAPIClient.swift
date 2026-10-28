import Foundation

/// 与 LUMI 后端通信的唯一入口（URLSession + async/await）。
///
/// - 只使用真实 HTTP 端点，客户端内置**没有任何**假回复逻辑；
/// - 令牌从 Keychain 读取，模型密钥永远不在客户端出现；
/// - 所有失败都转成 `LUMIError`，带上可展示的中文提示。
final class LUMIAPIClient: Sendable {
    private let session: URLSession
    private let configurationProvider: @Sendable () -> ServerConfiguration

    init(
        session: URLSession? = nil,
        configuration configurationProvider: @escaping @Sendable () -> ServerConfiguration
    ) {
        self.configurationProvider = configurationProvider
        if let session {
            self.session = session
        } else {
            let config = URLSessionConfiguration.default
            config.timeoutIntervalForRequest = 30
            config.timeoutIntervalForResource = 90
            config.waitsForConnectivity = true
            config.httpAdditionalHeaders = ["Accept": "application/json"]
            self.session = URLSession(configuration: config)
        }
    }

    // MARK: - 系统

    func health() async throws -> HealthResponse {
        try await get("/api/v1/health")
    }

    func persona() async throws -> PersonaResponse {
        try await get("/api/v1/persona")
    }

    // MARK: - 会话与聊天

    func conversations(characterKey: String? = nil) async throws -> [ConversationSummary] {
        var path = "/api/v1/conversations"
        if let characterKey, let encoded = characterKey.addingPercentEncoding(
            withAllowedCharacters: .urlQueryAllowed
        ) {
            path += "?character_key=\(encoded)"
        }
        return try await get(path)
    }

    func createConversation(characterKey: String? = nil) async throws -> ConversationSummary {
        var path = "/api/v1/conversations"
        if let characterKey, let encoded = characterKey.addingPercentEncoding(
            withAllowedCharacters: .urlQueryAllowed
        ) {
            path += "?character_key=\(encoded)"
        }
        struct Created: Decodable, Sendable {
            let id: String
            let title: String
            let characterId: String?
            enum CodingKeys: String, CodingKey {
                case id, title
                case characterId = "character_id"
            }
        }
        let created: Created = try await post(path, body: EmptyBody())
        let now = LUMIDate.string(from: Date())
        return ConversationSummary(
            id: created.id, title: created.title, createdAt: now, updatedAt: now,
            messageCount: 0, characterId: created.characterId, userId: nil
        )
    }

    func messages(conversationID: String) async throws -> [ServerMessage] {
        try await get("/api/v1/conversations/\(conversationID)/messages")
    }

    /// 发送一条消息并等待真实模型回复。
    ///
    /// `requestID` 用于幂等：App 在网络极差时重发同一条，服务端不会产生第二条回复。
    func sendMessage(
        text: String,
        conversationID: String?,
        requestID: String? = nil,
        characterKey: String? = nil,
        mediaID: String? = nil,
        kind: String = "text"
    ) async throws -> ChatResponse {
        let body = ChatRequest(
            message: text,
            conversationId: conversationID,
            requestId: requestID,
            characterKey: characterKey,
            mediaId: mediaID,
            kind: kind
        )
        return try await post("/api/v1/chat", body: body)
    }

    /// 切换会话所属人格（不合并人格，只是换一个角色继续聊）。
    func switchCharacter(
        conversationID: String,
        characterKey: String
    ) async throws -> String? {
        guard let encoded = characterKey.addingPercentEncoding(
            withAllowedCharacters: .urlQueryAllowed
        ) else { return nil }
        struct Result: Decodable, Sendable {
            let id: String
            let title: String
            let characterId: String?
            enum CodingKeys: String, CodingKey {
                case id, title
                case characterId = "character_id"
            }
        }
        let result: Result = try await patch(
            "/api/v1/conversations/\(conversationID)/character?character_key=\(encoded)",
            body: EmptyBody()
        )
        return result.characterId
    }

    // MARK: - 人格

    func characters() async throws -> [CharacterInfo] {
        try await get("/api/v1/characters")
    }

    func character(key: String) async throws -> CharacterInfo {
        try await get("/api/v1/characters/\(key)")
    }

    func idleLines(characterKey: String, limit: Int = 20) async throws -> IdleLinesResponse {
        try await get("/api/v1/characters/\(characterKey)/idle-lines?limit=\(limit)")
    }

    // MARK: - 长期记忆

    func memories(
        characterKey: String? = nil,
        scope: String? = nil,
        limit: Int = 50
    ) async throws -> [MemoryItem] {
        var parts: [String] = ["limit=\(limit)"]
        if let characterKey, let encoded = characterKey.addingPercentEncoding(
            withAllowedCharacters: .urlQueryAllowed
        ) {
            parts.append("character_key=\(encoded)")
        }
        if let scope, let encoded = scope.addingPercentEncoding(
            withAllowedCharacters: .urlQueryAllowed
        ) {
            parts.append("scope=\(encoded)")
        }
        return try await get("/api/v1/memory?\(parts.joined(separator: "&"))")
    }

    func memorySummary(characterKey: String? = nil) async throws -> MemorySummary {
        if let characterKey, let encoded = characterKey.addingPercentEncoding(
            withAllowedCharacters: .urlQueryAllowed
        ) {
            return try await get("/api/v1/memory/summary?character_key=\(encoded)")
        }
        return try await get("/api/v1/memory/summary")
    }

    func createMemory(scope: String, content: String, characterId: String? = nil) async throws -> MemoryItem {
        struct Body: Encodable, Sendable {
            let scope: String
            let content: String
            let characterId: String?
            let sourceType: String
            enum CodingKeys: String, CodingKey {
                case scope, content
                case characterId = "character_id"
                case sourceType = "source_type"
            }
        }
        return try await post(
            "/api/v1/memory",
            body: Body(scope: scope, content: content, characterId: characterId,
                       sourceType: "user_explicit")
        )
    }

    func archiveMemory(id: String) async throws {
        let _: EmptyResponse = try await post("/api/v1/memory/\(id)/archive", body: EmptyBody())
    }

    func deleteMemory(id: String) async throws {
        try await delete("/api/v1/memory/\(id)")
    }

    // MARK: - 虚构人生

    func diary(characterKey: String, limit: Int = 30) async throws -> DiaryResponse {
        try await get("/api/v1/world/\(characterKey)/diary?limit=\(limit)")
    }

    func timeline(characterKey: String, days: Int = 7) async throws -> [WorldEventItem] {
        try await get("/api/v1/world/\(characterKey)/timeline?days=\(days)")
    }

    // MARK: - 设备

    /// 注册本机。返回的明文令牌**只出现一次**，调用方必须立刻写入 Keychain。
    func registerDevice(
        name: String,
        platform: String = "ios",
        appVersion: String,
        scopes: [String]? = nil
    ) async throws -> DeviceRegistration {
        let body = DeviceRegistrationRequest(
            name: name, platform: platform, appVersion: appVersion, scopes: scopes
        )
        return try await post("/api/v1/devices", body: body)
    }

    func devices() async throws -> [DeviceInfo] {
        try await get("/api/v1/devices")
    }

    func whoAmI() async throws -> WhoAmI {
        try await get("/api/v1/devices/me")
    }

    // MARK: - 跨设备同步

    /// 拉取全部会话的增量。返回体里的 `cursor` 需要回写本地，作为下次的 `since`。
    func sync(since: [String: Int], limit: Int = 100) async throws -> SyncResponse {
        try await post("/api/v1/sync", body: SyncRequest(since: since, limit: limit))
    }

    func syncConversation(
        conversationID: String,
        after: Int = 0,
        limit: Int = 100
    ) async throws -> [SyncMessage] {
        try await get("/api/v1/sync/conversation/\(conversationID)?after=\(after)&limit=\(limit)")
    }

    // MARK: - 主动联系

    func proactivePending(characterKey: String? = nil) async throws -> [ProactiveMessageItem] {
        if let characterKey, let encoded = characterKey.addingPercentEncoding(
            withAllowedCharacters: .urlQueryAllowed
        ) {
            return try await get("/api/v1/proactive?character_key=\(encoded)")
        }
        return try await get("/api/v1/proactive")
    }

    func proactiveStatus() async throws -> ProactiveStatus {
        try await get("/api/v1/proactive/status")
    }

    func markProactiveDelivered(ids: [String]) async throws -> Int {
        struct Body: Encodable, Sendable { let ids: [String] }
        struct Result: Decodable, Sendable { let delivered: Int }
        let result: Result = try await post("/api/v1/proactive/delivered", body: Body(ids: ids))
        return result.delivered
    }

    // MARK: - 底层

    private struct EmptyBody: Encodable, Sendable {}
    private struct EmptyResponse: Decodable, Sendable {}

    private func get<T: Decodable & Sendable>(_ path: String) async throws -> T {
        let request = try makeRequest(path: path, method: "GET", body: nil as Data?)
        return try await perform(request)
    }

    private func post<T: Decodable & Sendable, B: Encodable & Sendable>(
        _ path: String,
        body: B
    ) async throws -> T {
        let data = try JSONEncoder().encode(body)
        let request = try makeRequest(path: path, method: "POST", body: data)
        return try await perform(request)
    }

    private func patch<T: Decodable & Sendable, B: Encodable & Sendable>(
        _ path: String,
        body: B
    ) async throws -> T {
        let data = try JSONEncoder().encode(body)
        let request = try makeRequest(path: path, method: "PATCH", body: data)
        return try await perform(request)
    }

    private func delete(_ path: String) async throws {
        let request = try makeRequest(path: path, method: "DELETE", body: nil as Data?)
        let _: EmptyResponse = try await perform(request)
    }

    // MARK: - 媒体与语音（v0.3）

    /// 上传图片或语音。返回服务端媒体 ID，随后带上 `media_id` 发消息。
    func uploadMedia(
        data: Data,
        filename: String,
        mime: String,
        kind: String,
        durationMs: Int = 0
    ) async throws -> MediaAssetDTO {
        let boundary = "lumi-\(UUID().uuidString)"
        var body = Data()
        func append(_ text: String) {
            if let encoded = text.data(using: .utf8) { body.append(encoded) }
        }
        append("--\(boundary)\r\n")
        append("Content-Disposition: form-data; name=\"kind\"\r\n\r\n\(kind)\r\n")
        append("--\(boundary)\r\n")
        append("Content-Disposition: form-data; name=\"duration_ms\"\r\n\r\n\(durationMs)\r\n")
        append("--\(boundary)\r\n")
        append("Content-Disposition: form-data; name=\"file\"; filename=\"\(filename)\"\r\n")
        append("Content-Type: \(mime)\r\n\r\n")
        body.append(data)
        append("\r\n--\(boundary)--\r\n")

        var request = try makeRequest(path: "/api/v1/media", method: "POST", body: body)
        request.setValue(
            "multipart/form-data; boundary=\(boundary)",
            forHTTPHeaderField: "Content-Type"
        )
        request.timeoutInterval = 120
        return try await perform(request)
    }

    /// 语音转写。`mock == true` 时界面必须显示「未接入 ASR」。
    func transcribe(mediaID: String) async throws -> TranscriptDTO {
        struct Empty: Encodable, Sendable {}
        let request = try makeRequest(
            path: "/api/v1/media/\(mediaID)/transcribe",
            method: "POST",
            body: try JSONEncoder().encode(Empty())
        )
        return try await perform(request)
    }

    /// 语音合成（返回可播放音频数据）。
    func synthesize(text: String) async throws -> Data {
        struct Body: Encodable, Sendable { let text: String }
        let request = try makeRequest(
            path: "/api/v1/speech/tts",
            method: "POST",
            body: try JSONEncoder().encode(Body(text: text))
        )
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch let error as URLError {
            throw LUMIError.from(error)
        } catch {
            throw LUMIError.cannotConnectToServer
        }
        guard let http = response as? HTTPURLResponse else {
            throw LUMIError.serverUnreachable(status: 0)
        }
        guard (200..<300).contains(http.statusCode) else {
            throw Self.parseError(statusCode: http.statusCode, data: data, response: http)
        }
        return data
    }

    func speechStatus() async throws -> SpeechStatusDTO {
        try await get("/api/v1/speech/status")
    }

    /// 下载媒体原始字节（图片气泡 / 语音播放用）。
    func downloadMedia(mediaID: String) async throws -> Data {
        let request = try makeRequest(path: "/api/v1/media/\(mediaID)", method: "GET", body: nil as Data?)
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch let error as URLError {
            throw LUMIError.from(error)
        } catch {
            throw LUMIError.cannotConnectToServer
        }
        guard let http = response as? HTTPURLResponse else {
            throw LUMIError.serverUnreachable(status: 0)
        }
        guard (200..<300).contains(http.statusCode) else {
            throw Self.parseError(statusCode: http.statusCode, data: data, response: http)
        }
        return data
    }

    private func makeRequest(path: String, method: String, body: Data?) throws -> URLRequest {
        let configuration = configurationProvider()
        guard var components = URLComponents(url: configuration.baseURL, resolvingAgainstBaseURL: true),
              components.scheme == "http" || components.scheme == "https",
              components.host != nil
        else {
            throw LUMIError.invalidBaseURL(configuration.baseURL.absoluteString)
        }

        // baseURL 可能带路径前缀，这里做一次拼接；查询串单独处理
        let basePath = components.path.hasSuffix("/") ? String(components.path.dropLast()) : components.path
        let split = path.split(separator: "?", maxSplits: 1)
        components.path = basePath + String(split[0])
        if split.count > 1 {
            components.percentEncodedQuery = String(split[1])
        } else {
            components.queryItems = nil
        }

        guard let url = components.url else {
            throw LUMIError.invalidBaseURL(configuration.baseURL.absoluteString)
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = configuration.requestTimeout
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if configuration.isTokenConfigured {
            request.setValue(configuration.accessToken, forHTTPHeaderField: "X-LUMI-TOKEN")
        }
        request.httpBody = body
        return request
    }

    private func perform<T: Decodable & Sendable>(_ request: URLRequest) async throws -> T {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch let error as URLError {
            throw LUMIError.from(error)
        } catch {
            throw LUMIError.cannotConnectToServer
        }

        guard let http = response as? HTTPURLResponse else {
            throw LUMIError.serverUnreachable(status: 0)
        }

        guard (200..<300).contains(http.statusCode) else {
            throw Self.parseError(statusCode: http.statusCode, data: data, response: http)
        }

        if T.self == EmptyResponse.self {
            return EmptyResponse() as! T  // 204/空响应：只关心成功与否
        }

        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw LUMIError.decodingFailure(String(describing: error))
        }
    }

    private static func parseError(
        statusCode: Int,
        data: Data,
        response: HTTPURLResponse
    ) -> LUMIError {
        let retryAfter = response.value(forHTTPHeaderField: "Retry-After").flatMap(Int.init)
        if let envelope = try? JSONDecoder().decode(ErrorEnvelope.self, from: data) {
            return .from(
                code: envelope.error.code,
                httpStatus: statusCode,
                message: envelope.error.message,
                retryAfter: retryAfter
            )
        }
        // 兜底：非标准错误体（例如网关返回的 HTML）
        if statusCode == 401 { return .unauthorized }
        if statusCode == 409 { return .requestIdConflict }
        if statusCode == 429 { return .rateLimited(retryAfter: retryAfter) }
        if statusCode == 504 { return .upstreamTimeout }
        if statusCode == 503 { return .upstreamUnavailable }
        return .serverUnreachable(status: statusCode)
    }
}
