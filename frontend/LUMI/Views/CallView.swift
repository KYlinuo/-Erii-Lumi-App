import SwiftUI

/// 实时通话界面（语音 / 视频）。
///
/// 语音模式：纯音频，全屏展示绘梨衣头像与通话状态。
/// 视频模式：在语音基础上叠加本地渲染的角色立绘动画（呼吸 + 眨眼），
/// 不使用摄像头——绘梨衣是虚构角色，「影像」来自本地素材而非真实视频流。
struct CallView: View {
    enum Kind { case voice, video }
    let kind: Kind

    @EnvironmentObject private var session: AppSession
    @StateObject private var callSession = LiveCallSession()
    @Environment(\.dismiss) private var dismiss

    @State private var isMuted = false
    @State private var tokenInfo: CallTokenDTO?
    @State private var connectError: String?

    var body: some View {
        ZStack {
            background

            VStack(spacing: 28) {
                Spacer()

                // 角色影像 / 头像
                if kind == .video {
                    eriiLivePortrait
                } else {
                    eriiAvatar
                }

                VStack(spacing: 6) {
                    Text("绘梨衣")
                        .font(.title2.weight(.semibold))
                        .foregroundStyle(.white)
                    Text(statusText)
                        .font(.footnote)
                        .foregroundStyle(.white.opacity(0.6))
                }

                Spacer()

                // 控制按钮
                HStack(spacing: 40) {
                    controlButton(
                        icon: isMuted ? "mic.slash.fill" : "mic.fill",
                        label: "静音",
                        active: isMuted
                    ) {
                        isMuted.toggle()
                        callSession.setMuted(isMuted)
                    }
                    controlButton(icon: "phone.down.fill", label: "挂断", active: true, tint: .red) {
                        callSession.disconnect()
                        dismiss()
                    }
                    if kind == .video {
                        controlButton(icon: "video.fill", label: "影像", active: false) {
                            // 视频模式无摄像头；此按钮仅为占位提示
                        }
                    }
                }
                .padding(.bottom, 40)
            }
        }
        .task { await bootstrap() }
    }

    // MARK: - 连接

    private var statusText: String {
        if let connectError { return connectError }
        if callSession.isConnected { return "通话中 · 实时语音" }
        if callSession.isConnecting { return "正在连接…" }
        return "准备通话"
    }

    private func bootstrap() async {
        // 先向后端要一个 LiveKit token；未配置时给出明确提示。
        do {
            tokenInfo = try await session.api.callToken()
            if let info = tokenInfo {
                await callSession.connect(url: info.url, token: info.token)
            }
        } catch let error as LUMIError {
            connectError = error.userMessage
        } catch {
            connectError = "无法建立通话连接。"
        }
    }

    // MARK: - 视觉

    private var background: some View {
        LinearGradient(
            colors: [
                Color(red: 0.10, green: 0.08, blue: 0.18),
                Color(red: 0.16, green: 0.12, blue: 0.28),
            ],
            startPoint: .top,
            endPoint: .bottom
        )
        .ignoresSafeArea()
    }

    private var eriiAvatar: some View {
        Circle()
            .fill(Color.white.opacity(0.10))
            .frame(width: 140, height: 140)
            .overlay(
                Image(systemName: "person.wave.2.fill")
                    .font(.system(size: 56))
                    .foregroundStyle(.white.opacity(0.8))
            )
            .overlay(Circle().strokeBorder(.white.opacity(0.2), lineWidth: 1))
    }

    /// 视频模式的「角色影像」：本地渲染的立绘 + 呼吸动画。
    /// 后续接入分层立绘素材后，可在此替换为 SpriteKit 眨眼/口型动画。
    private var eriiLivePortrait: some View {
        VStack(spacing: 0) {
            Image("EriiPortrait")
                .resizable()
                .scaledToFit()
                .frame(width: 200, height: 200)
                .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 24, style: .continuous)
                        .strokeBorder(.white.opacity(0.2), lineWidth: 1)
                )
                .scaleEffect(breathing ? 1.03 : 0.99)
                .animation(.easeInOut(duration: 2.2).repeatForever(autoreverses: true), value: breathing)
                .onAppear { breathing = true }
        }
    }

    @State private var breathing = false

    private func controlButton(
        icon: String,
        label: String,
        active: Bool,
        tint: Color = Color(red: 0.72, green: 0.60, blue: 1.0),
        action: @escaping () -> Void
    ) -> some View {
        VStack(spacing: 6) {
            Button(action: action) {
                Image(systemName: icon)
                    .font(.system(size: 22))
                    .foregroundStyle(.white)
                    .frame(width: 64, height: 64)
                    .background(active ? tint.opacity(0.85) : Color.white.opacity(0.15))
                    .clipShape(Circle())
            }
            Text(label)
                .font(.caption2)
                .foregroundStyle(.white.opacity(0.7))
        }
    }
}
