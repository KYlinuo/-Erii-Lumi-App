import Foundation
import SwiftUI

/// 人物主页 / 人格切换。
@MainActor
final class PersonaViewModel: ObservableObject {
    @Published private(set) var characters: [CharacterInfo] = []
    @Published private(set) var isLoading = false
    @Published private(set) var isSwitching = false
    @Published var lastError: LUMIError?
    @Published var idleLines: IdleLinesResponse?

    /// 当前会话绑定的人格 key（由 Chat 侧同步过来）
    @Published var activeKey: String? {
        didSet { UserDefaults.standard.set(activeKey, forKey: Self.activeKeyDefaultsKey) }
    }

    private static let activeKeyDefaultsKey = "lumi.character.key"

    private let api: LUMIAPIClient

    init(api: LUMIAPIClient) {
        self.api = api
        self.activeKey = UserDefaults.standard.string(forKey: Self.activeKeyDefaultsKey)
    }

    var activeCharacter: CharacterInfo? {
        guard let activeKey else { return characters.first(where: { $0.isDefault }) ?? characters.first }
        return characters.first(where: { $0.key == activeKey })
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            characters = try await api.characters()
            lastError = nil
        } catch let error as LUMIError {
            lastError = error
        } catch {
            lastError = .cannotConnectToServer
        }
    }

    /// 切换当前会话的人格（不合并人格，只是换一个角色继续聊）。
    func select(_ character: CharacterInfo, conversationID: String?) async {
        activeKey = character.key
        guard let conversationID else { return }

        isSwitching = true
        defer { isSwitching = false }
        do {
            _ = try await api.switchCharacter(conversationID: conversationID, characterKey: character.key)
            lastError = nil
        } catch let error as LUMIError {
            lastError = error
        } catch {
            lastError = .cannotConnectToServer
        }
    }

    func loadIdleLines(for character: CharacterInfo) async {
        do {
            idleLines = try await api.idleLines(characterKey: character.key, limit: 24)
        } catch {
            idleLines = nil
        }
    }
}
