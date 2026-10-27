import Foundation

do {
    let data = FileHandle.standardInput.readDataToEndOfFile()
    let paths = try JSONDecoder().decode([String].self, from: data)
    let manager = FileManager.default
    var failures: [String] = []
    for path in paths {
        let url = URL(fileURLWithPath: path)
        do {
            guard manager.isUbiquitousItem(at: url) else {
                failures.append(url.lastPathComponent)
                continue
            }
            try manager.startDownloadingUbiquitousItem(at: url)
        } catch {
            failures.append(url.lastPathComponent)
        }
    }
    let result = try JSONSerialization.data(withJSONObject: ["failures": failures])
    FileHandle.standardOutput.write(result)
} catch {
    FileHandle.standardError.write(Data(error.localizedDescription.utf8))
    exit(1)
}
