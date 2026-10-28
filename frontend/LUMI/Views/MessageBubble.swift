import SwiftUI
import UIKit

/// 单条消息气泡。三套主题共用这一个组件，样式全部来自 `BubbleTheme`。
struct MessageBubble: View {
    let message: ChatMessage
    var theme: BubbleTheme = .sakura
    var appearance: AppearanceStore?
    /// 同一组里的第一条才显示时间
    var showTime: Bool = false
    /// 同一组的最后一条才显示头像（合并连续消息）
    var showAvatar: Bool = true
    var onRetry: (() -> Void)?
    var onReply: ((ChatMessage) -> Void)?
    var onDelete: ((ChatMessage) -> Void)?
    var onPreviewImage: ((UIImage) -> Void)?

    @ObservedObject private var mediaStore = MediaStore.shared
    @StateObject private var player = AudioPlayer()

    var body: some View {
        VStack(spacing: 6) {
            if showTime {
                Text(Self.timeLabel(message.createdAt))
                    .font(LUMIStyle.Font.bubbleMeta)
                    .foregroundStyle(.white.opacity(0.38))
                    .padding(.vertical, 4)
            }

            HStack(alignment: .top, spacing: 8) {
                if message.isFromUser {
                    Spacer(minLength: 52)
                } else if showAvatar {
                    avatar(isMine: false)
                } else {
                    Color.clear.frame(width: 30, height: 1)
                }

                VStack(alignment: message.isFromUser ? .trailing : .leading, spacing: 4) {
                    if let quoted = message.quotedText, !quoted.isEmpty {
                        quotedPreview(quoted)
                    }
                    bubble
                    footer
                }
                .frame(maxWidth: .infinity, alignment: message.isFromUser ? .trailing : .leading)

                if message.isFromUser {
                    if showAvatar { avatar(isMine: true) } else { Color.clear.frame(width: 30) }
                } else {
                    Spacer(minLength: 52)
                }
            }
            .padding(.horizontal, 12)
        }
        .padding(.top, showTime ? 2 : 0)
    }

    // MARK: - 头像

    @ViewBuilder
    private func avatar(isMine: Bool) -> some View {
        let custom = isMine ? appearance?.myAvatar : appearance?.characterAvatar
        Group {
            if let custom {
                Image(uiImage: custom)
                    .resizable()
                    .scaledToFill()
            } else if isMine {
                ZStack {
                    Circle().fill(
                        LinearGradient(
                            colors: [Color(red: 0.55, green: 0.66, blue: 0.98),
                                     Color(red: 0.72, green: 0.55, blue: 0.95)],
                            startPoint: .top, endPoint: .bottom
                        )
                    )
                    Image(systemName: "person.fill")
                        .font(.system(size: 14))
                        .foregroundStyle(.white.opacity(0.9))
                }
            } else {
                LUMIAvatar(size: 30)
            }
        }
        .frame(width: 30, height: 30)
        .clipShape(Circle())
        .overlay(Circle().strokeBorder(.white.opacity(0.14), lineWidth: 0.6))
    }

    // MARK: - 引用

