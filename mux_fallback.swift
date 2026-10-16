#!/usr/bin/env swift
// iPhone の空間オーディオ動画と同じ「APAC トラック (無効) + ステレオ AAC トラック (有効, fallback)」構造の
// 音声ファイルを作る。Apple の SpatialAudioCLI サンプル "bake" と同じ AVAssetWriter の組み立て方。
//
//   swift demo/synth/mux_fallback.swift <apac.mp4> <stereo.wav> <out.mov>
//
// - APAC はデコードせずパススルー (outputSettings nil + sourceFormatHint)
// - ステレオは AAC 256 kbps にエンコード
// - spatial input: marksOutputTrackAsEnabled = false, stereo への .audioFallback 関連付け
// - AVAssetWriterInputGroup(defaultInput: stereo) で alternate group にまとめる
import AVFoundation
import Foundation

let args = CommandLine.arguments
guard args.count == 4 else { print("usage: mux_fallback.swift <apac.mp4> <stereo.wav> <out.mov>"); exit(1) }
let apacURL = URL(fileURLWithPath: args[1])
let stereoURL = URL(fileURLWithPath: args[2])
let outURL = URL(fileURLWithPath: args[3])
try? FileManager.default.removeItem(at: outURL)

// 2 本の入力は writer がインターリーブするので、片方ずつ順に流すと互いを待って止まる。
// 1 つのループで「受け付けられる入力」にだけ追加していく。
final class Lane {
    let output: AVAssetReaderOutput, input: AVAssetWriterInput, label: String
    var pending: CMSampleBuffer? = nil, done = false, count = 0
    init(_ o: AVAssetReaderOutput, _ i: AVAssetWriterInput, _ l: String) { output = o; input = i; label = l }
    /// 進展があれば true
    func step() -> Bool {
        guard !done, input.isReadyForMoreMediaData else { return false }
        if pending == nil { pending = output.copyNextSampleBuffer() }
        guard let sb = pending else { input.markAsFinished(); done = true; return true }
        guard input.append(sb) else { print("append failed (\(label))"); input.markAsFinished(); done = true; return true }
        pending = nil; count += 1
        return true
    }
}

func pumpAll(_ lanes: [Lane], _ writer: AVAssetWriter) {
    var idle = 0
    while lanes.contains(where: { !$0.done }) {
        var progressed = false
        for l in lanes where l.step() { progressed = true }
        if !progressed {
            usleep(1000); idle += 1
            if idle % 2000 == 0 {  // 2 秒ごとに状況を出す
                print("stall: writer.status=\(writer.status.rawValue) err=\(String(describing: writer.error)) " +
                      lanes.map { "\($0.label): count=\($0.count) done=\($0.done) ready=\($0.input.isReadyForMoreMediaData) pending=\($0.pending != nil)" }.joined(separator: " | "))
                if idle >= 10000 { print("giving up"); exit(2) }
            }
        }
    }
}

let sema = DispatchSemaphore(value: 0)
Task {
    do {
        let apacAsset = AVURLAsset(url: apacURL)
        let stereoAsset = AVURLAsset(url: stereoURL)
        guard let apacTrack = try await apacAsset.loadTracks(withMediaType: .audio).first,
              let stereoTrack = try await stereoAsset.loadTracks(withMediaType: .audio).first else {
            print("no audio track"); exit(1)
        }
        let apacFormat = try await apacTrack.load(.formatDescriptions).first!

        let apacReader = try AVAssetReader(asset: apacAsset)
        let apacOut = AVAssetReaderTrackOutput(track: apacTrack, outputSettings: nil)  // パススルー
        apacReader.add(apacOut)
        let stereoReader = try AVAssetReader(asset: stereoAsset)
        let stereoOut = AVAssetReaderTrackOutput(track: stereoTrack, outputSettings: [
            AVFormatIDKey: kAudioFormatLinearPCM, AVLinearPCMBitDepthKey: 32, AVLinearPCMIsFloatKey: true,
            AVLinearPCMIsNonInterleaved: false, AVSampleRateKey: 48000, AVNumberOfChannelsKey: 2,
        ])
        stereoReader.add(stereoOut)

        let fileType: AVFileType = outURL.pathExtension.lowercased() == "mp4" ? .mp4 : .mov
        let writer = try AVAssetWriter(outputURL: outURL, fileType: fileType)
        let spatialInput = AVAssetWriterInput(mediaType: .audio, outputSettings: nil, sourceFormatHint: apacFormat)
        let stereoInput = AVAssetWriterInput(mediaType: .audio, outputSettings: [
            AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: 48000, AVNumberOfChannelsKey: 2,
            AVEncoderBitRateKey: 256_000,
        ])
        spatialInput.marksOutputTrackAsEnabled = false
        stereoInput.marksOutputTrackAsEnabled = true
        spatialInput.addTrackAssociation(withTrackOf: stereoInput, type: AVAssetTrack.AssociationType.audioFallback.rawValue)
        // 入力は先に個別に add してからグループを add する (グループだけだと入力が有効にならず、isReadyForMoreMediaData が永遠に false)
        guard writer.canAdd(stereoInput), writer.canAdd(spatialInput) else { print("cannot add inputs"); exit(1) }
        writer.add(stereoInput); writer.add(spatialInput)
        let group = AVAssetWriterInputGroup(inputs: [stereoInput, spatialInput], defaultInput: stereoInput)
        guard writer.canAdd(group) else { print("cannot add input group: \(String(describing: writer.error))"); exit(1) }
        writer.add(group)

        guard writer.startWriting() else { print("startWriting failed: \(String(describing: writer.error))"); exit(1) }
        apacReader.startReading(); stereoReader.startReading()
        writer.startSession(atSourceTime: .zero)
        let laneS = Lane(stereoOut, stereoInput, "stereo"), laneA = Lane(apacOut, spatialInput, "apac")
        pumpAll([laneS, laneA], writer)
        await writer.finishWriting()
        if writer.status == .failed { print("writer failed: \(String(describing: writer.error))"); exit(1) }
        if apacReader.status == .failed || stereoReader.status == .failed { print("reader failed"); exit(1) }
        print("wrote \(outURL.lastPathComponent): stereo AAC \(laneS.count) buffers (enabled), APAC passthrough \(laneA.count) buffers (disabled, fallback → stereo)")
    } catch { print("error: \(error)"); exit(1) }
    sema.signal()
}
sema.wait()
