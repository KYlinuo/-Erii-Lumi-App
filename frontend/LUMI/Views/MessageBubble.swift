import SwiftUI

struct MessageBubble: View {
    let message: ChatMessage
    var onRetry: (() -> Void)?

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
                } else if let model = message.model {
                    Text(model)
                        .font(.caption2)
                        .foregroundStyle(.white.opacity(0.35))
                }
            }
            .frame(maxWidth: .infinity, alignment: message.isFromUser ? .trailing : .leading)

            if !message.isFromUser { Spacer(minLength: 40) }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 4)
    }

    private var bubble: some View {
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
            Timer.scheduledTimer(withTimeInterval: 0.45, repeats: true) { _ in
                withAnimation(.easeInOut(duration: 0.4)) {
                    phase = (phase + 1) % 3
                }
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
