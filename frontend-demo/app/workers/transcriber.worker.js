/* eslint-disable no-restricted-globals */
import { pipeline as createPipeline, env } from "@xenova/transformers";

let pipelineInstance = null;
let loading = false;

async function loadModel(name) {
  env.useBrowserCache = true;
  env.allowLocalModels = true;
  env.allowRemoteModels = false;
  env.localModelPath = "/models/";
  env.useFS = false;
  env.backends.onnx.wasm.numThreads = 1;
  env.backends.onnx.wasm.wasmPaths = "/wasm/";
  env.backends.onnx.logLevel = "error";

  const pipe = await createPipeline("automatic-speech-recognition", name, {
    progress_callback: (progress) => {
      if (
        progress.status === "download" &&
        typeof progress.progress === "number"
      ) {
        self.postMessage({ type: "model-loading", progress: progress.progress });
      }
    },
  });

  pipelineInstance = pipe;
  self.postMessage({ type: "model-ready" });
}

self.addEventListener("message", (event) => {
  void (async () => {
    const data = event.data;

    try {
      if (data.type === "load-model") {
        if (!pipelineInstance && !loading) {
          loading = true;
          try {
            await loadModel(data.modelName);
          } finally {
            loading = false;
          }
        } else {
          if (pipelineInstance) self.postMessage({ type: "model-ready" });
        }
        return;
      }

      if (data.type === "transcribe") {
        if (!pipelineInstance) {
          if (!loading) {
            loading = true;
            try {
              await loadModel(data.modelName);
            } finally {
              loading = false;
            }
          } else {
            await new Promise((resolve) => {
              const check = () => {
                if (pipelineInstance) resolve();
                else setTimeout(check, 100);
              };
              check();
            });
          }
        }

        self.postMessage({ type: "progress", progress: 0.5 });

        const audioArray = new Float32Array(data.audio);

        const result = await pipelineInstance(audioArray, {
          language: data.language || "es",
          task: "transcribe",
          return_timestamps: false,
        });

        self.postMessage({ type: "result", text: result.text });
      }
    } catch (err) {
      self.postMessage({
        type: "error",
        error: err.message || String(err),
        stack: err.stack,
      });
    }
  })();
});
