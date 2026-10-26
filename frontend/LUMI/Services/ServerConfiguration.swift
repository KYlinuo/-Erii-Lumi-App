import Foundation

/// 客户端连接配置。
///
/// 安全边界：**这里只保存服务器地址与访问令牌，绝不保存任何模型 API Key。**
/// 令牌存放在 Keychain，其它非敏感偏好放在 UserDefaults。
struct ServerConfiguration: Sendable, Equatable {
    var baseURL: URL
    var accessToken: String
    var requestTimeout: TimeInterval

    init(baseURL: URL, accessToken: String = "", requestTimeout: TimeInterval = 30) {
        self.baseURL = baseURL
        self.accessToken = accessToken
        self.requestTimeout = requestTimeout
    }

    var isTokenConfigured: Bool { !accessToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
}

enum ConfigurationStore {
    private static let baseURLKey = "lumi.server.baseURL"
    private static let timeoutKey = "lumi.server.timeout"
    static let defaultBaseURLString = "http://127.0.0.1:8000"

    /// Info.plist 中可预置 `LUMIServerBaseURL`，便于发布内网版本。
    static func bundledBaseURLString() -> String {
        (Bundle.main.object(forInfoDictionaryKey: "LUMIServerBaseURL") as? String)?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .isEmpty == false
            ? (Bundle.main.object(forInfoDictionaryKey: "LUMIServerBaseURL") as? String)!
            : defaultBaseURLString
    }

    static func storedBaseURLString() -> String {
        if let saved = UserDefaults.standard.string(forKey: baseURLKey), !saved.isEmpty {
            return saved
        }
        return bundledBaseURLString()
    }

    static func saveBaseURLString(_ value: String) {
        UserDefaults.standard.set(value, forKey: baseURLKey)
    }

    static func storedTimeout() -> TimeInterval {
        let v = UserDefaults.standard.double(forKey: timeoutKey)
        return v > 0 ? v : 30
    }

    static func saveTimeout(_ value: TimeInterval) {
        UserDefaults.standard.set(value, forKey: timeoutKey)
    }

    /// 读取完整配置（令牌来自 Keychain）。
    static func load(keychain: KeychainStore = .shared) -> ServerConfiguration {
        let urlString = storedBaseURLString()
        let url = URL(string: urlString) ?? URL(string: defaultBaseURLString)!
        let token = (try? keychain.read(.accessToken)) ?? ""
        return ServerConfiguration(baseURL: url, accessToken: token, requestTimeout: storedTimeout())
    }
}
