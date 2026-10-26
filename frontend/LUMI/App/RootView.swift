import SwiftUI

/// 根视图：原生 NavigationStack 承载启动页 → 聊天页 → 设置页。
struct RootView: View {
    @EnvironmentObject private var session: AppSession

    var body: some View {
        NavigationStack {
            Group {
                switch session.phase {
                case .launching:
                    LaunchView(status: session.launchStatus) {
                        session.enterChat()
                    }
                case .ready:
                    ChatView()
                        .environmentObject(session.chatViewModel)
                }
            }
            .animation(.easeInOut, value: session.phase == .ready)
        }
        .task {
            await session.bootstrap()
        }
    }
}
