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

    /// 视频模式的「角色影像」：本地渲染的立绘 + 呼吸 + 眨眼占位动画。
    ///
    /// 诚实说明：当前只有静态立绘，用「呼吸 + 轻微浮动 + 周期性眨眼（眼皮遮罩）」
    /// 表现「待机状态有生命感」。真正的口型同步 / 表情变化需要分层立绘素材
    /// （眼睛、嘴巴独立图层），后续接入 SpriteKit 时替换本视图即可，接口已预留。
    private var eriiLivePortrait: some View {
        ZStack {
            Image("EriiPortrait")
                .resizable()
                .scaledToFit()
                .frame(width: 200, height: 200)
                .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))

            // 眨眼遮罩：闭眼时在立绘上 1/3 处叠一条与背景同色的细线，
            // 模拟眼皮合上；素材换成独立眼睛图层后应删除此占位。
            if isBlinking {
                RoundedRectangle(cornerRadius: 3)
                    .fill(Color(red: 0.10, green: 0.08, blue: 0.18).opacity(0.9))
                    .frame(width: 90, height: 5)
                    .offset(y: -28)
            }
        }
        .frame(width: 200, height: 200)
        .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .strokeBorder(.white.opacity(0.2), lineWidth: 1)
        )
        .scaleEffect(breathing ? 1.03 : 0.99)
        .offset(y: floating ? -4 : 4)
        .animation(.easeInOut(duration: 2.2).repeatForever(autoreverses: true), value: breathing)
        .animation(.easeInOut(duration: 3.0).repeatForever(autoreverses: true), value: floating)
        .onAppear {
            breathing = true
            floating = true
            startBlinkLoop()
        }
        .onDisappear { blinkTask?.cancel() }
    }

    @State private var breathing = false
    @State private var floating = false
    @State private var isBlinking = false
    @State private var blinkTask: Task<Void, Never>?

    /// 周期眨眼：睁 3.5 秒 → 闭 0.12 秒，循环。给待机立绘一点「活着」的感觉。
    private func startBlinkLoop() {
        blinkTask?.cancel()
        blinkTask = Task { @MainActor in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 3_500_000_000)
                guard !Task.isCancelled else { return }
                isBlinking = true
                try? await Task.sleep(nanoseconds: 120_000_000)
                isBlinking = false
            }
        }
    }

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
