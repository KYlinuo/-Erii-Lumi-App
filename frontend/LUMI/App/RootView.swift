import SwiftUI

/// 根视图：启动页 → 主界面（Tab：聊天 / 人物 / 记忆 / 日记 / 设置）。
struct RootView: View {
    @EnvironmentObject private var session: AppSession

    var body: some View {
        Group {
            switch session.phase {
            case .launching:
                LaunchView(status: session.launchStatus) {
                    session.enterChat()
                }
            case .ready:
                MainTabs()
                    .environmentObject(session)
            }
        }
        .animation(.easeInOut, value: session.phase == .ready)
        .task {
            await session.bootstrap()
        }
    }
}

/// 主界面：原生 TabView + 统一视觉。
struct MainTabs: View {
    @EnvironmentObject private var session: AppSession

    var body: some View {
        TabView {
            ChatView()
                .environmentObject(session.chatViewModel)
                .tabItem {
                    Label("聊天", systemImage: "bubble.left.and.bubble.right.fill")
                }

            ProfileView(viewModel: session.personaViewModel)
                .environmentObject(session.chatViewModel)
                .tabItem {
                    Label("人物", systemImage: "person.crop.circle.fill")
                }

            MemoryView(viewModel: session.memoryViewModel)
                .tabItem {
                    Label("记忆", systemImage: "brain")
                }

            DiaryView(viewModel: session.diaryViewModel)
                .tabItem {
                    Label("日记", systemImage: "book.closed.fill")
                }

            SettingsView()
                .environmentObject(session.chatViewModel)
                .tabItem {
                    Label("设置", systemImage: "gearshape.fill")
                }
        }
        .tint(LUMIStyle.violet)
        .onAppear {
            // 统一 Tab 栏的玻璃质感
            let appearance = UITabBarAppearance()
            appearance.configureWithTransparentBackground()
            appearance.backgroundEffect = UIBlurEffect(style: .systemThinMaterialDark)
            UITabBar.appearance().standardAppearance = appearance
            UITabBar.appearance().scrollEdgeAppearance = appearance
        }
    }
}
