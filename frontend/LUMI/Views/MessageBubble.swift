import SwiftUI
import UIKit

struct MessageBubble: View {
    let message: ChatMessage
    var onRetry: (() -> Void)?

    @ObservedObject private var mediaStore = MediaStore.shared
    @StateObject private var player = AudioPlayer()

    var body: some View {
        HStack(alignment: .bottom, spacing: 8) {
            if message.isFromUser { Spacer(minLength: 40) }

            if !message.isFromUser {
                LUMIAvatar(size: 32)
            }

            VStack(alignment: message.isFromUser ? .trailing : .leading, spacing: 5) {
                bubble

                if message.status == .failed {
                    failedFooter
                } else if message.isFromUser {
                    Text(statusText)
                        .font(.caption2)
                        .foregroundStyle(.white.opacity(0.35))
                } else if message.isMock {
                    // 明确告知：这条不是真实模型说的，避免用户误以为已接通
                    Text("演示回复 · 未接入模型")
                        .font(.caption2)
                        .foregroundStyle(.orange.opacity(0.7))
                } else if let model = message.model {
                    Text(model)
                        .font(.caption2)
                        .foregroundStyle(.white.opacity(0.3))
                }
            }
            .frame(maxWidth: .infinity, alignment: message.isFromUser ? .trailing : .leading)

            if !message.isFromUser { Spacer(minLength: 40) }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private var bubble: some View {
        switch message.kind {
        case .image:
            imageBubble
        case .audio:
            audioBubble
        case .text:
            textBubble
        }
    }

    private var textBubble: some View {
        Text(message.content)
            .font(.system(size: 16))
            .foregroundStyle(message.isFromUser ? .white : Color(red: 0.96, green: 0.95, blue: 0.99))
            .textSelection(.enabled)
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(bubbleBackground)
            .overlay(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .strokeBorder(message.status == .failed ? Color.red.opacity(0.55) : .clear, lineWidth: 1)
            )
            .opacity(message.status == .sending ? 0.72 : 1)
    }

    // MARK: - 图片

    private var imageBubble: some View {
        Group {
            if let image = localImage {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFit()
            } else if let data = mediaStore.imageData(for: mediaKey), let image = UIImage(data: data) {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFit()
            } else {
                ZStack {
                    Color.white.opacity(0.08)
                    VStack(spacing: 6) {
                        Image(systemName: mediaStore.hasFailed(mediaKey) ? "exclamationmark.triangle" : "photo")
                            .font(.system(size: 22))
                        Text(mediaStore.hasFailed(mediaKey) ? "图片加载失败" : "加载中…")
                            .font(.caption2)
                    }
                    .foregroundStyle(.white.opacity(0.6))
                }
                .frame(width: 180, height: 180)
            }
        }
        .frame(maxWidth: 220, maxHeight: 280)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(Color.white.opacity(0.12), lineWidth: 0.8)
        )
        .opacity(message.status == .sending ? 0.72 : 1)
        .task(id: mediaKey) {
            guard localImage == nil else { return }
            await mediaStore.loadImage(mediaKey)
        }
    }

    private var mediaKey: String { message.mediaID ?? "" }

    private var localImage: UIImage? {
        guard let path = message.localMediaPath else { return nil }
        return UIImage(contentsOfFile: path)
    }

    // MARK: - 语音

    private var audioBubble: some View {
        HStack(spacing: 10) {
            Button {
                Task { await playAudio() }
            } label: {
                Image(systemName: player.playingID == message.id ? "pause.circle.fill" : "play.circle.fill")
                    .font(.system(size: 26))
                    .foregroundStyle(message.isFromUser ? .white : Color(red: 0.72, green: 0.60, blue: 1.0))
            }
            .buttonStyle(.plain)

            VStack(alignment: .leading, spacing: 4) {
                Capsule()
                    .fill(Color.white.opacity(0.28))
                    .frame(width: 74, height: 4)
                    .overlay(alignment: .leading) {
                        Capsule()
                            .fill(Color.white.opacity(0.85))
                            .frame(width: player.playingID == message.id ? 74 * player.progress : 0, height: 4)
                    }
                Text(durationLabel)
                    .font(.caption2)
                    .foregroundStyle(.white.opacity(0.65))
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(bubbleBackground)
        .opacity(message.status == .sending ? 0.72 : 1)
        .accessibilityLabel("语音消息，\(durationLabel)")
    }

    private var durationLabel: String {
        let ms = message.durationMs ?? 0
        let seconds = max(1, Int((Double(ms) / 1000).rounded()))
        return "\(seconds)″"
    }

    private func playAudio() async {
        guard player.playingID != message.id else {
            player.stop()
            return
        }
        if let path = message.localMediaPath, let data = try? Data(contentsOf: URL(fileURLWithPath: path)) {
            player.play(id: message.id, data: data)
            return
        }
        guard !mediaKey.isEmpty else { return }
        if let data = await mediaStore.loadAudio(mediaKey) {
            player.play(id: message.id, data: data)
        }
    }

    private var bubbleBackground: some View {
        RoundedRectangle(cornerRadius: 18, style: .continuous)
            .fill(
                message.isFromUser
                ? AnyShapeStyle(
                    LinearGradient(
                        colors: [Color(red: 0.49, green: 0.36, blue: 0.95),
                                 Color(red: 0.32, green: 0.47, blue: 0.95)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                : AnyShapeStyle(Color.white.opacity(0.10))
            )
    }

    private var failedFooter: some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.caption2)
                .foregroundStyle(.red)
            Text(message.errorMessage ?? "发送失败")
                .font(.caption2)
                .foregroundStyle(.red.opacity(0.9))
                .fixedSize(horizontal: false, vertical: true)
            if let onRetry {
                Button("重试", action: onRetry)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(Color(red: 0.75, green: 0.85, blue: 1.0))
                    .accessibilityIdentifier("retryButton")
            }
        }
    }

    private var statusText: String {
        switch message.status {
        case .sending: return "发送中…"
        case .sent: return "已送达"
        case .failed: return "发送失败"
        }
    }
}

/// 等待真实模型回复时的「正在输入」指示（不是假消息，是可辨识的加载态）。
struct TypingIndicator: View {
    @State private var phase = 0

    var body: some View {
        HStack(alignment: .bottom, spacing: 8) {
            LUMIAvatar(size: 32)
            HStack(spacing: 5) {
                ForEach(0..<3, id: \.self) { index in
                    Circle()
                        .fill(Color.white.opacity(phase == index ? 0.85 : 0.28))
                        .frame(width: 7, height: 7)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 13)
            .background(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .fill(Color.white.opacity(0.10))
            )
            Spacer(minLength: 40)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 4)
        .accessibilityIdentifier("typingIndicator")
        .onAppear {
            withAnimation(.easeInOut(duration: 0.6).repeatForever(autoreverses: false)) {
                phase = 1
            }
        }
        // 用 onReceive 而不是 Timer：回调在 MainActor 上执行，
        // 且随视图消失自动断开，不会留下永不 invalidate 的计时器。
        .onReceive(Timer.publish(every: 0.45, on: .main, in: .common).autoconnect()) { _ in
            withAnimation(.easeInOut(duration: 0.4)) {
                phase = (phase + 1) % 3
            }
        }
    }
}

#Preview("Bubbles") {
    VStack(spacing: 12) {
        MessageBubble(message: ChatMessage(role: .assistant, content: "嗨，我是 LUMI。今天想聊点什么？", model: "deepseek-chat"))
        MessageBubble(message: ChatMessage(role: .user, content: "讲个冷笑话", status: .sent))
        MessageBubble(message: ChatMessage(role: .user, content: "在吗", status: .failed, errorMessage: "请求超时了，服务器没有及时响应。"), onRetry: {})
        TypingIndicator()
    }
    .padding()
    .background(Color(red: 0.08, green: 0.08, blue: 0.14))
}
