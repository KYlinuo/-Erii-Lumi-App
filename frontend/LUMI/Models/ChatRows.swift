import Foundation

/// A lazy, zero-array-copy adapter. Stable IDs and grouping are derived on demand.
struct ChatRows: RandomAccessCollection {
    struct Row: Identifiable {
        let message: ChatMessage
        let showTime: Bool
        let showAvatar: Bool
        let spacingBelow: Double
        var id: UUID { message.id }
    }
    let messages: [ChatMessage]
    var startIndex: Int { messages.startIndex }
    var endIndex: Int { messages.endIndex }
    func index(after i: Int) -> Int { i + 1 }
    func index(before i: Int) -> Int { i - 1 }

    subscript(index: Int) -> Row {
        let message = messages[index]
        let previous = index > startIndex ? messages[index - 1] : nil
        let next = index + 1 < endIndex ? messages[index + 1] : nil
        let joinsPrevious = previous.map { Self.join($0, message) } ?? false
        let joinsNext = next.map { Self.join(message, $0) } ?? false
        return Row(message: message, showTime: !joinsPrevious,
                   showAvatar: !joinsNext, spacingBelow: joinsNext ? 3 : 10)
    }

    private static func join(_ first: ChatMessage, _ second: ChatMessage) -> Bool {
        let gap = second.createdAt.timeIntervalSince(first.createdAt)
        return first.role == second.role && gap >= 0 && gap < 180
    }
}
