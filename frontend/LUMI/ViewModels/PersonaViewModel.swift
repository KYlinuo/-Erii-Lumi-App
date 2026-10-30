import Foundation
import SwiftUI

/// 人物主页 / 人格切换。
@MainActor
final class PersonaViewModel: ObservableObject {
    @Published private(set) var characters: [CharacterInfo] = []
    @Published private(set) var isLoading = false
    @Published var lastError: LUMIError?

    let activeKey = "erii"

    private let api: LUMIAPIClient

    init(api: LUMIAPIClient) {
        self.api = api
    }

    var activeCharacter: CharacterInfo? {
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

}
