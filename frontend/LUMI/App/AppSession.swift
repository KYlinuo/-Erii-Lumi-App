import Foundation
import SwiftUI

/// 应用级状态：持有 API 客户端与各个页面的 ViewModel。
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
    let personaViewModel: PersonaViewModel
    let memoryViewModel: MemoryViewModel
    let diaryViewModel: DiaryViewModel

    init(api: LUMIAPIClient? = nil, store: MessageStore? = nil) {
        let client = api ?? LUMIAPIClient(configuration: { ConfigurationStore.load() })
        let stored = "erii"
        self.api = client
        self.chatViewModel = ChatViewModel(
            api: client,
            store: store ?? MessageStore(directory: MessageStore.defaultDirectory())
        )
        self.personaViewModel = PersonaViewModel(api: client)
        self.memoryViewModel = MemoryViewModel(api: client, characterKey: stored)
        self.diaryViewModel = DiaryViewModel(api: client, characterKey: stored)
    }

    /// 启动：本地历史优先进入聊天，健康探测与增量同步不阻塞首屏。
    func bootstrap() async {
        launchStatus = .connecting

        // 1. 本地历史优先：先读本地快照，聊天页立刻可用（离线也能看历史）。
        await chatViewModel.restoreHistory()

        // 2. 立即进入聊天页，不等待任何网络请求。
        if case .launching = phase {
            phase = .ready
        }

        // 3. 健康探测仅用于状态展示，在进入聊天后执行，不阻塞首屏。
        do {
            let health = try await api.health()
            launchStatus = health.isHealthy
                ? .online("\(health.provider)/\(health.providerModel)")
                : .offline("服务器状态 \(health.status)")
        } catch let error as LUMIError {
            launchStatus = .offline(error.userMessage)
        } catch {
            launchStatus = .offline(error.localizedDescription)
        }

        // 4. 增量同步 + 主动消息，失败不阻塞主流程。
        try? await chatViewModel.syncFromServer()
        await chatViewModel.pullProactiveMessages()
    }

    func enterChat() {
        guard case .launching = phase else { return }
        phase = .ready
    }

}
