import SwiftUI

/// 统一视觉规范：柔和光影 + 适度玻璃质感 + 深色优先的日系气质。
///
/// 所有页面共用这里的背景、卡片与强调色，避免各页各画一套。
enum LUMIStyle {
    // MARK: - 颜色

    static let ink = Color(red: 0.07, green: 0.07, blue: 0.12)
    static let inkSoft = Color(red: 0.11, green: 0.11, blue: 0.18)
    static let violet = Color(red: 0.62, green: 0.52, blue: 0.98)
    static let sakura = Color(red: 0.98, green: 0.68, blue: 0.80)
    static let aqua = Color(red: 0.56, green: 0.86, blue: 0.98)
    static let mint = Color(red: 0.62, green: 0.92, blue: 0.82)

    /// 页面底色：深夜蓝紫渐变，顶部略亮，模拟柔光。
    static var background: some View {
        LinearGradient(
            colors: [
                Color(red: 0.12, green: 0.11, blue: 0.20),
                Color(red: 0.07, green: 0.07, blue: 0.13),
                Color(red: 0.05, green: 0.05, blue: 0.10),
            ],
            startPoint: .top, endPoint: .bottom
        )
        .ignoresSafeArea()
    }

    /// 顶部柔光斑，营造「灯光」氛围。
    static var glow: some View {
        RadialGradient(
            colors: [violet.opacity(0.35), .clear],
            center: .topLeading,
            startRadius: 10,
            endRadius: 420
        )
        .ignoresSafeArea()
        .allowsHitTesting(false)
    }

    static func accent(for key: String) -> Color {
        switch key {
        case "lumi": return violet
        case "linsui": return mint
        case "qilu": return Color(red: 0.99, green: 0.72, blue: 0.45)
        case "shenzhou": return aqua
        case "erii": return sakura
        default: return violet
        }
    }
}

/// 玻璃卡片容器。
struct LUMICard<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        content
            .padding(16)
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .stroke(Color.white.opacity(0.10), lineWidth: 1)
            )
            .shadow(color: .black.opacity(0.28), radius: 14, x: 0, y: 6)
    }
}

/// 小标签（如「推测」「虚构」）。
struct LUMIBadge: View {
    let text: String
    var color: Color = LUMIStyle.violet

    var body: some View {
        Text(text)
            .font(.caption2.weight(.semibold))
            .foregroundStyle(color)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(color.opacity(0.16), in: Capsule())
            .overlay(Capsule().stroke(color.opacity(0.35), lineWidth: 0.8))
    }
}

/// 页面共用的「空状态」。
struct LUMIEmptyState: View {
    let symbol: String
    let title: String
    var subtitle: String? = nil

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: symbol)
                .font(.system(size: 34))
                .foregroundStyle(LUMIStyle.violet.opacity(0.75))
            Text(title)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.primary)
            if let subtitle {
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
    }
}
