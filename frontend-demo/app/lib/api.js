"use client";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export const SECTION_TO_UI = {
  "HISTORIA PROFESIONAL": "professional",
  "ANTECEDENTES FAMILIARES": "family",
  "ENFERMEDADES PASADAS": "past",
  INMUNIZACIONES: "immunizations",
  ALERGIAS: "allergies",
  HABITOS: "habits",
  HÁBITOS: "habits",
  TRATAMIENTOS: "treatments",
  "TRATAMIENTOS ACTUALES": "treatments",
};

export const UI_TO_PLNC_TARGET_SECTION = {
  professional: "historiaProfesional",
  family: "antecedentesFamiliares",
  past: "antecedentesEnfPasadas",
  immunizations: "antecedentesInmunizaciones",
  allergies: "antecedentesAlergias",
  habits: "habitos",
  treatments: "tratamientos",
};

export function uiSectionFromBackend(section) {
  if (!section) return "habits";
  const normalized = section.toUpperCase();
  return (
    SECTION_TO_UI[normalized] || normalized.toLowerCase().replace(/\s+/g, "_")
  );
}

export function suggestionToAssistantFindings(suggestion, question) {
  const codes = question?.codes || {};
  const targetSection =
    UI_TO_PLNC_TARGET_SECTION[suggestion.sectionId] ||
    suggestion.sectionId ||
    suggestion.backendSection;
  const selectedCodes = suggestion.selectedCodes?.length
    ? suggestion.selectedCodes
    : [suggestion.questionId];

  return selectedCodes.map((code) => {
    const label = codes[code];
    const isFreeText = label ? /#TEXTO_LIBRE#/i.test(label) : false;
    const value = isFreeText
      ? suggestion.freeText || suggestion.answer
      : label || suggestion.freeText || suggestion.answer;

    return {
      targetSection,
      code,
      description: suggestion.question,
      value,
    };
  });
}

export async function fetchAudioProviders() {
  const res = await fetch(`${API_BASE}/api/audio/providers`);
  if (!res.ok) throw new Error(`fetchAudioProviders ${res.status}`);
  return res.json();
}

export async function fetchIaProviders() {
  const res = await fetch(`${API_BASE}/api/ia/providers`);
  if (!res.ok) throw new Error(`fetchIaProviders ${res.status}`);
  return res.json();
}

export async function fetchSections(module = "history") {
  const res = await fetch(`${API_BASE}/api/questionnaire/${module}/sections`);
  if (!res.ok) throw new Error(`fetchSections ${res.status}`);
  return res.json();
}

export async function fetchQuestions(module, section) {
  const url = `${API_BASE}/api/questionnaire/${module}/sections/${encodeURIComponent(section)}/questions`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`fetchQuestions ${res.status}`);
  return res.json();
}

// Todas las preguntas del modulo (entrevista libre, sin filtrar por seccion).
export async function fetchAllQuestions(module) {
  const url = `${API_BASE}/api/questionnaire/${module}/questions`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`fetchAllQuestions ${res.status}`);
  return res.json();
}

// section vacia/null/"*" => extraccion sobre el modulo completo (entrevista libre).
function isModuleWide(section) {
  if (section == null) return true;
  const s = String(section).trim().toLowerCase();
  return s === "" || s === "*" || s === "all" || s === "todas";
}

