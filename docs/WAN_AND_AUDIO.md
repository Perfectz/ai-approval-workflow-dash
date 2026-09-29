# Wan 3.0 and temporary audio

Documentation checked September 26, 2026. Recheck before implementing submission; these are preview-model limits.

## Provider contract

The official Model Studio API documents `wan3.0-video`, 30 fps, output up to 30 seconds, and asynchronous submission/polling. With video input, **total input-video duration plus output duration must not exceed 30 seconds**. Reference video and reference audio each have a **15-second aggregate limit**, with at most five files of each type. Multiple files do not bypass those totals. Audio accepts WAV/MP3; video accepts MP4/MOV. Reference audio/video require accessible URLs. Up to ten reference images are allowed.

Reference mode can combine images, video and audio. First-frame/first-and-last-frame mode cannot also accept those reference types. Thus the intended combined Blender + character sheet + temporary audio flow uses **multimodal reference mode**.

A 15-second output plus a matching 15-second preview meets the documented duration constraint. Ensure the rendered file actually ends at 15 seconds; a surplus frame can exceed the limit. At 30 fps this is 450 frames. Multiple preview references share the input-video budget.

Source: [Alibaba Cloud Wan 3.0 API reference](https://www.alibabacloud.com/help/en/model-studio/wan3-video-generation-api-reference).

## Handoff for each generation

Package one approved character sheet per relevant character, clean scene/shot reference images as needed, a picture-only Blender preview, the temporary dialogue WAV, and a timed prompt. Use a persistent mapping such as `CHAR_A -> blue mannequin -> Image 1`. Keep the ordered media mapping with the package; provider indices count images, videos and audio separately.

Describe what each reference controls: identity from character sheets; blocking and camera from the preview; speech timing from the WAV. The first test must check whether Wan follows all three. Input acceptance does not prove exact identity replacement, lip synchronization, words, or timing preservation.

`wan-plan.json` is a local preparation manifest, not a valid submitted API request. It intentionally has no live credentials, hosted media, creative approval or submission function. The output WAVs are temporary review assets; do not treat the synthetic voices as approved final performance.

At the generation stage, verify the current provider schema, media durations, resolution, aspect ratio and region together. Reuse the returned job ID when polling; do not resubmit because a task is taking time. Save the request, model/settings, media mapping, costs, result and user decision with every take.

## Audio implementation

Windows System.Speech produces local WAV takes using installed voices. The pipeline uses Microsoft's `SpeechSynthesizer.SetOutputToWaveFile` with an explicit PCM format, then measures the samples rather than estimating speech speed.

Source: [Microsoft SpeechSynthesizer WAV output](https://learn.microsoft.com/en-us/dotnet/api/system.speech.synthesis.speechsynthesizer.setoutputtowavefile?view=netframework-4.8.1).
