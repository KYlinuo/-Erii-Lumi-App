import Foundation
import SwiftUI

@MainActor
final class SettingsViewModel: ObservableObject {
    enum ConnectionState: Equatable {
        case idle
        case checking
        case connected(HealthResponse)
        case failed(String)

        var label: String {
            switch self {
            case .idle: return "未检测"
            case .checking: return "检测中…"
            case .connected(let h): return h.isHealthy ? "已连接" : "服务异常"
            case .failed: return "连接失败"
            }
        }

        var symbol: String {
            switch self {
            case .idle: return "questionmark.circle"
            case .checking: return "arrow.triangle.2.circlepath"
            case .connected(let h): return h.isHealthy ? "checkmark.circle.fill" : "exclamationmark.triangle.fill"
            case .failed: return "xmark.circle.fill"
            }
        }

        var tint: Color {
            switch self {
            case .idle: return .secondary
            case .checking: return .orange
            case .connected(let h): return h.isHealthy ? .green : .yellow
            case .failed: return .red
            }
        }
    }

    @Published var baseURLString: String = ConfigurationStore.storedBaseURLString() {
        didSet {
            guard baseURLString != oldValue else { return }
            ConfigurationStore.saveBaseURLString(baseURLString)
            // 换服务器后清掉旧服务器的媒体缓存，避免旧内容残留占用内存。
            Task { await MediaStore.shared.clearCache() }
        }
    }
    @Published var accessToken: String = (try? KeychainStore.shared.read(.accessToken)) ?? "" {
        didSet { try? KeychainStore.shared.save(accessToken, for: .accessToken) }
    }
    @Published var timeout: TimeInterval = ConfigurationStore.storedTimeout() {
        didSet { ConfigurationStore.saveTimeout(timeout) }
    }
    @Published private(set) var connection: ConnectionState = .idle
    @Published private(set) var isTokenStoredInKeychain = false

    private let api: LUMIAPIClient

    init(api: LUMIAPIClient) {
        self.api = api
        refreshTokenPresence()
    }

    var currentConfiguration: ServerConfiguration {
        ServerConfiguration(
            baseURL: URL(string: baseURLString) ?? URL(string: ConfigurationStore.defaultBaseURLString)!,
            accessToken: accessToken,
            requestTimeout: timeout
        )
    }

    func refreshTokenPresence() {
        isTokenStoredInKeychain = ((try? KeychainStore.shared.read(.accessToken)) ?? "").isEmpty == false
    }

    func clearToken() {
        try? KeychainStore.shared.delete(.accessToken)
        accessToken = ""
        refreshTokenPresence()
        // 登出 / 清令牌后清掉媒体缓存，避免不同账号间图片残留。
        Task { await MediaStore.shared.clearCache() }
    }

    func checkConnection() async {
        connection = .checking
        do {
            let health = try await api.health()
            connection = .connected(health)
        } catch let error as LUMIError {
            connection = .failed(error.userMessage)
        } catch {
            connection = .failed(error.localizedDescription)
        }
    }
}
