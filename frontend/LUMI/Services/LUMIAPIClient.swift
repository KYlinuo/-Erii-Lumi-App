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

    // MARK: - 端点

    func health() async throws -> HealthResponse {
        try await get("/api/v1/health")
    }

    func persona() async throws -> PersonaResponse {
        try await get("/api/v1/persona")
    }

    func conversations() async throws -> [ConversationSummary] {
        try await get("/api/v1/conversations")
    }

    func messages(conversationID: String) async throws -> [ServerMessage] {
        try await get("/api/v1/conversations/\(conversationID)/messages")
    }

    /// 发送一条消息并等待真实模型回复。
    func sendMessage(text: String, conversationID: String?) async throws -> ChatResponse {
        let body = ChatRequest(message: text, conversationId: conversationID)
        return try await post("/api/v1/chat", body: body)
    }

    // MARK: - 底层

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

    private func makeRequest(path: String, method: String, body: Data?) throws -> URLRequest {
        let configuration = configurationProvider()
        guard var components = URLComponents(url: configuration.baseURL, resolvingAgainstBaseURL: true),
              components.scheme == "http" || components.scheme == "https",
              components.host != nil
        else {
            throw LUMIError.invalidBaseURL(configuration.baseURL.absoluteString)
        }

        // baseURL 可能带路径前缀，这里做一次拼接
        let basePath = components.path.hasSuffix("/") ? String(components.path.dropLast()) : components.path
        components.path = basePath + path
        components.queryItems = nil

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
        if statusCode == 429 { return .rateLimited(retryAfter: retryAfter) }
        if statusCode == 504 { return .upstreamTimeout }
        if statusCode == 503 { return .upstreamUnavailable }
        return .serverUnreachable(status: statusCode)
    }
}
