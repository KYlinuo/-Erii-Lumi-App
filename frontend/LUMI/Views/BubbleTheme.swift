import SwiftUI

/// 三套完整主题（需求 06）：联动 气泡 + 强调色 + 默认背景 + 可选提示音。
///
/// 设计约束：三套主题**共用同一个气泡组件**，这里只提供样式参数，
/// 不允许为每套主题复制一份聊天代码。
/// 主题名对齐用户要求：樱花白 / 东京夜雨 / 深海蓝。
enum BubbleTheme: String, CaseIterable, Identifiable, Sendable {
    case sakura   // 樱花白：白天、柔和、粉白
    case midnight // 东京夜雨：夜间、深紫蓝、雨夜
    case crystal  // 深海蓝：高透玻璃、冷蓝

    var id: String { rawValue }

    var title: String {
        switch self {
        case .sakura: return "樱花白"
        case .midnight: return "东京夜雨"
        case .crystal: return "深海蓝"
        }
    }

    var subtitle: String {
        switch self {
        case .sakura: return "柔粉与浅紫，适合白天"
        case .midnight: return "深紫蓝与银光，适合夜里"
        case .crystal: return "高透玻璃与冷蓝高光"
        }
    }

    // MARK: - 强调色（输入栏、按钮、选中态）

    var accent: Color {
        switch self {
        case .sakura: return Color(red: 0.86, green: 0.55, blue: 0.72)
        case .midnight: return Color(red: 0.55, green: 0.48, blue: 0.95)
        case .crystal: return Color(red: 0.42, green: 0.65, blue: 0.98)
        }
    }

    // MARK: - 默认聊天背景（用户未自定义壁纸时使用；均为深色可读底，保证白字对比度）

    var defaultBackground: [Color] {
        switch self {
        case .sakura:
            return [Color(red: 0.16, green: 0.12, blue: 0.22),
                    Color(red: 0.22, green: 0.15, blue: 0.28)]
        case .midnight:
            return [Color(red: 0.07, green: 0.07, blue: 0.15),
                    Color(red: 0.12, green: 0.10, blue: 0.24)]
        case .crystal:
            return [Color(red: 0.06, green: 0.10, blue: 0.17),
                    Color(red: 0.10, green: 0.16, blue: 0.26)]
        }
    }

    /// 可选提示音（发消息/收消息）。nil = 静音。
    /// 音频资源需授权后补充，当前先留空占位，不把占位音效当最终资源。
    var soundName: String? { nil }

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
            return [Color(red: 0.42, green: 0.68, blue: 0.98).opacity(0.55),
                    Color(red: 0.30, green: 0.55, blue: 0.92).opacity(0.40)]
        }
    }

    /// 对方气泡填充
    var incomingFill: Color {
        switch self {
        case .sakura:
            return Color.white.opacity(0.60)
        case .midnight:
            return Color(red: 0.16, green: 0.15, blue: 0.28).opacity(0.92)
        case .crystal:
            return Color.white.opacity(0.14)
        }
    }

    var incomingStroke: Color {
        switch self {
        case .sakura: return Color.white.opacity(0.55)
        case .midnight: return Color(red: 0.45, green: 0.42, blue: 0.72).opacity(0.35)
        case .crystal: return Color.white.opacity(0.30)
        }
    }

    /// 我发出的气泡上的文字颜色（浅底主题用深字）
    var outgoingText: Color {
        switch self {
        case .sakura: return Color(red: 0.35, green: 0.20, blue: 0.32)
        case .midnight: return .white
        case .crystal: return Color(red: 0.10, green: 0.16, blue: 0.24)
        }
    }

    var incomingText: Color {
        switch self {
        case .sakura: return Color(red: 0.24, green: 0.20, blue: 0.30)
        case .midnight, .crystal: return Color(red: 0.95, green: 0.95, blue: 0.99)
        }
    }

    /// 气泡后方的一层柔光，让玻璃有厚度感
    var glow: Color {
        switch self {
        case .sakura: return Color(red: 1.0, green: 0.72, blue: 0.86).opacity(0.28)
        case .midnight: return Color(red: 0.45, green: 0.38, blue: 0.95).opacity(0.22)
        case .crystal: return Color(red: 0.40, green: 0.70, blue: 1.0).opacity(0.22)
        }
    }

    var bubbleCorner: CGFloat {
        switch self {
        case .sakura: return 18
        default: return 16
        }
    }
}
