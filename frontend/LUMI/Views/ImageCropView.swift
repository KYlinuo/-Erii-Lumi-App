import SwiftUI
import UIKit

/// 头像裁切：图片可缩放/拖动，中心圆形框，确认后按圆形区域裁切输出。
///
/// 用 UIGraphicsImageRenderer 精确裁切（不引入第三方库），
/// 把「缩放 + 偏移后的显示状态」回算到原图坐标系，再裁成圆形。
struct ImageCropView: View {
    let image: UIImage
    let onComplete: (UIImage) -> Void

    @Environment(\.dismiss) private var dismiss

    @State private var scale: CGFloat = 1.0
    @State private var lastScale: CGFloat = 1.0
    @State private var offset: CGSize = .zero
    @State private var lastOffset: CGSize = .zero

    /// 裁切框边长（与显示框一致）
    private let cropSize: CGFloat = 300

    var body: some View {
        VStack(spacing: 20) {
            Spacer()

            ZStack {
                // 遮罩底色
                Color.black

                // 图片：缩放 + 拖动
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
                    .frame(width: cropSize, height: cropSize)
                    .clipped()
                    .scaleEffect(scale)
                    .offset(offset)
                    .gesture(
                        SimultaneousGesture(
                            MagnificationGesture()
                                .onChanged { value in
                                    scale = min(max(lastScale * value, 1.0), 4.0)
                                }
                                .onEnded { _ in lastScale = scale },
                            DragGesture()
                                .onChanged { value in
                                    offset = CGSize(
                                        width: lastOffset.width + value.translation.width,
                                        height: lastOffset.height + value.translation.height
                                    )
                                }
                                .onEnded { _ in lastOffset = offset }
                        )
                    )

                // 圆形裁切框
                Circle()
                    .strokeBorder(.white, lineWidth: 2)
                    .frame(width: cropSize, height: cropSize)

                // 半透明遮罩（框外区域变暗）
                Circle()
                    .fill(Color.black.opacity(0.35))
                    .frame(width: cropSize, height: cropSize)
                    .blendMode(.destinationOut)
                    .allowsHitTesting(false)
            }
            .frame(width: cropSize, height: cropSize)
            .clipShape(Circle())
            .overlay(Circle().strokeBorder(.white, lineWidth: 2))

            Text("拖动调整位置，双指缩放")
                .font(.footnote)
                .foregroundStyle(.secondary)

            HStack(spacing: 24) {
                Button("取消") { dismiss() }
                    .foregroundStyle(.secondary)

                Button("使用") { confirmCrop() }
                    .fontWeight(.semibold)
            }

            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.black.ignoresSafeArea())
        .preferredColorScheme(.dark)
    }

    private func confirmCrop() {
        let side = cropSize * scale
        // 显示后的图片尺寸（scaledToFill 已铺满 cropSize，缩放后为 side）
        let displaySize = CGSize(width: side, height: side)
        // 偏移：offset 是「图片中心相对框中心的偏移」，绘制时图片左上角在
        // (cropSize - side)/2 + offset.width - (cropSize/2) 化简为：
        let originX = (cropSize - side) / 2 + offset.width
        let originY = (cropSize - side) / 2 + offset.height

        let renderer = UIGraphicsImageRenderer(size: CGSize(width: cropSize, height: cropSize))
        let cropped = renderer.image { _ in
            image.draw(in: CGRect(origin: CGPoint(x: originX, y: originY), size: displaySize))
        }
        // 圆形裁剪
        if let rounded = cropped.circular(cropSize: cropSize) {
            onComplete(rounded)
            dismiss()
        }
    }
}

extension UIImage {
    /// 把图片裁成指定大小的圆形。
    func circular(cropSize: CGFloat) -> UIImage? {
        let size = CGSize(width: cropSize, height: cropSize)
        let renderer = UIGraphicsImageRenderer(size: size)
        let result = renderer.image { _ in
            let rect = CGRect(origin: .zero, size: size)
            UIBezierPath(ovalIn: rect).addClip()
            draw(in: rect)
        }
        return result
    }
}
