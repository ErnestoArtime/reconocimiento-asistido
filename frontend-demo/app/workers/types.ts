export interface WorkerMessageTranscribe {
  type: "transcribe";
  audio: ArrayBuffer;
  modelName: string;
  language: string;
}

export interface WorkerMessageLoadModel {
  type: "load-model";
  modelName: string;
}

export type WorkerMessage = WorkerMessageTranscribe | WorkerMessageLoadModel;

export interface WorkerMessageResult {
  type: "result";
  text: string;
}

export interface WorkerMessageError {
  type: "error";
  error: string;
  stack?: string;
}

export interface WorkerMessageModelReady {
  type: "model-ready";
}

export interface WorkerMessageModelLoading {
  type: "model-loading";
  progress: number;
}

export interface WorkerMessageProgress {
  type: "progress";
  progress: number;
}

export type WorkerResponse =
  | WorkerMessageResult
  | WorkerMessageError
  | WorkerMessageProgress
  | WorkerMessageModelReady
  | WorkerMessageModelLoading;
