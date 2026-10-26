import SwiftUI

/// LUMI 的独立形象：纯 SwiftUI 矢量绘制，任意尺寸都清晰，不依赖外部图片资源。
///
/// 设计要点（LUMI 少女形象）：
/// - 深靛蓝渐变短发 + 侧边发缕 + 一撮呆毛
/// - 暖色系瞳孔高光、腮红、微笑
/// - 紫粉渐变光晕背景
struct LUMIAvatar: View {
    var size: CGFloat = 64
    var showHalo: Bool = true

    var body: some View {
        content
            .frame(width: 100, height: 100)
            .scaleEffect(size / 100, anchor: .center)
            .frame(width: size, height: size)
            .clipShape(Circle())
            .overlay(
                Circle()
                    .strokeBorder(Color.white.opacity(0.35), lineWidth: max(1, size * 0.02))
            )
    }

    // 以下坐标均基于 100×100 设计稿
    private var content: some View {
        ZStack {
            // 光晕背景
            Circle()
                .fill(
                    LinearGradient(
                        colors: [Color(red: 0.98, green: 0.80, blue: 0.92),
                                 Color(red: 0.76, green: 0.72, blue: 0.98),
                                 Color(red: 0.66, green: 0.86, blue: 0.98)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )

            if showHalo {
                Circle()
                    .stroke(Color.white.opacity(0.55), lineWidth: 2)
                    .frame(width: 92, height: 92)
                    .position(x: 50, y: 50)
                    .blur(radius: 1)
            }

            // 后发
            Circle()
                .fill(
                    LinearGradient(
                        colors: [Color(red: 0.20, green: 0.22, blue: 0.42),
                                 Color(red: 0.12, green: 0.14, blue: 0.30)],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .frame(width: 96, height: 96)
                .position(x: 50, y: 52)

            // 侧发缕
            RoundedRectangle(cornerRadius: 7, style: .continuous)
                .fill(Color(red: 0.18, green: 0.20, blue: 0.40))
                .frame(width: 15, height: 54)
                .position(x: 17, y: 58)
            RoundedRectangle(cornerRadius: 7, style: .continuous)
                .fill(Color(red: 0.18, green: 0.20, blue: 0.40))
                .frame(width: 15, height: 54)
                .position(x: 83, y: 58)

            // 脸
            Ellipse()
                .fill(
                    LinearGradient(
                        colors: [Color(red: 1.00, green: 0.94, blue: 0.90),
                                 Color(red: 0.99, green: 0.86, blue: 0.84)],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .frame(width: 58, height: 62)
                .position(x: 50, y: 58)

            // 刘海
            Ellipse()
                .fill(Color(red: 0.19, green: 0.21, blue: 0.41))
                .frame(width: 66, height: 40)
                .position(x: 50, y: 32)
            // 刘海下缘的弧线（斜刘海）
            LUMIBangs()
                .fill(Color(red: 0.19, green: 0.21, blue: 0.41))
                .frame(width: 62, height: 20)
                .position(x: 50, y: 46)

            // 呆毛
            LUMIAhoge()
                .stroke(Color(red: 0.19, green: 0.21, blue: 0.41), lineWidth: 3)
                .frame(width: 26, height: 22)
                .position(x: 62, y: 12)

            // 眼睛
            ForEach([38.0, 62.0], id: \.self) { x in
                Ellipse()
                    .fill(
                        LinearGradient(
                            colors: [Color(red: 0.35, green: 0.28, blue: 0.62),
                                     Color(red: 0.16, green: 0.13, blue: 0.34)],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
                    .frame(width: 9.5, height: 12.5)
                    .position(x: x, y: 57)
                Circle()
                    .fill(Color.white.opacity(0.9))
                    .frame(width: 3.4, height: 3.4)
                    .position(x: x - 2, y: 53.5)
                Circle()
                    .fill(Color.white.opacity(0.45))
                    .frame(width: 1.8, height: 1.8)
                    .position(x: x + 2.2, y: 60)
            }

            // 腮红
            Ellipse()
                .fill(Color(red: 1.0, green: 0.62, blue: 0.70).opacity(0.45))
                .frame(width: 13, height: 7)
                .position(x: 32, y: 66)
            Ellipse()
                .fill(Color(red: 1.0, green: 0.62, blue: 0.70).opacity(0.45))
                .frame(width: 13, height: 7)
                .position(x: 68, y: 66)

            // 嘴
            LUMISmile()
                .stroke(Color(red: 0.72, green: 0.36, blue: 0.42), lineWidth: 1.6)
                .frame(width: 10, height: 6)
                .position(x: 50, y: 70)
        }
    }
}

private struct LUMIBangs: Shape {
    func path(in rect: CGRect) -> Path {
        var p = Path()
        let w = rect.width
        let h = rect.height
        p.move(to: CGPoint(x: 0, y: 0))
        p.addLine(to: CGPoint(x: w, y: 0))
        p.addLine(to: CGPoint(x: w, y: h * 0.35))
        p.addQuadCurve(to: CGPoint(x: w * 0.62, y: h), control: CGPoint(x: w * 0.85, y: h * 0.85))
        p.addQuadCurve(to: CGPoint(x: w * 0.30, y: h * 0.30), control: CGPoint(x: w * 0.48, y: h * 0.75))
        p.addQuadCurve(to: CGPoint(x: 0, y: h * 0.55), control: CGPoint(x: w * 0.12, y: h * 0.35))
        p.closeSubpath()
        return p
    }
}

private struct LUMIAhoge: Shape {
    func path(in rect: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: rect.width * 0.15, y: rect.height))
        p.addQuadCurve(
            to: CGPoint(x: rect.width * 0.85, y: rect.height * 0.15),
            control: CGPoint(x: rect.width * 0.35, y: rect.height * 0.05)
        )
        return p
    }
}

private struct LUMISmile: Shape {
    func path(in rect: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: 0, y: 0))
        p.addQuadCurve(
            to: CGPoint(x: rect.width, y: 0),
            control: CGPoint(x: rect.width / 2, y: rect.height)
        )
        return p
    }
}

#Preview("LUMI Avatar") {
    VStack(spacing: 24) {
        LUMIAvatar(size: 120)
        LUMIAvatar(size: 56)
        LUMIAvatar(size: 32, showHalo: false)
    }
    .padding()
    .background(Color.black)
}
