"use client";

import { useState, useCallback, useRef } from "react";

async function resampleAudio(
  audioBuffer,
  targetSampleRate = 16000,
) {
  const offlineCtx = new OfflineAudioContext(
    1,
    audioBuffer.duration * targetSampleRate,
    targetSampleRate,
  );
  const source = offlineCtx.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(offlineCtx.destination);
  source.start();
  const renderedBuffer = await offlineCtx.startRendering();
  return renderedBuffer.getChannelData(0);
}

export const DEFAULT_V2_MODEL = "Xenova/whisper-small";

export function useTranscriberV2() {
  const workerRef = useRef(null);
  const audioCtxRef = useRef(null);
  const modelReadyPromiseRef = useRef(null);
  const loadedModelRef = useRef(null);
  const loadingModelRef = useRef(null);
  const [isReady, setIsReady] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [loadProgress, setLoadProgress] = useState(0);

  const getAudioContext = useCallback(() => {
    if (!audioCtxRef.current || audioCtxRef.current.state === "closed") {
      audioCtxRef.current = new AudioContext();
    }
    return audioCtxRef.current;
  }, []);

  const createWorker = useCallback(() => {
    return new Worker(
      new URL("../workers/transcriber.worker.js", import.meta.url),
      { type: "module" },
    );
  }, []);

  const initWorker = useCallback(
    (modelName) => {
      return new Promise((resolve, reject) => {
        if (workerRef.current) workerRef.current.terminate();

        setIsLoading(true);
        setIsReady(false);
        setLoadProgress(0);
        loadingModelRef.current = modelName;

        const w = createWorker();
        workerRef.current = w;

        w.addEventListener("message", (event) => {
          const data = event.data;
          switch (data.type) {
            case "model-loading":
              setLoadProgress(data.progress);
              break;
            case "model-ready":
              setIsReady(true);
              loadedModelRef.current = modelName;
              setIsLoading(false);
              setLoadProgress(1);
              modelReadyPromiseRef.current = null;
              loadingModelRef.current = null;
              resolve();
              break;
            case "error":
              setIsLoading(false);
              modelReadyPromiseRef.current = null;
              loadingModelRef.current = null;
              reject(new Error(data.error));
              break;
          }
        });

        w.postMessage({ type: "load-model", modelName });
      });
    },
    [createWorker],
  );

  const ensureModelReady = useCallback(
    async (modelName) => {
      if (isReady && loadedModelRef.current === modelName) return;
      if (modelReadyPromiseRef.current && loadingModelRef.current === modelName) {
        return modelReadyPromiseRef.current;
      }
      modelReadyPromiseRef.current = initWorker(modelName);
      return modelReadyPromiseRef.current;
    },
    [isReady, initWorker],
  );

  const transcribe = useCallback(
    (audioBlob, modelName, language) => {
      return new Promise((resolve, reject) => {
        const worker = workerRef.current;
        if (!worker) {
          reject(new Error("Worker not initialized"));
          return;
        }

        const handleMessage = (event) => {
          const data = event.data;
          switch (data.type) {
            case "progress":
              setLoadProgress(data.progress);
              break;
            case "result":
              cleanup();
              resolve(data.text);
              break;
            case "error":
              cleanup();
              reject(new Error(data.error));
              break;
          }
        };

        const cleanup = () => {
          if (workerRef.current)
            workerRef.current.removeEventListener("message", handleMessage);
        };

        worker.addEventListener("message", handleMessage);

        const reader = new FileReader();
        reader.onload = () => {
          const arrayBuffer = reader.result;
          const ctx = getAudioContext();
          ctx.decodeAudioData(arrayBuffer)
            .then(async (audioBuffer) => {
              const pcmData = await resampleAudio(audioBuffer, 16000);
              worker.postMessage({
                type: "transcribe",
                audio: pcmData.buffer,
                modelName,
                language,
              });
            })
            .catch((err) => {
              cleanup();
              reject(
                new Error(
                  err instanceof Error
                    ? err.message
                    : "Failed to decode audio",
                ),
              );
            });
        };
        reader.onerror = () => {
          cleanup();
          reject(new Error("Failed to read audio blob"));
        };
        reader.readAsArrayBuffer(audioBlob);
      });
    },
    [getAudioContext],
  );

  const terminate = useCallback(() => {
    if (audioCtxRef.current && audioCtxRef.current.state !== "closed") {
      audioCtxRef.current.close();
      audioCtxRef.current = null;
    }
    if (workerRef.current) {
      workerRef.current.terminate();
      workerRef.current = null;
    }
    setIsReady(false);
    setIsLoading(false);
    setLoadProgress(0);
    modelReadyPromiseRef.current = null;
    loadedModelRef.current = null;
    loadingModelRef.current = null;
  }, []);

  return {
    isReady,
    isLoading,
    loadProgress,
    initWorker,
    ensureModelReady,
    transcribe,
    terminate,
  };
}
