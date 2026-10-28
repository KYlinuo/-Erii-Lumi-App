import SwiftUI

/// 三套聊天气泡主题。
///
/// 设计约束：三套主题**共用同一个气泡组件**，这里只提供样式参数，
/// 不允许为每套主题复制一份聊天代码。
enum BubbleTheme: String, CaseIterable, Identifiable, Sendable {
    case sakura   // 樱色微光：白天、柔和
    case midnight // 深夜星河：夜间、深紫蓝
    case crystal  // 透明冰晶：高透、冷白高光

    var id: String { rawValue }

    var title: String {
        switch self {
        case .sakura: return "樱色微光"
        case .midnight: return "深夜星河"
        case .crystal: return "透明冰晶"
        }
    }

    var subtitle: String {
        switch self {
        case .sakura: return "柔粉与浅紫，适合白天"
        case .midnight: return "深紫蓝与银光，适合夜里"
        case .crystal: return "高透玻璃与冷白高光"
        }
    }

    /// 我发出的气泡渐变
    var outgoingColors: [Color] {
        switch self {
        case .sakura:
            return [Color(red: 0.98, green: 0.72, blue: 0.82),
                    Color(red: 0.76, green: 0.66, blue: 0.98)]
        case .midnight:
            return [Color(red: 0.36, green: 0.30, blue: 0.72),
                    Color(red: 0.22, green: 0.24, blue: 0.58)]
        case .crystal:
            return [Color.white.opacity(0.34), Color.white.opacity(0.18)]
        }
    }

    /// 对方气泡填充
    var incomingFill: Color {
        switch self {
        case .sakura:
            return Color.white.opacity(0.16)
        case .midnight:
            return Color(red: 0.16, green: 0.15, blue: 0.28).opacity(0.92)
        case .crystal:
            return Color.white.opacity(0.12)
        }
    }

    var incomingStroke: Color {
        switch self {
        case .sakura: return Color.white.opacity(0.20)
        case .midnight: return Color(red: 0.45, green: 0.42, blue: 0.72).opacity(0.35)
        case .crystal: return Color.white.opacity(0.38)
        }
    }

    /// 我发出的气泡上的文字颜色（冰晶主题是浅底深字）
    var outgoingText: Color {
        switch self {
        case .sakura, .midnight: return .white
        case .crystal: return Color(red: 0.12, green: 0.13, blue: 0.22)
        }
    }

    var incomingText: Color {
        Color(red: 0.95, green: 0.95, blue: 0.99)
    }

    /// 气泡后方的一层柔光，让玻璃有厚度感
    var glow: Color {
        switch self {
        case .sakura: return Color(red: 1.0, green: 0.72, blue: 0.86).opacity(0.28)
        case .midnight: return Color(red: 0.45, green: 0.38, blue: 0.95).opacity(0.22)
        case .crystal: return Color.white.opacity(0.16)
        }
    }

    var bubbleCorner: CGFloat {
        switch self {
        case .sakura: return 18
        default: return 16
        }
    }
}
