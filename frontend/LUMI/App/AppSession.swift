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
    /// 当前人格 key：切换人格后聊天、人物、记忆、日记四处保持一致
    @Published var characterKey: String {
        didSet { UserDefaults.standard.set(characterKey, forKey: Self.characterKeyDefaultsKey) }
    }

    private static let characterKeyDefaultsKey = "lumi.character.key"

    let api: LUMIAPIClient
    let chatViewModel: ChatViewModel
    let settingsViewModel: SettingsViewModel
    let personaViewModel: PersonaViewModel
    let memoryViewModel: MemoryViewModel
    let diaryViewModel: DiaryViewModel

    init(api: LUMIAPIClient? = nil, store: MessageStore? = nil) {
        let client = api ?? LUMIAPIClient(configuration: { ConfigurationStore.load() })
        let stored = UserDefaults.standard.string(forKey: Self.characterKeyDefaultsKey) ?? "erii"
        self.api = client
        self.characterKey = stored
        self.chatViewModel = ChatViewModel(
            api: client,
            store: store ?? MessageStore(directory: MessageStore.defaultDirectory())
        )
        self.settingsViewModel = SettingsViewModel(api: client)
        self.personaViewModel = PersonaViewModel(api: client)
        self.memoryViewModel = MemoryViewModel(api: client, characterKey: stored)
        self.diaryViewModel = DiaryViewModel(api: client, characterKey: stored)
        self.personaViewModel.activeKey = stored
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
        // 冷启动补拉一次增量，保证 iPhone 与 Windows 看到同一份历史
        try? await chatViewModel.syncFromServer()
        // 拉取她主动发来的消息（根据记忆/未聊完话题/虚构日常）
        await chatViewModel.pullProactiveMessages()
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

    /// 切换人格：四处视图共享同一个 key，保证数据一致。
    func selectCharacter(_ key: String, conversationID: String?) async {
        characterKey = key
        personaViewModel.activeKey = key
        memoryViewModel.characterKey = key
        diaryViewModel.characterKey = key
        if let conversationID {
            _ = try? await api.switchCharacter(conversationID: conversationID, characterKey: key)
        }
        await memoryViewModel.load()
        await diaryViewModel.load()
    }
}
