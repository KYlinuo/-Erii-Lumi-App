import Foundation
import SwiftUI

/// 快捷表情栏配置：默认一组绘梨衣风表情，可在设置里自定义（逗号分隔）。
/// 存 UserDefaults，只影响本机。
@MainActor
final class QuickEmojiStore: ObservableObject {
    static let shared = QuickEmojiStore()

    @Published var emojis: [String] {
        didSet {
            UserDefaults.standard.set(emojis.joined(separator: ","), forKey: Key.raw)
        }
    }

    private enum Key {
        static let raw = "erii.quickEmojis"
    }

    private static let defaults: [String] = ["🥺", "🌙", "🌸", "✨", "🫂", "😴", "🍵", "💜", "…", "嗯"]

    private init() {
        if let raw = UserDefaults.standard.string(forKey: Key.raw), !raw.isEmpty {
            emojis = raw.split(separator: ",").map(String.init)
        } else {
            emojis = Self.defaults
        }
    }

    /// 从逗号分隔的文本更新（设置页用），非法输入回退默认。
    func update(fromRaw raw: String) {
        let parts = raw.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        emojis = parts.isEmpty ? Self.defaults : parts
    }
}
