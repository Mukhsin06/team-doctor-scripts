import Foundation
import CoreGraphics

struct DisplayInfo: Codable {
    let displayId: UInt32
    let x: Double
    let y: Double
    let width: Double
    let height: Double
}

func emit(_ value: DisplayInfo) {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    if let data = try? encoder.encode(value), let text = String(data: data, encoding: .utf8) {
        print(text)
    }
}

func main() {
    let args = CommandLine.arguments
    guard args.count >= 2 else {
        fputs("usage: display_helper display-for-point <x> <y>\n", stderr)
        exit(2)
    }

    let mode = args[1]
    if mode == "display-for-point" {
        guard args.count >= 4, let x = Double(args[2]), let y = Double(args[3]) else {
            fputs("display-for-point requires x y\n", stderr)
            exit(2)
        }

        var matches = [CGDirectDisplayID](repeating: 0, count: 8)
        var count: UInt32 = 0
        let point = CGPoint(x: x, y: y)
        let error = CGGetDisplaysWithPoint(point, UInt32(matches.count), &matches, &count)
        guard error == .success else {
            fputs("CGGetDisplaysWithPoint failed\n", stderr)
            exit(1)
        }

        let displayId: CGDirectDisplayID
        if count > 0 {
            displayId = matches[0]
        } else {
            displayId = CGMainDisplayID()
        }

        let bounds = CGDisplayBounds(displayId)
        emit(
            DisplayInfo(
                displayId: displayId,
                x: bounds.origin.x,
                y: bounds.origin.y,
                width: bounds.size.width,
                height: bounds.size.height
            )
        )
        return
    }

    fputs("unknown mode\n", stderr)
    exit(2)
}

main()