    private func quotedPreview(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 12))
            .foregroundStyle(.white.opacity(0.55))
            .lineLimit(2)
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(Color.white.opacity(0.08))
            )
    }

    // MARK: - 气泡

    @ViewBuilder
    private var bubble: some View {
        switch message.kind {
        case .image: imageBubble
        case .audio: audioBubble
        case .text: textBubble
        }
    }

    private var textBubble: some View {
        Text(message.content)
            .font(LUMIStyle.Font.bubble)
            .foregroundStyle(message.isFromUser ? theme.outgoingText : theme.incomingText)
            .textSelection(.enabled)
            .padding(.horizontal, 12)
            .padding(.vertical, 9)
            .background(
                RoundedRectangle(cornerRadius: theme.bubbleCorner, style: .continuous)
                    .fill(bubbleStyle)
            )
            .overlay(
                RoundedRectangle(cornerRadius: theme.bubbleCorner, style: .continuous)
                    .strokeBorder(strokeColor, lineWidth: 0.8)
            )
            .opacity(message.status == .sending ? 0.72 : 1)
            .contextMenu { menu }
    }

    private var bubbleStyle: AnyShapeStyle {
        if message.isFromUser {
            return AnyShapeStyle(
                LinearGradient(colors: theme.outgoingColors, startPoint: .topLeading, endPoint: .bottomTrailing)
            )
        }
        return AnyShapeStyle(theme.incomingFill)
    }

    private var strokeColor: Color {
        if message.status == .failed { return Color.red.opacity(0.55) }
        return message.isFromUser ? Color.white.opacity(0.14) : theme.incomingStroke
    }

    // MARK: - 图片

    private var mediaKey: String { message.mediaID ?? "" }

    private var localImage: UIImage? {
        guard let path = message.localMediaPath else { return nil }
        return UIImage(contentsOfFile: path)
    }

    private var imageBubble: some View {
        Group {
            if let image = localImage ?? mediaStore.imageData(for: mediaKey).flatMap({ UIImage(data: $0) }) {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFit()
                    .onTapGesture { onPreviewImage?(image) }
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
                .frame(width: 168, height: 168)
            }
        }
        .frame(maxWidth: 210, maxHeight: 270)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(Color.white.opacity(0.12), lineWidth: 0.8)
        )
        .opacity(message.status == .sending ? 0.72 : 1)
        .task(id: mediaKey) {
            guard localImage == nil, !mediaKey.isEmpty else { return }
            await mediaStore.loadImage(mediaKey)
        }
        .contextMenu { menu }
    }

    // MARK: - 语音

    private var audioBubble: some View {
        HStack(spacing: 10) {
            Button {
                Task { await playAudio() }
            } label: {
                Image(systemName: player.playingID == message.id ? "pause.circle.fill" : "play.circle.fill")
                    .font(.system(size: 24))
                    .foregroundStyle(message.isFromUser ? theme.outgoingText : LUMIStyle.violet)
            }
            .buttonStyle(.plain)

            VStack(alignment: .leading, spacing: 4) {
                Capsule()
                    .fill(Color.white.opacity(0.26))
                    .frame(width: 70, height: 3)
                    .overlay(alignment: .leading) {
                        Capsule()
                            .fill(Color.white.opacity(0.85))
                            .frame(width: 70 * (player.playingID == message.id ? player.progress : 0), height: 3)
                    }
                Text(durationLabel)
                    .font(LUMIStyle.Font.bubbleMeta)
                    .foregroundStyle(.white.opacity(0.6))
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(
            RoundedRectangle(cornerRadius: theme.bubbleCorner, style: .continuous).fill(bubbleStyle)
        )
        .overlay(
            RoundedRectangle(cornerRadius: theme.bubbleCorner, style: .continuous)
                .strokeBorder(strokeColor, lineWidth: 0.8)
        )
        .opacity(message.status == .sending ? 0.72 : 1)
        .contextMenu { menu }
    }

    private var durationLabel: String {
        let seconds = max(1, Int((Double(message.durationMs ?? 0) / 1000).rounded()))
        return "\(seconds)″"
    }

    private func playAudio() async {
        if player.playingID == message.id { player.stop(); return }
        if let path = message.localMediaPath,
           let data = try? Data(contentsOf: URL(fileURLWithPath: path)) {
            player.play(id: message.id, data: data); return
        }
        guard !mediaKey.isEmpty else { return }
        if let data = await mediaStore.loadAudio(mediaKey) {
            player.play(id: message.id, data: data)
        }
    }

    // MARK: - 底部状态

    @ViewBuilder
    private var footer: some View {
        if message.status == .failed {
            HStack(spacing: 6) {
                Image(systemName: "exclamationmark.circle.fill")
                    .font(.system(size: 11))
                    .foregroundStyle(.red.opacity(0.85))
                Text(message.errorMessage ?? "发送失败")
                    .font(LUMIStyle.Font.bubbleMeta)
                    .foregroundStyle(.red.opacity(0.8))
                    .lineLimit(1)
                if let onRetry {
                    Button("重试", action: onRetry)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(LUMIStyle.violet)
                }
            }
        } else if message.isFromUser {
            Text(message.status == .sending ? "发送中…" : "已送达")
                .font(LUMIStyle.Font.bubbleMeta)
                .foregroundStyle(.white.opacity(0.3))
        } else if message.isMock {
            Text("演示回复 · 未接入模型")
                .font(LUMIStyle.Font.bubbleMeta)
                .foregroundStyle(.orange.opacity(0.72))
        } else if let model = message.model {
            Text(model)
                .font(LUMIStyle.Font.bubbleMeta)
                .foregroundStyle(.white.opacity(0.28))
        }
    }

    // MARK: - 长按菜单

    @ViewBuilder
    private var menu: some View {
        Button {
            UIPasteboard.general.string = message.content.isEmpty
                ? (message.kind == .image ? "[图片]" : "[语音]")
                : message.content
        } label: {
            Label("复制", systemImage: "doc.on.doc")
        }

        if message.kind == .text {
            Button { onReply?(message) } label: {
                Label("引用", systemImage: "quote.bubble")
            }
        }

        if message.status == .failed, let onRetry {
            Button(action: onRetry) { Label("重新发送", systemImage: "arrow.clockwise") }
        }

        Button(role: .destructive) {
            onDelete?(message)
        } label: {
            Label("删除", systemImage: "trash")
        }
    }

    static func timeLabel(_ date: Date) -> String {
        let formatter = DateFormatter()
        let calendar = Calendar.current
        if calendar.isDateInToday(date) {
            formatter.dateFormat = "HH:mm"
        } else if calendar.isDateInYesterday(date) {
            formatter.dateFormat = "'昨天' HH:mm"
        } else {
            formatter.dateFormat = "M月d日 HH:mm"
        }
        return formatter.string(from: date)
    }
}

/// 打字指示器：三点呼吸。
struct TypingIndicator: View {
    @State private var phase = 0

    var body: some View {
        HStack(spacing: 5) {
            ForEach(0..<3, id: \.self) { index in
                Circle()
                    .fill(Color.white.opacity(phase == index ? 0.85 : 0.28))
                    .frame(width: 6, height: 6)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(Color.white.opacity(0.10))
        )
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 50)
        .onAppear {
            withAnimation(.easeInOut(duration: 0.6).repeatForever(autoreverses: false)) {
                phase = 1
            }
        }
        .onReceive(Timer.publish(every: 0.45, on: .main, in: .common).autoconnect()) { _ in
            withAnimation(.easeInOut(duration: 0.4)) {
                phase = (phase + 1) % 3
            }
        }
        .accessibilityIdentifier("typingIndicator")
    }
}
