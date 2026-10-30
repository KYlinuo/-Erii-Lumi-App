import Foundation
import SwiftUI

/// 角色虚构人生时间线。
///
/// 诚实边界：所有内容都来自后端 `simulated=true` 的事件，
/// 界面顶部必须常驻「虚构内容」提示，禁止冒充真实经历。
@MainActor
final class DiaryViewModel: ObservableObject {
    @Published private(set) var events: [WorldEventItem] = []
    @Published private(set) var notice = "以下为角色虚构生活中的内容，不是真实经历。"
    @Published private(set) var isLoading = false
    @Published private(set) var characterName = ""
    @Published var lastError: LUMIError?

    var characterKey: String

    private let api: LUMIAPIClient

    init(api: LUMIAPIClient, characterKey: String = "lumi") {
        self.api = api
        self.characterKey = characterKey
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let response = try await api.diary(characterKey: characterKey, limit: 60)
            events = response.events
            notice = response.notice
            characterName = response.characterName
            lastError = nil
        } catch let error as LUMIError {
            lastError = error
        } catch {
            lastError = .cannotConnectToServer
        }
    }

    /// 按日期分组，便于渲染时间线。
    var grouped: [(key: String, items: [WorldEventItem])] {
        var buckets: [(key: String, items: [WorldEventItem])] = []
        for event in events {
            let key = Self.dayKey(event.occurredAt)
            if let index = buckets.firstIndex(where: { $0.key == key }) {
                buckets[index].items.append(event)
            } else {
                buckets.append((key: key, items: [event]))
            }
        }
        return buckets
    }

    private static func dayKey(_ iso: String?) -> String {
        guard let iso, let date = LUMIDate.parse(iso) else {
            return "未知日期"
        }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_CN")
        formatter.dateFormat = "M月d日 EEEE"
        return formatter.string(from: date)
    }
}
