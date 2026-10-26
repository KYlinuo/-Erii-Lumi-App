import SwiftUI

struct ComposerBar: View {
    @Binding var text: String
    var isSending: Bool
    var onSend: () -> Void

    @FocusState private var focused: Bool

    var body: some View {
        HStack(alignment: .bottom, spacing: 10) {
            TextField("给 LUMI 发消息…", text: $text, axis: .vertical)
                .textFieldStyle(.plain)
                .focused($focused)
                .font(.system(size: 16))
                .foregroundStyle(.white)
                .lineLimit(1...5)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(
                    RoundedRectangle(cornerRadius: 20, style: .continuous)
                        .fill(Color.white.opacity(0.09))
                )
                .disabled(isSending)
                .accessibilityIdentifier("composerTextField")

            Button(action: onSend) {
                Image(systemName: isSending ? "hourglass" : "arrow.up.circle.fill")
                    .font(.system(size: 30))
                    .foregroundStyle(canSend ? Color(red: 0.72, green: 0.60, blue: 1.0) : .gray.opacity(0.5))
            }
            .buttonStyle(.plain)
            .disabled(!canSend)
            .accessibilityIdentifier("sendButton")
        }
        .padding(.horizontal, 12)
        .padding(.top, 8)
        .padding(.bottom, 6)
        .background(
            Color(red: 0.07, green: 0.07, blue: 0.12)
                .overlay(
                    Rectangle().fill(Color.white.opacity(0.06)).frame(height: 0.5),
                    alignment: .top
                )
        )
    }

    private var canSend: Bool {
        !isSending && !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
}

#Preview("Composer") {
    VStack {
        Spacer()
        ComposerBar(text: .constant("你好"), isSending: false) { }
        ComposerBar(text: .constant(""), isSending: true) { }
    }
    .background(Color(red: 0.07, green: 0.07, blue: 0.12))
}
