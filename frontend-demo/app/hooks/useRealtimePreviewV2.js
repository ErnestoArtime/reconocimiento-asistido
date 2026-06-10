"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { VoskClient } from "@lichess-org/vosk-browser";

export const VOSK_MODELS = {
  small: { label: "Vosk Small (~38MB, rapido)", size: "small" },
  medium: { label: "Vosk Medium V2 (~325MB, sin rescore)", size: "medium" },
  large: { label: "Vosk Large (~1.4GB, preciso)", size: "large" },
};

function clearVoskIDB() {
  return new Promise((resolve) => {
    if (typeof indexedDB === "undefined") {
      resolve();
      return;
    }
    const dbs = indexedDB.databases ? indexedDB.databases() : Promise.resolve([]);
    dbs
      .then((databases) => {
        const voskDBs = databases.filter((db) => db.name && db.name.includes("vosk"));
        if (voskDBs.length === 0) {
          resolve();
          return;
        }
        let pending = voskDBs.length;
        const done = () => {
          pending -= 1;
          if (pending <= 0) resolve();
        };
        voskDBs.forEach((db) => {
          if (!db.name) {
            done();
            return;
          }
          const req = indexedDB.deleteDatabase(db.name);
          req.onsuccess = done;
          req.onerror = done;
          req.onblocked = done;
        });
      })
      .catch(() => resolve());
  });
}

export function useRealtimePreviewV2() {
  const [isSupported, setIsSupported] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [interimText, setInterimText] = useState("");
  const [finalText, setFinalText] = useState("");
  const [error, setError] = useState(null);

  const voskClientRef = useRef(null);
  const recognizerRef = useRef(null);
  const audioCtxRef = useRef(null);
  const processorRef = useRef(null);
  const sourceRef = useRef(null);
  const listeningRef = useRef(false);
  const finalRef = useRef("");
  const initGenRef = useRef(0);

  const init = useCallback(async (voskModelSize = "small") => {
    const myGen = ++initGenRef.current;

    try {
      const modelUrl = `/models/vosk/model-${voskModelSize}.tar.gz`;
      const wasmUrl = "/models/vosk/vosk.wasm";
      const workerUrl = "/models/vosk/vosk.worker.js?v=3";

      await clearVoskIDB();

      const model = new VoskClient({ modelUrl, wasmUrl, workerUrl });
      const client = await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          reject(new Error("Vosk V2 model loading timed out"));
        }, 120000);

        model.on("load", (message) => {
          clearTimeout(timeout);
          if (message?.result) {
            resolve(model);
            return;
          }
          reject(new Error("Failed to load Vosk V2 model"));
        });

        model.on("error", (message) => {
          clearTimeout(timeout);
          reject(new Error(message?.detail?.error || "Vosk V2 model error"));
        });
      });

      if (myGen !== initGenRef.current) {
        client.terminate();
        return;
      }
      if (typeof client.setLogLevel === "function") {
        client.setLogLevel(-1);
      }
      voskClientRef.current = client;
      setIsSupported(true);
      setError(null);
    } catch (e) {
      if (myGen !== initGenRef.current) return;
      console.error("Vosk V2 init error:", e);
      setIsSupported(false);
      const msg =
        voskModelSize === "large"
          ? "No se pudo cargar Vosk Large en el navegador. Verifica memoria disponible y que el archivo local este completo."
          : voskModelSize === "medium"
            ? "No se pudo cargar Vosk Medium en el navegador. Verifica memoria disponible y que el archivo local este completo."
          : "No se pudo cargar Vosk Small en el navegador. Verifica que el archivo local este completo.";
      setError(msg);
    }
  }, []);

  const start = useCallback((_lang, stream) => {
    const client = voskClientRef.current;
    if (!client) return;

    if (recognizerRef.current) {
      try {
        recognizerRef.current.remove();
      } catch {}
      recognizerRef.current = null;
    }

    const recognizer = new client.KaldiRecognizer(16000);
    recognizerRef.current = recognizer;

    recognizer.on("partialresult", (message) => {
      if (message?.result?.partial) {
        setInterimText(message.result.partial);
      }
    });

    recognizer.on("result", (message) => {
      if (message?.result?.text) {
        finalRef.current +=
          (finalRef.current ? " " : "") + message.result.text;
        setFinalText(finalRef.current);
        setInterimText("");
      }
    });

    const micStream = stream || null;
    if (micStream) {
      try {
        const audioCtx = new AudioContext();
        audioCtxRef.current = audioCtx;
        const source = audioCtx.createMediaStreamSource(micStream);
        sourceRef.current = source;
        const processor = audioCtx.createScriptProcessor(4096, 1, 1);
        processorRef.current = processor;

        processor.onaudioprocess = (event) => {
          if (!listeningRef.current) return;
          try {
            recognizer.acceptWaveform(event.inputBuffer);
          } catch {}
        };

        source.connect(processor);
        processor.connect(audioCtx.destination);
      } catch (e) {
        console.error("Vosk V2 audio pipeline error:", e);
        setError("Error al conectar el audio");
        return;
      }
    }

    setError(null);
    listeningRef.current = true;
    finalRef.current = "";
    setFinalText("");
    setInterimText("");
    setIsListening(true);
  }, []);

  const stop = useCallback(() => {
    listeningRef.current = false;

    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close();
      audioCtxRef.current = null;
    }

    const recognizer = recognizerRef.current;
    if (recognizer) {
      try {
        recognizer.retrieveFinalResult();
      } catch {}
      try {
        recognizer.remove();
      } catch {}
      recognizerRef.current = null;
    }

    setIsListening(false);
    return finalRef.current;
  }, []);

  const reset = useCallback(() => {
    setInterimText("");
    setFinalText("");
    finalRef.current = "";
    setError(null);
  }, []);

  function terminateVosk() {
    initGenRef.current++;
    listeningRef.current = false;
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close();
      audioCtxRef.current = null;
    }
    if (recognizerRef.current) {
      try {
        recognizerRef.current.remove();
      } catch {}
      recognizerRef.current = null;
    }
    if (voskClientRef.current) {
      voskClientRef.current.terminate();
      voskClientRef.current = null;
    }
  }

  useEffect(() => {
    return () => {
      terminateVosk();
    };
  }, []);

  return {
    isSupported,
    isListening,
    interimText,
    finalText,
    error,
    init,
    start,
    stop,
    reset,
  };
}
