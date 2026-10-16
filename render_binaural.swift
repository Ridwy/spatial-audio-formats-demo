#!/usr/bin/env swift
// spec JSON に書かれた音源を AVAudioEnvironmentNode (Apple の HRTF) でバイノーラルにオフラインレンダリングする。
// Channel / Object / Scene のどれも同じレンダラーを通すための共通部品。
//
//   swift demo/synth/render_binaural.swift <spec.json> <out.wav> [listenerYawDeg]
//
// spec: {"sampleRate":48000, "sources":[
//          {"file":"a.wav","channel":0,"az":30,"el":0,"label":"L"},        // 固定位置
//          {"file":"src.wav","channel":0,"trajectory":"trajectory.json"}    // 位置列 [[t, az, el, dist], ...]
//       ]}
// 方位は AmbiX 流 (正面 0°, 左 +90°)。listenerYawDeg は聴き手が左を向く角度 (+90 で左向き)。
import AVFoundation
import Foundation

struct Src: Decodable {
    var file: String
    var channel: Int
    var az: Double?
    var el: Double?
    var label: String?
    var trajectory: String?
}
struct Spec: Decodable {
    var sampleRate: Double
    var distance: Double
    var sources: [Src]
}

let args = CommandLine.arguments
guard args.count >= 3 else { print("usage: render_binaural.swift <spec.json> <out.wav> [yawDeg]"); exit(1) }
let specURL = URL(fileURLWithPath: args[1])
let outURL = URL(fileURLWithPath: args[2])
let yawDeg = args.count >= 4 ? Double(args[3])! : 0.0
let dir = specURL.deletingLastPathComponent()
let spec = try JSONDecoder().decode(Spec.self, from: Data(contentsOf: specURL))
let sr = spec.sampleRate
let blockFrames: AVAudioFrameCount = 480  // 10 ms。この粒度で位置を更新する

// 方位 az (左 +), 仰角 el, 距離 d → AVAudioEnvironmentNode の座標 (前 -z, 右 +x, 上 +y)
func point(az: Double, el: Double, d: Double) -> AVAudio3DPoint {
    let a = (az - yawDeg) * .pi / 180, e = el * .pi / 180  // 聴き手が左を向く = 音源が右へ回る
    return AVAudio3DPoint(x: Float(-d * cos(e) * sin(a)), y: Float(d * sin(e)), z: Float(-d * cos(e) * cos(a)))
}

func loadMono(_ url: URL, channel: Int) throws -> AVAudioPCMBuffer {
    let f = try AVAudioFile(forReading: url)
    let all = AVAudioPCMBuffer(pcmFormat: f.processingFormat, frameCapacity: AVAudioFrameCount(f.length))!
    try f.read(into: all)
    precondition(f.processingFormat.sampleRate == sr, "sample rate mismatch: \(url.lastPathComponent)")
    let mono = AVAudioFormat(standardFormatWithSampleRate: sr, channels: 1)!
    let out = AVAudioPCMBuffer(pcmFormat: mono, frameCapacity: all.frameLength)!
    out.frameLength = all.frameLength
    let src = all.floatChannelData![channel], dst = out.floatChannelData![0]
    for i in 0..<Int(all.frameLength) { dst[i] = src[i] }
    return out
}

let engine = AVAudioEngine()
let env = AVAudioEnvironmentNode()
env.outputType = .headphones
env.renderingAlgorithm = .HRTFHQ
env.reverbParameters.enable = false
env.distanceAttenuationParameters.referenceDistance = Float(spec.distance)  // 1.5 m で 0 dB
env.distanceAttenuationParameters.distanceAttenuationModel = .inverse
env.listenerPosition = AVAudio3DPoint(x: 0, y: 0, z: 0)
env.listenerVectorOrientation = AVAudio3DVectorOrientation(forward: AVAudio3DVector(x: 0, y: 0, z: -1),
                                                           up: AVAudio3DVector(x: 0, y: 1, z: 0))
engine.attach(env)
let stereo = AVAudioFormat(standardFormatWithSampleRate: sr, channels: 2)!
engine.connect(env, to: engine.mainMixerNode, format: stereo)
engine.connect(engine.mainMixerNode, to: engine.outputNode, format: stereo)

var players: [(AVAudioPlayerNode, [[Double]]?)] = []
var totalFrames: AVAudioFrameCount = 0
for s in spec.sources {
    let buf = try loadMono(dir.appendingPathComponent(s.file), channel: s.channel)
    totalFrames = max(totalFrames, buf.frameLength)
    let p = AVAudioPlayerNode()
    p.renderingAlgorithm = .HRTFHQ
    p.sourceMode = .pointSource
    engine.attach(p)
    engine.connect(p, to: env, format: buf.format)
    var traj: [[Double]]? = nil
    if let tj = s.trajectory {
        traj = try JSONDecoder().decode([[Double]].self, from: Data(contentsOf: dir.appendingPathComponent(tj)))
        p.position = point(az: traj![0][1], el: traj![0][2], d: traj![0][3])
    } else {
        p.position = point(az: s.az ?? 0, el: s.el ?? 0, d: spec.distance)
    }
    p.scheduleBuffer(buf, at: nil, options: [], completionHandler: nil)
    players.append((p, traj))
}

try engine.enableManualRenderingMode(.offline, format: stereo, maximumFrameCount: blockFrames)
try engine.start()
for (p, _) in players { p.play() }

let outFile = try AVAudioFile(forWriting: outURL, settings: [
    AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: sr, AVNumberOfChannelsKey: 2,
    AVLinearPCMBitDepthKey: 32, AVLinearPCMIsFloatKey: true, AVLinearPCMIsNonInterleaved: false,
], commonFormat: .pcmFormatFloat32, interleaved: false)
let outBuf = AVAudioPCMBuffer(pcmFormat: engine.manualRenderingFormat, frameCapacity: blockFrames)!

var rendered: AVAudioFrameCount = 0
while rendered < totalFrames + AVAudioFrameCount(sr * 0.3) {  // HRTF の尾を少し残す
    let t = Double(rendered) / sr
    for (p, traj) in players {
        guard let traj = traj else { continue }
        // 位置列から現在時刻のサンプルを選ぶ (10 ms 刻みなので index で引く)
        let idx = min(Int(t / 0.01), traj.count - 1)
        let r = traj[idx]
        p.position = point(az: r[1], el: r[2], d: r[3])
    }
    let status = try engine.renderOffline(blockFrames, to: outBuf)
    guard status == .success else { print("render status \(status.rawValue)"); break }
    try outFile.write(from: outBuf)
    rendered += outBuf.frameLength
}
engine.stop()
outFile.close()  // ヘッダ (データ長) を書き戻す。閉じずに終了すると audio bytes 0 の WAV になる
print("wrote \(outURL.lastPathComponent)  \(Double(rendered) / sr) s  yaw \(yawDeg)°  sources \(players.count)")
