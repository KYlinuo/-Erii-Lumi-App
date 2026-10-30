import SwiftUI

/// 原生启动界面：展示 LUMI 形象与名称，同时探测服务器可达性。
struct LaunchView: View {
    enum Status: Equatable {
        case connecting
        case online(String)
        case offline(String)

        var text: String {
            switch self {
            case .connecting: return "正在连接服务器…"
            case .online(let detail): return "已连接 · \(detail)"
            case .offline(let reason): return "暂时无法连接 · \(reason)"
            }
        }

        var tint: Color {
            switch self {
            case .connecting: return .white.opacity(0.75)
            case .online: return Color(red: 0.55, green: 0.95, blue: 0.75)
            case .offline: return Color(red: 1.0, green: 0.72, blue: 0.62)
            }
        }
    }

    let status: Status
    let onEnter: () -> Void

    @State private var appeared = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color(red: 0.10, green: 0.09, blue: 0.20),
                    Color(red: 0.20, green: 0.14, blue: 0.34),
                    Color(red: 0.13, green: 0.16, blue: 0.34),
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            VStack(spacing: 22) {
                LUMIAvatar(size: 132)
                    .shadow(color: Color.purple.opacity(0.55), radius: 30, x: 0, y: 12)
                    .scaleEffect(appeared ? 1 : 0.65)
                    .opacity(appeared ? 1 : 0)
                    .animation(reduceMotion ? nil : .spring(response: 0.7, dampingFraction: 0.7), value: appeared)

                VStack(spacing: 6) {
                    Text("绘梨衣")
                        .font(.system(size: 40, weight: .bold, design: .rounded))
                        .foregroundStyle(.white)
                        .tracking(6)
                    Text("会一直在你身边的 AI 少女")
                        .font(.system(size: 15, weight: .medium, design: .rounded))
                        .foregroundStyle(.white.opacity(0.72))
                }
                .opacity(appeared ? 1 : 0)
                .animation(.easeOut(duration: 0.5).delay(0.25), value: appeared)

                VStack(spacing: 12) {
                    ProgressView()
                        .controlSize(.small)
                        .tint(.white.opacity(0.85))
                    Text(status.text)
                        .font(.footnote)
                        .foregroundStyle(status.tint)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 32)
                }
                .padding(.top, 8)


                Button {
                    onEnter()
                } label: {
                    Text("进入对话")
                        .font(.system(size: 16, weight: .semibold, design: .rounded))
                        .foregroundStyle(Color(red: 0.16, green: 0.14, blue: 0.30))
                        .padding(.horizontal, 34)
                        .padding(.vertical, 12)
                        .background(
                            Capsule().fill(
                                LinearGradient(
                                    colors: [Color(red: 0.98, green: 0.86, blue: 0.95),
                                             Color(red: 0.82, green: 0.90, blue: 1.0)],
                                    startPoint: .leading,
                                    endPoint: .trailing
                                )
                            )
                        )
                }
                .buttonStyle(.plain)
                .opacity(appeared ? 1 : 0)
                .animation(.easeOut(duration: 0.6).delay(0.6), value: appeared)
                .accessibilityIdentifier("launchEnterButton")
            }
        }
        .onAppear {
            appeared = true
        }
    }
}

#Preview("Launch") {
    LaunchView(status: .connecting) { }
}
