import Foundation
import SwiftUI

/// 应用级状态：持有 API 客户端与两个 ViewModel。
@MainActor
final class AppSession: ObservableObject {
    enum Phase {
        case launching
        case ready
    }

    @Published var phase: Phase = .launching
    @Published var launchStatus: LaunchView.Status = .connecting

    let api: LUMIAPIClient
    let chatViewModel: ChatViewModel
    let settingsViewModel: SettingsViewModel

    init(api: LUMIAPIClient? = nil, store: MessageStore? = nil) {
        let client = api ?? LUMIAPIClient(configuration: { ConfigurationStore.load() })
        self.api = client
        self.chatViewModel = ChatViewModel(
            api: client,
            store: store ?? MessageStore(directory: MessageStore.defaultDirectory())
        )
        self.settingsViewModel = SettingsViewModel(api: client)
    }

    /// 启动探测：拿到健康信息后自动进入聊天页；失败也允许进入（设置页可修地址）。
    func bootstrap() async {
        launchStatus = .connecting

        do {
            let health = try await api.health()
            let detail = "\(health.provider)/\(health.providerModel)"
            launchStatus = health.isHealthy ? .online(detail) : .offline("服务器状态 \(health.status)")
        } catch let error as LUMIError {
            launchStatus = .offline(error.userMessage)
        } catch {
            launchStatus = .offline(error.localizedDescription)
        }

        await chatViewModel.restoreHistory()
        try? await Task.sleep(nanoseconds: 700_000_000)

        // 只有在还没有进入聊天页时才切换（用户可能已点「进入对话」）
        if case .launching = phase {
            phase = .ready
        }
    }

    func enterChat() {
        guard case .launching = phase else { return }
        phase = .ready
    }
}