export async function extractFromText({
  module = "history",
  section,
  text,
  iaProvider,
  iaModel,
}) {
  const body = { module, text };
  if (!isModuleWide(section)) body.section = section;
  if (iaProvider) body.ia_provider = iaProvider;
  if (iaModel) body.ia_model = iaModel;
  const res = await fetch(`${API_BASE}/api/v1/ia/extract-from-text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`extractFromText v1 ${res.status}: ${detail}`);
  }
  return res.json();
}

export async function transcribeAudio({
  audioBlob,
  filename = "audio.webm",
  language,
  provider,
  model,
  diarize,
  useClinicalPrompt = true,
  useCache = true,
}) {
  const form = new FormData();
  form.append("audio", audioBlob, filename);
  if (language) form.append("language", language);
  if (provider) form.append("provider", provider);
  if (model) form.append("model", model);
  if (diarize !== undefined) form.append("diarize", String(diarize));
  form.append("use_clinical_prompt", String(useClinicalPrompt));
  form.append("use_cache", String(useCache));
  const res = await fetch(`${API_BASE}/api/audio/transcribe`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`transcribeAudio ${res.status}: ${detail}`);
  }
  return res.json();
}

// Codifica buffers PCM s16le mono a WAV (cabecera RIFF). Devuelve Blob.
export function pcmChunksToWavBlob(int16Chunks, sampleRate = 16000) {
  let totalLen = 0;
  for (const c of int16Chunks) totalLen += c.byteLength;
  const buffer = new ArrayBuffer(44 + totalLen);
  const view = new DataView(buffer);

  function writeString(offset, s) {
    for (let i = 0; i < s.length; i++)
      view.setUint8(offset + i, s.charCodeAt(i));
  }
  // RIFF
  writeString(0, "RIFF");
  view.setUint32(4, 36 + totalLen, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true); // PCM chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  writeString(36, "data");
  view.setUint32(40, totalLen, true);

  let offset = 44;
  for (const c of int16Chunks) {
    new Uint8Array(buffer, offset, c.byteLength).set(new Uint8Array(c));
    offset += c.byteLength;
  }
  return new Blob([buffer], { type: "audio/wav" });
}

function isStreamStatusEvent(msg) {
  return [
    "connected",
    "loading_model",
    "ready",
    "audio_received",
    "transcribing",
    "audio.done",
    "suggestions.finalizing",
    "extracting",
    "extraction_error",
  ].includes(msg?.type);
}

function createQueuedSocketHandle(ws, { onError, onClose } = {}) {
  let doneResolving = null;
  let closedIntentionally = false;
  const pendingChunks = [];
  let resolveBackendReady = null;
  const socketReady = new Promise((resolve, reject) => {
    ws.addEventListener("open", () => {
      while (pendingChunks.length && ws.readyState === WebSocket.OPEN) {
        ws.send(pendingChunks.shift());
      }
      resolve();
    });
    ws.addEventListener("error", () => {
      reject(new Error("ws error"));
    }, { once: true });
  });
  const backendReady = new Promise((resolve) => {
    resolveBackendReady = resolve;
  });

  ws.addEventListener("close", () => {
    if (resolveBackendReady) resolveBackendReady();
    if (doneResolving) doneResolving();
    if (!closedIntentionally) onClose && onClose();
  });
  ws.addEventListener(
    "error",
    (err) => onError && onError(err.message || "ws error"),
  );

  return {
    ws,
    socketReady,
    backendReady,
    ready: backendReady,
    markIntentionalClose() {
      closedIntentionally = true;
    },
    markBackendReady() {
      if (resolveBackendReady) resolveBackendReady();
    },
    resolveDone() {
      if (doneResolving) doneResolving();
    },
    sendChunk(arrayBuffer) {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(arrayBuffer);
        return true;
      }
      if (ws.readyState === WebSocket.CONNECTING) {
        pendingChunks.push(arrayBuffer);
        return true;
      }
      return false;
    },
    stop(timeoutMs = 5000) {
      closedIntentionally = true;
      try {
        if (ws.readyState === WebSocket.OPEN) ws.send("__end__");
      } catch {}
      return new Promise((resolve) => {
        doneResolving = resolve;
        const timeout = setTimeout(() => {
          doneResolving = null;
          try {
            ws.close();
          } catch {}
          resolve();
        }, timeoutMs);
        const origResolve = resolve;
        doneResolving = () => {
          clearTimeout(timeout);
          origResolve();
        };
        if (ws.readyState !== WebSocket.OPEN && ws.readyState !== WebSocket.CONNECTING) {
          clearTimeout(timeout);
          doneResolving = null;
          resolve();
        }
      });
    },
  };
}

// WebSocket streaming. Devuelve un objeto { stop, ws, ready } y dispara onPartial / onFinal / onError.
export function openStreamingTranscription({
  provider,
  language = "es",
  onPartial,
  onFinal,
  onStatus,
  onError,
  onClose,
}) {
  const wsBase = API_BASE.replace(/^http/, "ws");
  const qs = new URLSearchParams();
  if (provider) qs.set("provider", provider);
  if (language) qs.set("language", language);
  const ws = new WebSocket(`${wsBase}/api/audio/stream?${qs.toString()}`);
  ws.binaryType = "arraybuffer";

  const handle = createQueuedSocketHandle(ws, { onError, onClose });

  ws.addEventListener("message", (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.error) {
        handle.markBackendReady();
        return onError && onError(msg.error);
      }
      if (isStreamStatusEvent(msg)) {
        if (msg.type === "ready") handle.markBackendReady();
        onStatus && onStatus(msg);
        return;
      }
      if (msg.done || msg.type === "done") {
        handle.resolveDone();
        return;
      }
      if (msg.is_final) onFinal && onFinal(msg);
      else if (msg.text) onPartial && onPartial(msg);
    } catch (err) {
      onError && onError(err.message || String(err));
    }
  });
  return handle;
}

// WebSocket v1: audio streaming + extraccion incremental en backend.
export function openStreamingAssist({
  provider,
  language = "es",
  module = "history",
  section,
  iaProvider,
  iaModel,
  onEvent,
  onPartial,
  onFinal,
  onSuggestions,
  onStatus,
  onError,
  onClose,
}) {
  const wsBase = API_BASE.replace(/^http/, "ws");
  const qs = new URLSearchParams();
  qs.set("module", module);
  if (!isModuleWide(section)) qs.set("section", section);
  if (provider) qs.set("provider", provider);
  if (language) qs.set("language", language);
  if (iaProvider) qs.set("ia_provider", iaProvider);
  if (iaModel) qs.set("ia_model", iaModel);
  const ws = new WebSocket(`${wsBase}/api/v1/audio/stream-and-extract?${qs.toString()}`);
  ws.binaryType = "arraybuffer";

  const handle = createQueuedSocketHandle(ws, { onError, onClose });

  ws.addEventListener("message", (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === "error" || msg.error) {
        handle.markBackendReady();
        return onError && onError(msg.error || "stream-and-extract error");
      }
      if (isStreamStatusEvent(msg)) {
        if (msg.type === "ready") handle.markBackendReady();
        onStatus && onStatus(msg);
        onEvent && onEvent(msg);
        return;
      }
      if (msg.type === "done") {
        handle.resolveDone();
        return;
      }
      if (msg.type === "transcript.partial") {
        onPartial && onPartial(msg);
      } else if (msg.type === "transcript.final") {
        onFinal && onFinal({ ...(msg.turn || {}), text: msg.turn?.text || "" });
      } else if (
        msg.type === "suggestions.partial" ||
        msg.type === "suggestions.final"
      ) {
        onSuggestions && onSuggestions(msg);
      }
      onEvent && onEvent(msg);
    } catch (err) {
      onError && onError(err.message || String(err));
    }
  });
  return {
    ...handle,
    stop() {
      return handle.stop(120000);
    },
  };
}

// --- Audit log v1 -----------------------------------------------------------

/**
 * Anade un evento al audit log encadenado del backend.
 *
 * Acciones soportadas (ver app/services/audit_log.AuditAction):
 *   "suggestion_proposed" | "suggestion_accepted" | "suggestion_edited"
 *   | "suggestion_rejected" | "session_started" | "session_closed"
 *
 * `evidence` se envia plano y el backend la hashea con SHA-256 antes de
 * persistir. NO se almacena texto literal en el audit log.
 *
 * En perfil `production`/`prototype_local` requiere header
 * `X-Internal-API-Key` (configurable via `apiKey`). En `demo` se admite sin.
 */
export async function appendAuditEvent({
  action,
  userId,
  patientId,
  questionId = "",
  selectedCodes = [],
  evidence = "",
  confidence = null,
  extra = {},
  apiKey,
} = {}) {
  if (!action || !userId || !patientId) {
    throw new Error("appendAuditEvent requires action, userId, patientId");
  }
  const headers = { "Content-Type": "application/json" };
  if (apiKey) headers["X-Internal-API-Key"] = apiKey;

  const res = await fetch(`${API_BASE}/api/v1/audit/events`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      action,
      user_id: userId,
      patient_id: patientId,
      question_id: questionId,
      selected_codes: selectedCodes,
      evidence,
      confidence,
      extra,
    }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`appendAuditEvent ${res.status}: ${detail}`);
  }
  return res.json();
}

export async function verifyAuditChain({ apiKey } = {}) {
  const headers = {};
  if (apiKey) headers["X-Internal-API-Key"] = apiKey;
  const res = await fetch(`${API_BASE}/api/v1/audit/verify`, { headers });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`verifyAuditChain ${res.status}: ${detail}`);
  }
  return res.json();
}

export async function listAuditEvents({ n = 50, apiKey } = {}) {
  const headers = {};
  if (apiKey) headers["X-Internal-API-Key"] = apiKey;
  const res = await fetch(`${API_BASE}/api/v1/audit/events?n=${n}`, { headers });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`listAuditEvents ${res.status}: ${detail}`);
  }
  return res.json();
}

// --- Review (decision humana sobre sugerencia) -----------------------------

/**
 * Registra decision humana sobre una sugerencia. Backend ejecuta audit_log
 * append automatico. Persistencia de estado en BBDD pendiente Hito 11+.
 *
 * @param {string} suggestionId  id local de la sugerencia (UUID o question_id-rand)
 * @param {object} opts
 * @param {"accepted"|"edited"|"rejected"} opts.decision
 * @param {string} opts.userId
 * @param {string} opts.patientId
 * @param {string} opts.questionId
 * @param {string[]} opts.selectedCodes
 * @param {string} [opts.evidence]  texto evidencia, se hashea backend
 * @param {number} [opts.confidence]
 * @param {string} [opts.freeText]  se hashea backend
 * @param {object} [opts.extra]
 * @param {string} [opts.apiKey]    X-Internal-API-Key si profile != demo
 */
export async function reviewSuggestion(suggestionId, opts) {
  if (!suggestionId) throw new Error("reviewSuggestion requires suggestionId");
  if (!opts?.decision || !opts.userId || !opts.patientId || !opts.questionId) {
    throw new Error(
      "reviewSuggestion requires decision, userId, patientId, questionId",
    );
  }
  const headers = { "Content-Type": "application/json" };
  if (opts.apiKey) headers["X-Internal-API-Key"] = opts.apiKey;

  const res = await fetch(
    `${API_BASE}/api/v1/suggestions/${encodeURIComponent(suggestionId)}/review`,
    {
      method: "PATCH",
      headers,
      body: JSON.stringify({
        decision: opts.decision,
        user_id: opts.userId,
        patient_id: opts.patientId,
        question_id: opts.questionId,
        selected_codes: opts.selectedCodes || [],
        evidence: opts.evidence || "",
        confidence: opts.confidence ?? null,
        free_text: opts.freeText || null,
        extra: opts.extra || {},
      }),
    },
  );
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`reviewSuggestion ${res.status}: ${detail}`);
  }
  return res.json();
}

// --- Audio v1 ---------------------------------------------------------------

export async function transcribeAndExtract({
  audioBlob,
  filename = "audio.webm",
  module = "history",
  section,
  language,
  provider,
  model,
  iaProvider,
  iaModel,
}) {
  const form = new FormData();
  form.append("audio", audioBlob, filename);
  form.append("module", module);
  if (!isModuleWide(section)) form.append("section", section);
  if (language) form.append("language", language);
  if (provider) form.append("provider", provider);
  if (model) form.append("model", model);
  if (iaProvider) form.append("ia_provider", iaProvider);
  if (iaModel) form.append("ia_model", iaModel);
  const res = await fetch(`${API_BASE}/api/v1/audio/transcribe-and-extract`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`transcribeAndExtract v1 ${res.status}: ${detail}`);
  }
  return res.json();
}

export function adaptSuggestion(raw, responseContext = {}, question = null) {
  const answer =
    raw.selected_labels && raw.selected_labels.length > 0
      ? raw.selected_labels.join(", ")
      : raw.free_text || "(sin valor)";
  const backendSection = raw.section || question?.section || responseContext.section;
  return {
    id: `${raw.question_id}-${Math.random().toString(36).slice(2, 8)}`,
    sectionId: uiSectionFromBackend(backendSection),
    backendSection,
    questionId: raw.question_id,
    question: raw.question_text || question?.text || raw.question_id,
    questionType: raw.question_type || question?.question_type,
    answer,
    selectedCodes: raw.selected_codes || [],
    selectedLabels: raw.selected_labels || [],
    freeText: raw.free_text || null,
    confidence: raw.confidence,
    evidence: raw.evidence,
    evidenceTurnIds: raw.evidence_turn_ids || [],
    status:
      raw.status ||
      (raw.technical_status === "discarded_by_graph" ? "conflict" : "suggested"),
    technicalStatus: raw.technical_status || "valid",
    reviewStatus: raw.review_status || "pending",
    riskFlags: raw.risk_flags || [],
    audioStart: raw.audio_start ?? null,
    audioEnd: raw.audio_end ?? null,
    speaker: raw.speaker || null,
    speakerCluster: raw.speaker_cluster || null,
    reason: raw.reason || null,
  };
}
