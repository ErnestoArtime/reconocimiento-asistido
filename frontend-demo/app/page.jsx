"use client";

import {
  Activity,
  BadgePlus,
  BriefcaseBusiness,
  Check,
  ChevronDown,
  ChevronUp,
  ClipboardList,
  FileText,
  FlaskConical,
  Grid2X2,
  Hospital,
  Loader2,
  Menu,
  Mic,
  Plus,
  ShieldCheck,
  Sparkles,
  Square,
  Stethoscope,
  Upload,
  User,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import SuggestionsPanel from "./components/SuggestionsPanel";

import {
  adaptSuggestion,
  extractFromText,
  fetchAllQuestions,
  fetchAudioProviders,
  fetchIaProviders,
  fetchSections,
  openStreamingAssist,
  openStreamingTranscription,
  pcmChunksToWavBlob,
  suggestionToAssistantFindings,
  transcribeAndExtract,
  transcribeAudio,
} from "./lib/api";
import { useTranscriberV2, DEFAULT_V2_MODEL } from "./hooks/useTranscriberV2";
import {
  useRealtimePreviewV2,
  VOSK_MODELS,
} from "./hooks/useRealtimePreviewV2";
import AuditPanel from "./components/AuditPanel";

const initialSections = [
  { id: "professional", title: "Historia Profesional", open: false, rows: [] },
  { id: "family", title: "Antecedentes Familiares", open: false, rows: [] },
  { id: "past", title: "Enfermedades Pasadas", open: false, rows: [] },
  { id: "immunizations", title: "Inmunizaciones", open: false, rows: [] },
  { id: "allergies", title: "Alergias", open: false, rows: [] },
  { id: "habits", title: "Hábitos", open: false, rows: [] },
  { id: "treatments", title: "Tratamientos", open: false, rows: [] },
];

const navItems = [
  ["Pantalla de Estado", Grid2X2],
  ["Clientes", Hospital],
  ["Laboral", BriefcaseBusiness],
  ["Seguros", ShieldCheck],
  ["Privados", User],
  ["Reconocimientos", BadgePlus, true],
  ["Análisis", FlaskConical],
  ["Definiciones", ClipboardList],
];

const tabs = [
  ["Datos Generales", User],
  ["Historia Clínica", Activity, true],
  ["Exploración Física", Stethoscope],
  ["Pruebas Complementarias", FlaskConical],
  ["Consultas Externas", Plus],
  ["Conclusiones", FileText],
];

export default function Home() {
  const [sections, setSections] = useState(initialSections);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [auditOpen, setAuditOpen] = useState(false);
  const [accepted, setAccepted] = useState([]);

  function toggleSection(sectionId) {
    setSections((current) =>
      current.map((section) =>
        section.id === sectionId
          ? { ...section, open: !section.open }
          : section,
      ),
    );
  }

  function acceptSuggestion(suggestion) {
    setAccepted((current) =>
      current.includes(suggestion.id) ? current : [...current, suggestion.id],
    );
    setSections((current) =>
      current.map((section) => {
        if (section.id !== suggestion.sectionId) return section;
        const nextRows = section.rows.filter(
          (row) => row.id !== suggestion.questionId,
        );
        nextRows.push({
          id: suggestion.questionId,
          question: suggestion.question,
          answer: suggestion.answer,
          source: "ai",
        });
        return {
          ...section,
          open: true,
          rows: nextRows,
        };
      }),
    );
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brandMark">R</div>
          <span>Medical Prevenor</span>
        </div>
        <NavGroup title="General" items={navItems.slice(0, 1)} />
        <NavGroup title="Área de Salud" items={navItems.slice(1)} />
        <NavGroup title="Sistema" items={[["Design System", ClipboardList]]} />
      </aside>

      <section className="workspace">
        <header className="topbar">
          <button className="iconButton" aria-label="Menu">
            <Menu size={24} />
          </button>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button
              className="primaryButton subtle"
              onClick={() => setAuditOpen(true)}
              title="Audit log (trazabilidad clinica)"
              style={{ fontSize: 13, padding: "6px 12px" }}
            >
              <ShieldCheck size={16} />
              <span>Audit</span>
            </button>
            <div className="userBadge">
              <span>Usuario Demo</span>
              <strong>U</strong>
            </div>
          </div>
        </header>

        <div className="patientStrip">
          <div className="avatar">42</div>
          <div>
            <h1>Paciente Demo</h1>
            <p>Particular | Centro: Centro Médico Privado</p>
          </div>
        </div>

        <div className="content">
          <nav className="tabs">
            {tabs.map(([label, Icon, active]) => (
              <button key={label} className={active ? "tab active" : "tab"}>
                <Icon size={18} />
                <span>{label}</span>
              </button>
            ))}
          </nav>

          <section className="sectionHeader">
            <div>
              <h2>Historia Clínica</h2>
              <p>Antecedentes personales y familiares del trabajador</p>
            </div>
            <button
              className="assistButton"
              onClick={() => setAssistantOpen(true)}
            >
              <Sparkles size={20} />
              <span>Reconocimiento Asistido</span>
            </button>
          </section>

          <section className="historyGrid">
            {sections.map((section) => (
              <QuestionSection
                key={section.id}
                section={section}
                onToggle={() => toggleSection(section.id)}
              />
            ))}
          </section>
        </div>
      </section>

      {assistantOpen && (
        <AssistantPanel
          accepted={accepted}
          existingRows={sections}
          onClose={() => setAssistantOpen(false)}
          onAccept={acceptSuggestion}
        />
      )}

      <AuditPanel open={auditOpen} onClose={() => setAuditOpen(false)} />
    </main>
  );
}

function NavGroup({ title, items }) {
  return (
    <div className="navGroup">
      <h3>{title}</h3>
      {items.map(([label, Icon, active]) => (
        <button key={label} className={active ? "navItem selected" : "navItem"}>
          <Icon size={20} />
          <span>{label}</span>
        </button>
      ))}
    </div>
  );
}

function QuestionSection({ section, onToggle }) {
  return (
    <article className="questionSection">
      <button className="sectionTitle" onClick={onToggle}>
        <span>{section.title}</span>
        {section.rows.length > 0 && <em>{section.rows.length} registro(s)</em>}
        <div className="versionGroup">
          <small>v1</small>
          <small>v2</small>
        </div>
        {section.open ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
      </button>
      {section.open && (
        <div className="tableBox">
          {section.rows.length === 0 ? (
            <p className="empty">Sin respuestas registradas</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Pregunta</th>
                  <th>Respuesta</th>
                </tr>
              </thead>
              <tbody>
                {section.rows.map((row) => (
                  <tr key={row.id}>
                    <td>{row.question}</td>
                    <td>
                      <span>{row.answer}</span>
                      {row.source === "ai" && <mark>IA</mark>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </article>
  );
}

function CollapsibleControlGroup({
  className = "",
  title,
  hint,
  open,
  onToggle,
  children,
}) {
  return (
    <section
      className={`controlGroup ${className} ${open ? "" : "controlGroupCollapsed"}`}
    >
      <div className="controlGroupHeader">
        <div className="controlGroupHeaderText">
          <span className="controlGroupTitle">{title}</span>
          <span className="controlGroupHint">{hint}</span>
        </div>
        <button
          type="button"
          className="controlGroupToggle"
          onClick={onToggle}
          aria-expanded={open}
        >
          {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          <span>{open ? "Colapsar" : "Expandir"}</span>
        </button>
      </div>
      {open && <div className="controlGroupBody">{children}</div>}
    </section>
  );
}

function AssistantPanel({ accepted, existingRows, onClose, onAccept }) {
  const [module, setModule] = useState("history");
  const [sectionsList, setSectionsList] = useState([]);
  const [section, setSection] = useState(""); // "" = Todas (entrevista libre)
  const [text, setText] = useState("");
  const [transcript, setTranscript] = useState("");
  const [clinicalSummary, setClinicalSummary] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [questionsMap, setQuestionsMap] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [recording, setRecording] = useState(false);
  const [audioBlob, setAudioBlob] = useState(null);
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);

  // streaming en vivo
  const [streaming, setStreaming] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [v1ControlsOpen, setV1ControlsOpen] = useState(true);
  const [v2ControlsOpen, setV2ControlsOpen] = useState(true);
  const [streamPartial, setStreamPartial] = useState("");
  const [streamChunks, setStreamChunks] = useState(0);
  const [streamMsgs, setStreamMsgs] = useState(0);
  const [streamStatus, setStreamStatus] = useState("idle");
  const streamRef = useRef(null);
  const audioCtxRef = useRef(null);
  const processorRef = useRef(null);
  const workletNodeRef = useRef(null);
  const silentGainRef = useRef(null);
  const sourceRef = useRef(null);
  const liveStreamRef = useRef(null);
  const pcmFullRef = useRef([]); // acumula chunks PCM completos para refinar al detener
  const pendingPcmRef = useRef([]);
  const pendingSamplesRef = useRef(0);
  const flushRemainingPcmRef = useRef(null);
  const streamGotMsgRef = useRef(false); // ¿llegó algún partial/final del WS?
  const streamTextRef = useRef(""); // texto final acumulado durante streaming
  const lastAppliedRevisionRef = useRef(0);

  // Entrevista asistida en vivo: extracción incremental sobre el transcript
  // acumulado a medida que llegan los segmentos finales del WS.
  const [liveAssist, setLiveAssist] = useState(false);
  const liveAssistRef = useRef(false);
  const assistTextRef = useRef(""); // transcript acumulado para extraer
  const assistBusyRef = useRef(false); // hay extracción en vuelo
  const assistPendingRef = useRef(false); // llegaron finales mientras extraía
  const [assistExtracting, setAssistExtracting] = useState(false);

  const [refining, setRefining] = useState(false);
  const [refined, setRefined] = useState(false);

  // provider audio + stats transcripcion
  const [providers, setProviders] = useState([]);
  const [audioProvider, setAudioProvider] = useState("");
  const [audioModel, setAudioModel] = useState(""); // "" = modelo default backend
  const [transcribeStats, setTranscribeStats] = useState(null); // {duration_s, rtf, provider, model}

  // provider LLM (extraccion)
  const [iaProviders, setIaProviders] = useState([]);
  const [iaProvider, setIaProvider] = useState(""); // "" = usa el del .env
  const [iaModel, setIaModel] = useState(""); // "" = modelo default del backend
  const [iaDefault, setIaDefault] = useState("");

  // --- V2: transcripcion client-side con Whisper ONNX ---
  const transcriberV2 = useTranscriberV2();
  const [v2Recording, setV2Recording] = useState(false);
  const [v2Transcribing, setV2Transcribing] = useState(false);
  const [v2ModelLoading, setV2ModelLoading] = useState(false);
  const [v2Model, setV2Model] = useState(DEFAULT_V2_MODEL);
  const v2RecorderRef = useRef(null);
  const v2ChunksRef = useRef([]);
  const v2StreamRef = useRef(null);

  // --- V2: streaming real-time con Vosk (Kaldi WASM) ---
  const voskV2 = useRealtimePreviewV2();
  const [voskV2Active, setVoskV2Active] = useState(false);
  const [voskV2ModelSize, setVoskV2ModelSize] = useState("medium");
  const [voskV2ModelLoading, setVoskV2ModelLoading] = useState(false);
  const voskV2StreamRef = useRef(null);

  useEffect(() => {
    if (!voskV2Active) return;
    const liveText = [voskV2.finalText, voskV2.interimText]
      .filter(Boolean)
      .join(" ")
      .trim();
    if (!liveText) return;
    setText(liveText);
    setTranscript(liveText);
  }, [voskV2Active, voskV2.finalText, voskV2.interimText]);

  useEffect(() => {
    let cancelled = false;
    fetchAudioProviders()
      .then((data) => {
        if (cancelled) return;
        const list = (data.providers || []).filter((p) => !p.error);
        setProviders(list);
      })
      .catch(() => {});
    fetchIaProviders()
      .then((data) => {
        if (cancelled) return;
        setIaProviders(data.providers || []);
        setIaDefault(data.default || "");
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const activeIa = iaProvider || iaDefault;
  const activeIaMeta = iaProviders.find((p) => p.name === activeIa) || null;
  const activeIaModels = activeIaMeta?.models || [];
  // Cualquier provider que exponga `models` permite override por peticion
  // (ollama, both, cloudflare, both_cloudflare).
  const activeIaSupportsModel = activeIaModels.length > 0;

  // Modelos de audio seleccionables del provider activo (faster_whisper).
  const activeAudioMeta = audioProvider
    ? providers.find((p) => p.name === audioProvider)
    : null;
  const liveStreamProvider = activeAudioMeta?.supports_streaming
    ? audioProvider
    : undefined;
  const audioModels = useMemo(() => {
    const meta = audioProvider
      ? providers.find((p) => p.name === audioProvider)
      : providers.find((p) => p.supports_model_selection);
    return meta?.models || [];
  }, [providers, audioProvider]);

  // Stats de extraccion (LLM): { server_ms, client_ms, provider_used, model_used, count }
  const [extractStats, setExtractStats] = useState(null);

  useEffect(() => {
    let cancelled = false;
    // Al cambiar de modulo vuelve a "Todas" (entrevista libre) y recarga secciones.
    setSection("");
    fetchSections(module)
      .then((data) => {
        if (cancelled) return;
        setSectionsList(data.sections || []);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err.message || err));
      });
    return () => {
      cancelled = true;
    };
  }, [module]);

  useEffect(() => {
    // Carga TODAS las preguntas del modulo para poder resolver codes/tipo de
    // cualquier sugerencia, sin importar a que seccion pertenezca.
    let cancelled = false;
    fetchAllQuestions(module)
      .then((data) => {
        if (cancelled) return;
        const map = {};
        for (const q of data.questions || []) map[q.id] = q;
        setQuestionsMap(map);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err.message || err));
      });
    return () => {
      cancelled = true;
    };
  }, [module]);

  async function handleProcessText() {
    if (!text.trim()) {
      setError("Escribe o transcribe algo primero");
      return;
    }
    setError("");
    setLoading(true);
    setSuggestions([]);
    setTranscript(text);
    setClinicalSummary("");
    setExtractStats(null);
    const t0 = performance.now();
    try {
      const data = await extractFromText({
        module,
        section,
        text,
        iaProvider: iaProvider || undefined,
        iaModel: activeIaSupportsModel ? iaModel || undefined : undefined,
      });
      const clientMs = performance.now() - t0;
      const items = (data.suggestions || []).map((raw) =>
        adaptSuggestion(raw, data, questionsMap[raw.question_id]),
      );
      setSuggestions(items);
      setClinicalSummary(data.clinical_summary || "");
      setExtractStats({
        server_ms: data.extract_ms,
        client_ms: clientMs,
        provider_used: data.ia_provider_used || data.quality_report?.provider,
        model_used: data.ia_model_used || data.quality_report?.model,
        count: items.length,
        quality_report: data.quality_report,
        graph_report: data.graph_report,
      });
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setLoading(false);
    }
  }

  async function startRecording() {
    console.log("[rec] startRecording called, loading=", loading, "recording=", recording);
    setError("");
    setAudioBlob(null);
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      console.error("[rec] mediaDevices API not available");
      setError(
        "API de microfono no disponible. Asegurate de usar HTTPS o localhost, y que tu navegador soporte MediaDevices.",
      );
      return;
    }
    try {
      setError("Solicitando acceso al microfono...");
      console.log("[rec] calling getUserMedia...");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      console.log("[rec] getUserMedia OK, stream tracks:", stream.getTracks().length);
      setError("");
      const recorder = new MediaRecorder(stream);
      console.log("[rec] MediaRecorder created, mimeType:", recorder.mimeType);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        const totalBytes = chunksRef.current.reduce(
          (sum, c) => sum + c.size,
          0,
        );
        if (totalBytes < 1024) {
          setError(
            "La grabacion esta vacia o demasiado corta. Manten el boton grabando al menos 2 segundos.",
          );
          setAudioBlob(null);
          return;
        }
        const blob = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        setAudioBlob(blob);
        void transcribeBlob(blob, "audio.webm");
      };
      recorder.start(250);
      console.log("[rec] recorder started, state:", recorder.state);
      recorderRef.current = recorder;
      setRecording(true);
    } catch (err) {
      console.error("[rec] startRecording error:", err);
      const msg = err.message || String(err);
      if (msg.includes("Permission") || msg.includes("permission") || msg.includes("denied")) {
        setError("Permiso de microfono denegado. Habilita el microfono en la configuracion del navegador.");
      } else if (msg.includes("NotFoundError") || msg.includes("not found")) {
        setError("No se detecto ningun microfono conectado.");
      } else {
        setError("No se pudo acceder al microfono: " + msg);
      }
    }
  }

  function stopRecording() {
    console.log("[rec] stopRecording, recorder state:", recorderRef.current?.state);
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
    setRecording(false);
  }

  function handleFile(event) {
    const file = event.target.files?.[0];
    if (file) {
      setAudioBlob(file);
      setError("");
    }
  }

  // Paso 1: solo transcribir audio → texto. NO llama LLM.
  async function transcribeBlob(blob, filename = "audio.webm") {
    setError("");
    setLoading(true);
    setSuggestions([]);
    setTranscribeStats(null);
    try {
      const data = await transcribeAudio({
        audioBlob: blob,
        filename,
        provider: audioProvider || undefined,
        model: audioModel || undefined,
      });
      const txt = data.text || "";
      setTranscript(txt);
      setText(txt);
      setTranscribeStats({
        duration_s: data.duration_s,
        rtf: data.rtf,
        provider: data.provider,
        model: data.model,
        language: data.language,
      });
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setLoading(false);
    }
  }

  async function handleTranscribeOnly() {
    if (!audioBlob) {
      setError("Graba o sube un audio primero");
      return;
    }
    await transcribeBlob(audioBlob, audioBlob.name || "audio.webm");
  }

  // Atajo: transcribir + extraer LLM en un solo paso (modo confianza).
  async function handleTranscribeAndExtract() {
    if (!audioBlob) {
      setError("Graba o sube un audio primero");
      return;
    }
    setError("");
    setLoading(true);
    setSuggestions([]);
    setTranscript("");
    setClinicalSummary("");
    setTranscribeStats(null);
    setExtractStats(null);
    const t0 = performance.now();
    try {
      const data = await transcribeAndExtract({
        audioBlob,
        filename: audioBlob.name || "audio.webm",
        module,
        section,
        provider: audioProvider || undefined,
        model: audioModel || undefined,
        iaProvider: iaProvider || undefined,
        iaModel: activeIaSupportsModel ? iaModel || undefined : undefined,
      });
      const tr = data.transcription || {};
      setTranscript(tr.text || "");
      setText(tr.text || "");
      setTranscribeStats({
        duration_s: tr.duration_s,
        rtf: tr.rtf,
        provider: tr.provider,
        model: tr.model,
        language: tr.language,
      });
      const clientMs = performance.now() - t0;
      const items = (data.suggestions || []).map((raw) =>
        adaptSuggestion(raw, data, questionsMap[raw.question_id]),
      );
      setSuggestions(items);
      setClinicalSummary(data.clinical_summary || "");
      setExtractStats({
        server_ms: data.extract_ms,
        client_ms: clientMs,
        provider_used: data.ia_provider_used || data.quality_report?.provider,
        model_used: data.ia_model_used || data.quality_report?.model,
        count: items.length,
        quality_report: data.quality_report,
        graph_report: data.graph_report,
      });
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setLoading(false);
    }
  }

  // Streaming en vivo: WS + MediaRecorder → PCM 16k → backend.
  function downsampleBuffer(buffer, sampleRate, outSampleRate) {
    if (outSampleRate === sampleRate) return buffer;
    const ratio = sampleRate / outSampleRate;
    const newLen = Math.round(buffer.length / ratio);
    const result = new Float32Array(newLen);
    let offsetResult = 0;
    let offsetBuffer = 0;
    while (offsetResult < newLen) {
      const nextOffset = Math.round((offsetResult + 1) * ratio);
      let accum = 0;
      let count = 0;
      for (let i = offsetBuffer; i < nextOffset && i < buffer.length; i++) {
        accum += buffer[i];
        count++;
      }
      result[offsetResult] = accum / Math.max(count, 1);
      offsetResult++;
      offsetBuffer = nextOffset;
    }
    return result;
  }

  function floatTo16BitPCM(input) {
    const out = new Int16Array(input.length);
    for (let i = 0; i < input.length; i++) {
      const s = Math.max(-1, Math.min(1, input[i]));
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return out;
  }

  // Extracción incremental durante la entrevista asistida. Re-extrae sobre el
  // transcript acumulado (módulo completo). Debounce: si hay una en vuelo, marca
  // pendiente y reencola al terminar -> coalesce de varios finales seguidos.
  function mergeLiveSuggestions(current, incoming, eventType) {
    const acceptedSet = new Set(accepted || []);
    const liveStatus =
      eventType === "suggestions.final" || eventType === "suggestions.refined"
        ? "final"
        : "partial";
    const sameAnswer = (left, right) =>
      JSON.stringify([...(left.selectedCodes || [])].sort()) ===
        JSON.stringify([...(right.selectedCodes || [])].sort()) &&
      (left.freeText || "") === (right.freeText || "");
    const isSupersetAnswer = (next, existing) => {
      const existingCodes = new Set(existing.selectedCodes || []);
      const nextCodes = new Set(next.selectedCodes || []);
      if (!existingCodes.size || nextCodes.size < existingCodes.size) return false;
      for (const code of existingCodes) if (!nextCodes.has(code)) return false;
      return true;
    };
    const classifyUpdate = (existing, next) => {
      if (sameAnswer(existing, next)) return "same";
      if (
        acceptedSet.has(existing.id) ||
        existing.reviewStatus === "accepted" ||
        existing.locked
      ) {
        return "conflict";
      }
      if (eventType === "suggestions.refined") return "refinement";
      if (existing.liveStatus === "partial") return "refinement";
      if (existing.questionType === "multiple" && isSupersetAnswer(next, existing)) {
        return "enrichment";
      }
      if (existing.questionType === "free" || existing.questionType === "text" || existing.freeText) {
        return "revision";
      }
      return eventType === "suggestions.final" ? "conflict" : "revision";
    };
    const incomingByQuestion = new Map(
      incoming.map((suggestion) => [suggestion.questionId, suggestion]),
    );
    const merged = [];
    const seen = new Set();

    for (const existing of current || []) {
      const next = incomingByQuestion.get(existing.questionId);
      if (
        acceptedSet.has(existing.id) ||
        existing.reviewStatus === "accepted" ||
        existing.locked
      ) {
        if (next && !sameAnswer(existing, next)) {
          merged.push({
            ...existing,
            status: "conflict",
            riskFlags: Array.from(new Set([...(existing.riskFlags || []), "conflict"])),
            previousAnswer: {
              selectedCodes: existing.selectedCodes || [],
              freeText: existing.freeText || "",
            },
            proposedAnswer: {
              selectedCodes: next.selectedCodes || [],
              freeText: next.freeText || "",
            },
            previousEvidenceTurnIds: existing.evidenceTurnIds || [],
          });
        } else {
          merged.push(existing);
        }
        seen.add(existing.questionId);
        continue;
      }
      if (next) {
        const updateKind = classifyUpdate(existing, next);
        const changedAnswer = !["same", "refinement", "enrichment"].includes(updateKind);
        const evidenceTurnIds = changedAnswer
          ? next.evidenceTurnIds || []
          : Array.from(
              new Set([
                ...(existing.evidenceTurnIds || []),
                ...(next.evidenceTurnIds || []),
              ]),
            );
        const riskFlags =
          updateKind === "conflict"
            ? Array.from(new Set([...(next.riskFlags || []), "conflict"]))
            : next.riskFlags || existing.riskFlags || [];
        const conflictActive = updateKind === "conflict";
        merged.push({
          ...existing,
          ...next,
          id: existing.id,
          liveStatus,
          audioStart: next.audioStart ?? existing.audioStart,
          audioEnd: next.audioEnd ?? existing.audioEnd,
          speaker: next.speaker ?? existing.speaker,
          speakerCluster: next.speakerCluster ?? existing.speakerCluster,
          evidenceTurnIds,
          previousEvidenceTurnIds: conflictActive
            ? existing.evidenceTurnIds || []
            : undefined,
          status: conflictActive ? "conflict" : next.status || existing.status,
          riskFlags,
          updateKind,
          previousAnswer: conflictActive
            ? {
                selectedCodes: existing.selectedCodes || [],
                freeText: existing.freeText || "",
              }
            : undefined,
          proposedAnswer: conflictActive
            ? {
                selectedCodes: next.selectedCodes || [],
                freeText: next.freeText || "",
              }
            : undefined,
        });
        seen.add(existing.questionId);
        continue;
      }
      if (eventType !== "suggestions.final") {
        merged.push(existing);
        seen.add(existing.questionId);
      }
    }

    for (const item of incoming) {
      if (seen.has(item.questionId)) continue;
      merged.push({
        ...item,
        liveStatus,
      });
    }

    return merged;
  }

  async function runAssistExtract() {
    if (assistBusyRef.current) {
      assistPendingRef.current = true;
      return;
    }
    const accumulated = assistTextRef.current.trim();
    if (!accumulated) return;
    assistBusyRef.current = true;
    setAssistExtracting(true);
    try {
      const data = await extractFromText({
        module,
        section: "*", // entrevista libre = módulo completo
        text: accumulated,
        iaProvider: iaProvider || undefined,
        iaModel: activeIaSupportsModel ? iaModel || undefined : undefined,
      });
      const items = (data.suggestions || []).map((raw) =>
        adaptSuggestion(raw, data, questionsMap[raw.question_id]),
      );
      // Re-extracción autoritativa sobre todo el texto -> reemplaza el set.
      setSuggestions((current) =>
        liveAssistRef.current
          ? mergeLiveSuggestions(current, items, "suggestions.partial")
          : items,
      );
      setClinicalSummary(data.clinical_summary || "");
      setExtractStats({
        client_ms: null,
        provider_used: data.ia_provider_used || data.quality_report?.provider,
        model_used: data.ia_model_used || data.quality_report?.model,
        count: items.length,
        quality_report: data.quality_report,
        graph_report: data.graph_report,
      });
    } catch (err) {
      console.warn("[assist] extract fallo:", err?.message || err);
    } finally {
      assistBusyRef.current = false;
      setAssistExtracting(false);
      if (assistPendingRef.current) {
        assistPendingRef.current = false;
        runAssistExtract();
      }
    }
  }

  async function runFinalReconciliation(finalText) {
    const refinedText = (finalText || "").trim();
    if (!refinedText) return;
    try {
      const data = await extractFromText({
        module,
        section: "*",
        text: refinedText,
        iaProvider: iaProvider || undefined,
        iaModel: activeIaSupportsModel ? iaModel || undefined : undefined,
      });
      const items = (data.suggestions || []).map((raw) =>
        adaptSuggestion(raw, data, questionsMap[raw.question_id]),
      );
      setSuggestions((current) =>
        mergeLiveSuggestions(current, items, "suggestions.refined"),
      );
      setClinicalSummary(data.clinical_summary || "");
      setExtractStats({
        client_ms: null,
        provider_used: data.ia_provider_used || data.quality_report?.provider,
        model_used: data.ia_model_used || data.quality_report?.model,
        count: items.length,
        quality_report: data.quality_report,
        graph_report: data.graph_report,
        live_event: "suggestions.refined",
      });
    } catch (err) {
      setError("Reconciliacion final fallo: " + (err.message || err));
    }
  }

  async function startStreaming(assist = false) {
    setError("");
    setStreamPartial("");
    setSuggestions([]);
    setRefined(false);
    setStreamChunks(0);
    setStreamMsgs(0);
    setStreamStatus("conectando");
    streamGotMsgRef.current = false;
    streamTextRef.current = "";
    lastAppliedRevisionRef.current = 0;
    pcmFullRef.current = [];
    pendingPcmRef.current = [];
    pendingSamplesRef.current = 0;
    flushRemainingPcmRef.current = null;
    liveAssistRef.current = assist;
    assistTextRef.current = "";
    assistBusyRef.current = false;
    assistPendingRef.current = false;
    setLiveAssist(assist);
    let handle = null;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      liveStreamRef.current = stream;
      audioCtxRef.current = new (
        window.AudioContext || window.webkitAudioContext
      )();

      handle = (assist ? openStreamingAssist : openStreamingTranscription)({
        provider: liveStreamProvider,
        language: "es",
        module,
        section: "*",
        iaProvider: iaProvider || undefined,
        iaModel: activeIaSupportsModel ? iaModel || undefined : undefined,
        onStatus: (msg) => {
          const labels = {
            connected: "conectado",
            loading_model: "cargando modelo",
            ready: "listo",
            audio_received: `audio recibido (${msg.chunks || 0} chunks)`,
            transcribing: msg.is_final ? "transcribiendo final" : "transcribiendo parcial",
            "audio.done": "audio enviado; cerrando transcripcion",
            "suggestions.finalizing": "finalizando sugerencias",
            extracting: "extrayendo sugerencias",
            extraction_error: "extraccion fallo; transcripcion sigue activa",
          };
          setStreamStatus(labels[msg.type] || msg.type || "activo");
        },
        onPartial: (msg) => {
          console.log("[ws] partial:", msg.text);
          streamGotMsgRef.current = true;
          setStreamMsgs((n) => n + 1);
          const partial = (msg.text || "").trim();
          setStreamPartial(partial);
          const combined = [streamTextRef.current, partial]
            .filter(Boolean)
            .join(" ")
            .trim();
          setText(combined);
          setTranscript(combined);
        },
        onFinal: (msg) => {
          console.log("[ws] FINAL:", msg.text);
          streamGotMsgRef.current = true;
          setStreamMsgs((n) => n + 1);
          setStreamPartial("");
          if (msg.text) {
            streamTextRef.current = [streamTextRef.current, msg.text.trim()]
              .filter(Boolean)
              .join(" ")
              .trim();
            setText(streamTextRef.current);
            setTranscript(streamTextRef.current);
            // Modo asistido: acumula y dispara extracción incremental.
            if (liveAssistRef.current) {
              assistTextRef.current = assistTextRef.current
                ? assistTextRef.current + " " + msg.text.trim()
                : msg.text.trim();
              if (!assist) runAssistExtract();
            }
          }
        },
        onSuggestions: (msg) => {
          const revision = Number(msg.extraction_revision || 0);
          if (
            msg.type === "suggestions.partial" &&
            revision > 0 &&
            revision < lastAppliedRevisionRef.current
          ) {
            return;
          }
          if (revision > 0) {
            lastAppliedRevisionRef.current = Math.max(
              lastAppliedRevisionRef.current,
              revision,
            );
          }
          const data = msg.response || {};
          const items = (data.suggestions || []).map((raw) =>
            adaptSuggestion(raw, data, questionsMap[raw.question_id]),
          );
          setSuggestions((current) =>
            mergeLiveSuggestions(current, items, msg.type),
          );
          setClinicalSummary(data.clinical_summary || "");
          setExtractStats({
            client_ms: null,
            provider_used: data.quality_report?.provider,
            model_used: data.quality_report?.model,
            count: items.length,
            quality_report: data.quality_report,
            graph_report: data.graph_report,
            live_event: msg.type,
          });
        },
        onError: (e) => {
          console.error("[ws] error:", e);
          setError("Stream: " + e);
        },
        onClose: () => {
          console.log("[ws] closed");
          setStreaming(false);
          liveAssistRef.current = false;
          setLiveAssist(false);
          // Extracción final sobre todo el transcript acumulado (cubre huecos
          // de los segmentos sueltos / contexto cruzado).
          if (!assist && assistTextRef.current.trim()) runAssistExtract();
          if (!streamGotMsgRef.current) {
            setError(
              "Streaming cerrado sin respuesta del backend. La ruta " +
                "/api/audio/stream no respondio (posible server desactualizado " +
                "o sin reiniciar). Reinicia uvicorn y reintenta.",
            );
          }
        },
      });
      streamRef.current = handle;
      setStreaming(true);
      console.log("[ws] handle creado, esperando apertura...");
      await handle.socketReady;
      setStreamStatus("esperando backend");
      await handle.backendReady;
      setStreamStatus("listo");
      if (audioCtxRef.current.state === "suspended") {
        await audioCtxRef.current.resume();
      }
      sourceRef.current = audioCtxRef.current.createMediaStreamSource(stream);
      console.log("[ws] socket abierto, enviando audio...");

      const inputSampleRate = audioCtxRef.current.sampleRate;
      console.log(
        "[audio] inputSampleRate:",
        inputSampleRate,
        "downsample to 16000",
      );
      const frameSamples = 640; // 40 ms @ 16 kHz.
      const sendPcmFrame = (frame) => {
        try {
          const payload = frame.buffer.slice(
            frame.byteOffset,
            frame.byteOffset + frame.byteLength,
          );
          if (handle.sendChunk(payload)) {
            setStreamChunks((n) => n + 1);
          }
        } catch (err) {
          console.error("[ws] sendChunk fail:", err);
        }
      };
      const flushPcmFrames = () => {
        while (pendingSamplesRef.current >= frameSamples) {
          const frame = new Int16Array(frameSamples);
          let written = 0;
          while (written < frameSamples && pendingPcmRef.current.length) {
            const head = pendingPcmRef.current[0];
            const available = head.samples.length - head.offset;
            const take = Math.min(frameSamples - written, available);
            frame.set(head.samples.subarray(head.offset, head.offset + take), written);
            head.offset += take;
            written += take;
            pendingSamplesRef.current -= take;
            if (head.offset >= head.samples.length) pendingPcmRef.current.shift();
          }
          sendPcmFrame(frame);
        }
      };
      flushRemainingPcmRef.current = () => {
        const remaining = pendingSamplesRef.current;
        if (!remaining) return;
        const frame = new Int16Array(remaining);
        let written = 0;
        while (written < remaining && pendingPcmRef.current.length) {
          const head = pendingPcmRef.current[0];
          const available = head.samples.length - head.offset;
          const take = Math.min(remaining - written, available);
          frame.set(head.samples.subarray(head.offset, head.offset + take), written);
          head.offset += take;
          written += take;
          pendingSamplesRef.current -= take;
          if (head.offset >= head.samples.length) pendingPcmRef.current.shift();
        }
        sendPcmFrame(frame);
      };
      const sendFloatChunk = (float) => {
        if (!handle || !streamRef.current) return;
        const ds = downsampleBuffer(float, inputSampleRate, 16000);
        const pcm = floatTo16BitPCM(ds);
        // copia local para refinamiento posterior
        const copy = new Uint8Array(pcm.buffer.slice(0));
        pcmFullRef.current.push(copy.buffer);
        pendingPcmRef.current.push({ samples: pcm, offset: 0 });
        pendingSamplesRef.current += pcm.length;
        flushPcmFrames();
      };
      if (audioCtxRef.current.audioWorklet) {
        await audioCtxRef.current.audioWorklet.addModule(
          "/audio-capture-worklet.js",
        );
        workletNodeRef.current = new AudioWorkletNode(
          audioCtxRef.current,
          "audio-capture-processor",
          { numberOfInputs: 1, numberOfOutputs: 1, channelCount: 1 },
        );
        workletNodeRef.current.port.onmessage = (event) => {
          sendFloatChunk(event.data);
        };
        silentGainRef.current = audioCtxRef.current.createGain();
        silentGainRef.current.gain.value = 0;
        sourceRef.current.connect(workletNodeRef.current);
        workletNodeRef.current.connect(silentGainRef.current);
        silentGainRef.current.connect(audioCtxRef.current.destination);
      } else {
        processorRef.current = audioCtxRef.current.createScriptProcessor(
          4096,
          1,
          1,
        );
        processorRef.current.onaudioprocess = (e) => {
          sendFloatChunk(e.inputBuffer.getChannelData(0));
        };
        sourceRef.current.connect(processorRef.current);
        processorRef.current.connect(audioCtxRef.current.destination);
      }
    } catch (err) {
      setError("No se pudo iniciar streaming: " + (err.message || err));
      setStreaming(false);
      setStreamStatus("error");
      try {
        flushRemainingPcmRef.current && flushRemainingPcmRef.current();
        handle && handle.stop && (await handle.stop());
        processorRef.current && processorRef.current.disconnect();
        workletNodeRef.current && workletNodeRef.current.disconnect();
        silentGainRef.current && silentGainRef.current.disconnect();
        sourceRef.current && sourceRef.current.disconnect();
        audioCtxRef.current && audioCtxRef.current.close();
        liveStreamRef.current &&
          liveStreamRef.current.getTracks().forEach((t) => t.stop());
      } catch {}
      processorRef.current = null;
      workletNodeRef.current = null;
      silentGainRef.current = null;
      sourceRef.current = null;
      audioCtxRef.current = null;
      liveStreamRef.current = null;
      streamRef.current = null;
      pendingPcmRef.current = [];
      pendingSamplesRef.current = 0;
      flushRemainingPcmRef.current = null;
    }
  }

  // Tras detener stream, manda audio completo al endpoint batch (modelo grande)
  // y reemplaza el texto provisional small por la version refinada.
  async function refineAfterStream() {
    if (!pcmFullRef.current.length) return;
    const chunks = pcmFullRef.current;
    pcmFullRef.current = [];
    const wav = pcmChunksToWavBlob(chunks, 16000);
    setRefining(true);
    setRefined(false);
    try {
      const data = await transcribeAudio({
        audioBlob: wav,
        filename: "stream_full.wav",
        provider: audioProvider || undefined,
        model: audioModel || undefined,
        useCache: false,
      });
      if (data.text) {
        setText(data.text);
        setTranscript(data.text);
        setTranscribeStats({
          duration_s: data.duration_s,
          rtf: data.rtf,
          provider: data.provider,
          model: data.model,
          language: data.language,
        });
        setRefined(true);
        await runFinalReconciliation(data.text);
      }
    } catch (err) {
      setError("Refinamiento fallo: " + (err.message || err));
    } finally {
      setRefining(false);
    }
  }

  function handleClearAll() {
    setText("");
    setTranscript("");
    setClinicalSummary("");
    setStreamPartial("");
    setSuggestions([]);
    setAudioBlob(null);
    setTranscribeStats(null);
    setExtractStats(null);
    setError("");
    setRefined(false);
    setRefining(false);
    pcmFullRef.current = [];
  }

  // --- V2: grabacion + transcripcion client-side (Whisper ONNX) ---

  async function startRecordingV2() {
    setError("");
    setAudioBlob(null);
    setSuggestions([]);
    setTranscribeStats(null);
    voskV2.reset();
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setError("API de microfono no disponible. Usa HTTPS o localhost.");
      return;
    }
    try {
      setError("Solicitando acceso al microfono...");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      v2StreamRef.current = stream;
      setError("");

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const recorder = new MediaRecorder(stream, { mimeType });
      v2ChunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) v2ChunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        v2StreamRef.current = null;
        voskV2StreamRef.current = null;
        const totalBytes = v2ChunksRef.current.reduce(
          (sum, c) => sum + c.size,
          0,
        );
        if (totalBytes < 1024) {
          setError(
            "La grabacion esta vacia o demasiado corta (minimo 2 segundos).",
          );
          setV2Recording(false);
          return;
        }
        const blob = new Blob(v2ChunksRef.current, { type: mimeType });
        v2ChunksRef.current = [];
        setAudioBlob(blob);
        setV2Recording(false);
        // Auto-transcribe with V2
        transcribeV2(blob);
      };
      recorder.start(250);
      v2RecorderRef.current = recorder;
      setV2Recording(true);

      try {
        setVoskV2ModelLoading(true);
        await voskV2.init(voskV2ModelSize);
        setVoskV2ModelLoading(false);
        voskV2StreamRef.current = stream;
        voskV2.start("es", stream);
        setVoskV2Active(true);
      } catch (previewErr) {
        setVoskV2ModelLoading(false);
        setVoskV2Active(false);
        console.warn("Vosk V2 preview fallo:", previewErr);
      }
    } catch (err) {
      const msg = err.message || String(err);
      if (msg.includes("Permission") || msg.includes("denied")) {
        setError(
          "Permiso de microfono denegado. Habilita el microfono en la configuracion del navegador.",
        );
      } else if (msg.includes("NotFoundError")) {
        setError("No se detecto ningun microfono conectado.");
      } else {
        setError("No se pudo acceder al microfono: " + msg);
      }
      setV2Recording(false);
      setVoskV2Active(false);
      setVoskV2ModelLoading(false);
    }
  }

  function stopRecordingV2() {
    if (voskV2Active) {
      const voskText = voskV2.stop();
      setVoskV2Active(false);
      if (voskText) {
        setText(voskText);
        setTranscript(voskText);
      }
    }
    if (v2RecorderRef.current && v2RecorderRef.current.state !== "inactive") {
      v2RecorderRef.current.stop();
    }
    setV2Recording(false);
  }

  async function transcribeV2(blob) {
    if (!blob) return;
    setError("");
    setV2Transcribing(true);
    setSuggestions([]);
    setTranscribeStats(null);
    try {
      setV2ModelLoading(true);
      await transcriberV2.ensureModelReady(v2Model);
      setV2ModelLoading(false);

      const t0 = performance.now();
      const text = await transcriberV2.transcribe(
        blob,
        v2Model,
        "es",
      );
      const elapsed = performance.now() - t0;

      setTranscript(text);
      setText(text);
      setTranscribeStats({
        duration_s: 0,
        rtf: 0,
        provider: "whisper-onnx-browser",
        model: v2Model,
        language: "es",
      });
      setExtractStats({
        server_ms: 0,
        client_ms: elapsed,
        provider_used: "whisper-onnx-browser",
        model_used: v2Model,
        count: 0,
      });
    } catch (err) {
      setError("V2 transcripcion fallo: " + (err.message || err));
    } finally {
      setV2Transcribing(false);
      setV2ModelLoading(false);
    }
  }

  async function transcribeV2WithBackend(blob, filename = "audio_v2.webm") {
    if (!blob) return;
    setError("");
    setV2Transcribing(true);
    setSuggestions([]);
    setTranscribeStats(null);
    try {
      const data = await transcribeAudio({
        audioBlob: blob,
        filename,
        provider: audioProvider || undefined,
        model: audioModel || undefined,
        useCache: false,
      });
      const txt = data.text || "";
      setTranscript(txt);
      setText(txt);
      setTranscribeStats({
        duration_s: data.duration_s,
        rtf: data.rtf,
        provider: data.provider,
        model: data.model,
        language: data.language,
      });
      setExtractStats({
        server_ms: data.transcribe_ms,
        client_ms: 0,
        provider_used: data.provider,
        model_used: data.model,
        count: 0,
      });
    } catch (err) {
      setError("V2 backend transcripcion fallo: " + (err.message || err));
    } finally {
      setV2Transcribing(false);
    }
  }

  async function handleTranscribeAndExtractV2() {
    if (!audioBlob) {
      setError("Graba o sube un audio primero (V2)");
      return;
    }
    setError("");
    setV2Transcribing(true);
    setSuggestions([]);
    setTranscript("");
    setClinicalSummary("");
    setTranscribeStats(null);
    setExtractStats(null);
    try {
      setV2ModelLoading(true);
      await transcriberV2.ensureModelReady(v2Model);
      setV2ModelLoading(false);

      const t0 = performance.now();
      const transcribedText = await transcriberV2.transcribe(
        audioBlob,
        v2Model,
        "es",
      );
      const transcribeMs = performance.now() - t0;

      setTranscript(transcribedText);
      setText(transcribedText);
      setTranscribeStats({
        duration_s: 0,
        rtf: 0,
        provider: "whisper-onnx-browser",
        model: v2Model,
        language: "es",
      });

      // Now extract suggestions using backend LLM
      const t1 = performance.now();
      const data = await extractFromText({
        module,
        section,
        text: transcribedText,
        iaProvider: iaProvider || undefined,
        iaModel: activeIaSupportsModel ? iaModel || undefined : undefined,
      });
      const extractMs = performance.now() - t1;
      const items = (data.suggestions || []).map((raw) =>
        adaptSuggestion(raw, data, questionsMap[raw.question_id]),
      );
      setSuggestions(items);
      setClinicalSummary(data.clinical_summary || "");
      setExtractStats({
        server_ms: data.extract_ms,
        client_ms: extractMs,
        provider_used: data.ia_provider_used || data.quality_report?.provider,
        model_used: data.ia_model_used || data.quality_report?.model,
        count: items.length,
        quality_report: data.quality_report,
        graph_report: data.graph_report,
      });
    } catch (err) {
      setError("V2 fallo: " + (err.message || err));
    } finally {
      setV2Transcribing(false);
      setV2ModelLoading(false);
    }
  }

  async function handleTranscribeBackendAndExtractV2() {
    if (!audioBlob) {
      setError("Graba o sube un audio primero (V2)");
      return;
    }
    setError("");
    setV2Transcribing(true);
    setSuggestions([]);
    setTranscript("");
    setClinicalSummary("");
    setTranscribeStats(null);
    setExtractStats(null);
    const t0 = performance.now();
    try {
      const data = await transcribeAndExtract({
        audioBlob,
        filename: audioBlob.name || "audio_v2.webm",
        module,
        section,
        provider: audioProvider || undefined,
        model: audioModel || undefined,
        iaProvider: iaProvider || undefined,
        iaModel: activeIaSupportsModel ? iaModel || undefined : undefined,
      });
      const tr = data.transcription || {};
      setTranscript(tr.text || "");
      setText(tr.text || "");
      setTranscribeStats({
        duration_s: tr.duration_s,
        rtf: tr.rtf,
        provider: tr.provider,
        model: tr.model,
        language: tr.language,
      });
      const clientMs = performance.now() - t0;
      const items = (data.suggestions || []).map((raw) =>
        adaptSuggestion(raw, data, questionsMap[raw.question_id]),
      );
      setSuggestions(items);
      setClinicalSummary(data.clinical_summary || "");
      setExtractStats({
        server_ms: data.extract_ms,
        client_ms: clientMs,
        provider_used: data.ia_provider_used || data.quality_report?.provider,
        model_used: data.ia_model_used || data.quality_report?.model,
        count: items.length,
        quality_report: data.quality_report,
        graph_report: data.graph_report,
      });
    } catch (err) {
      setError("V2 backend fallo: " + (err.message || err));
    } finally {
      setV2Transcribing(false);
    }
  }

  // --- V2: streaming real-time con Vosk (Kaldi WASM en browser) ---

  async function startVoskV2() {
    setError("");
    setAudioBlob(null);
    setSuggestions([]);
    setTranscribeStats(null);
    voskV2.reset();
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setError("API de microfono no disponible. Usa HTTPS o localhost.");
      return;
    }
    try {
      setError("Cargando modelo Vosk...");
      setVoskV2ModelLoading(true);
      await voskV2.init(voskV2ModelSize);
      setVoskV2ModelLoading(false);

      setError("Solicitando acceso al microfono...");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      voskV2StreamRef.current = stream;
      v2StreamRef.current = stream;
      setError("");

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const recorder = new MediaRecorder(stream, { mimeType });
      v2ChunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) v2ChunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        v2StreamRef.current = null;
        voskV2StreamRef.current = null;
        const totalBytes = v2ChunksRef.current.reduce(
          (sum, c) => sum + c.size,
          0,
        );
        if (totalBytes < 1024) {
          v2ChunksRef.current = [];
          setV2Recording(false);
          setError(
            "La entrevista V2 esta vacia o demasiado corta (minimo 2 segundos).",
          );
          return;
        }
        const blob = new Blob(v2ChunksRef.current, { type: mimeType });
        v2ChunksRef.current = [];
        setAudioBlob(blob);
        setV2Recording(false);
        transcribeV2WithBackend(blob, "entrevista_v2.webm");
      };
      recorder.start(250);
      v2RecorderRef.current = recorder;

      voskV2.start("es", stream);
      setV2Recording(true);
      setVoskV2Active(true);
    } catch (err) {
      const msg = err.message || String(err);
      if (msg.includes("Permission") || msg.includes("denied")) {
        setError(
          "Permiso de microfono denegado. Habilita el microfono en la configuracion del navegador.",
        );
      } else {
        setError("Vosk V2 fallo: " + msg);
      }
      setVoskV2Active(false);
      setVoskV2ModelLoading(false);
      setV2Recording(false);
    }
  }

  function stopVoskV2() {
    const voskText = voskV2.stop();
    setVoskV2Active(false);
    if (voskText) {
      setText(voskText);
      setTranscript(voskText);
    }
    if (v2RecorderRef.current && v2RecorderRef.current.state !== "inactive") {
      v2RecorderRef.current.stop();
      return;
    }
    if (voskV2StreamRef.current) {
      voskV2StreamRef.current.getTracks().forEach((t) => t.stop());
      voskV2StreamRef.current = null;
      v2StreamRef.current = null;
    }
    setV2Recording(false);
  }

  async function handleVoskV2TranscribeAndExtract() {
    const accumulatedText = (
      (voskV2.finalText || "") +
      " " +
      (voskV2.interimText || "")
    ).trim();
    if (!accumulatedText) {
      setError("No hay texto de Vosk para procesar. Graba la entrevista primero.");
      return;
    }
    setError("");
    setLoading(true);
    setSuggestions([]);
    setTranscript(accumulatedText);
    setText(accumulatedText);
    setClinicalSummary("");
    setExtractStats(null);
    const t0 = performance.now();
    try {
      const data = await extractFromText({
        module,
        section,
        text: accumulatedText,
        iaProvider: iaProvider || undefined,
        iaModel: activeIaSupportsModel ? iaModel || undefined : undefined,
      });
      const clientMs = performance.now() - t0;
      const items = (data.suggestions || []).map((raw) =>
        adaptSuggestion(raw, data, questionsMap[raw.question_id]),
      );
      setSuggestions(items);
      setClinicalSummary(data.clinical_summary || "");
      setExtractStats({
        server_ms: data.extract_ms,
        client_ms: clientMs,
        provider_used: data.ia_provider_used || data.quality_report?.provider,
        model_used: data.ia_model_used || data.quality_report?.model,
        count: items.length,
        quality_report: data.quality_report,
        graph_report: data.graph_report,
      });
    } catch (err) {
      setError("Vosk V2 extraccion fallo: " + (err.message || err));
    } finally {
      setLoading(false);
    }
  }

  async function stopStreaming() {
    const handle = streamRef.current;
    try {
      processorRef.current && processorRef.current.disconnect();
      workletNodeRef.current && workletNodeRef.current.disconnect();
      silentGainRef.current && silentGainRef.current.disconnect();
      sourceRef.current && sourceRef.current.disconnect();
      audioCtxRef.current && audioCtxRef.current.close();
      liveStreamRef.current &&
        liveStreamRef.current.getTracks().forEach((t) => t.stop());
    } catch {}
    processorRef.current = null;
    workletNodeRef.current = null;
    silentGainRef.current = null;
    sourceRef.current = null;
    audioCtxRef.current = null;
    liveStreamRef.current = null;
    streamRef.current = null;
    // Wait for server to flush remaining audio and send final result.
    if (handle) {
      try {
        flushRemainingPcmRef.current && flushRemainingPcmRef.current();
        await handle.stop();
      } catch {}
    }
    pendingPcmRef.current = [];
    pendingSamplesRef.current = 0;
    flushRemainingPcmRef.current = null;
    setStreaming(false);
    setStreamStatus("idle");
    setStreamPartial("");
    liveAssistRef.current = false;
    setLiveAssist(false);
    setAssistExtracting(false);
    // dispara refinamiento con modelo grande (medium) sobre audio completo
    refineAfterStream();
  }

  const conflictedSuggestions = useMemo(() => {
    const existingByQid = new Map();
    for (const sec of existingRows) {
      for (const row of sec.rows) existingByQid.set(row.id, row);
    }
    return suggestions.map((s) => {
      const existing = existingByQid.get(s.questionId);
      if (existing && existing.answer !== s.answer) {
        return { ...s, status: "conflict", previous: existing.answer };
      }
      return s;
    });
  }, [suggestions, existingRows]);

  // Agrupa por segmento (seccion del backend) preservando orden de aparicion.
  // En entrevista libre las sugerencias caen en varias secciones a la vez.
  const groupedSuggestions = useMemo(() => {
    const groups = new Map();
    for (const s of conflictedSuggestions) {
      const key = s.backendSection || s.sectionId || "Otras";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(s);
    }
    return Array.from(groups, ([segment, items]) => ({ segment, items }));
  }, [conflictedSuggestions]);

  function acceptAll() {
    conflictedSuggestions
      .filter((suggestion) => !hasBlockingRisk(suggestion))
      .forEach(handleAcceptSuggestion);
  }

  function handleAcceptSuggestion(suggestion) {
    const findings = suggestionToAssistantFindings(
      suggestion,
      questionsMap[suggestion.questionId],
    );
    console.info("[integration] AssistantFinding[]", findings);
    onAccept({ ...suggestion, findings });
  }

  return (
    <div className="overlay">
      <aside className="assistantPanel">
        <header className="assistantHeader">
          <div>
            <h2>Reconocimiento Asistido</h2>
            <p>
              {module === "history" ? "Historia Clinica" : "Exploracion Fisica"}{" "}
              | Modo real
            </p>
          </div>
          <button className="iconButton" aria-label="Cerrar" onClick={onClose}>
            <X size={22} />
          </button>
        </header>

        <div className="assistantControls">
          <CollapsibleControlGroup
            className="controlGroupBase"
            title="V1 Backend"
            hint="Transcripcion autoritativa con timestamps"
            open={v1ControlsOpen}
            onToggle={() => setV1ControlsOpen((value) => !value)}
          >
            <div className="assistantToolbar" style={{ flexWrap: "wrap", gap: 8 }}>
          <select
            value={module}
            onChange={(e) => setModule(e.target.value)}
            className="select"
          >
            <option value="history">Historia</option>
            <option value="exam">Exploracion</option>
          </select>
          <select
            value={section}
            onChange={(e) => setSection(e.target.value)}
            className="select"
            title="Seccion como pista. 'Todas' = entrevista libre sobre el modulo completo"
          >
            <option value="">Todas las secciones</option>
            {sectionsList.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select
            value={audioProvider}
            onChange={(e) => setAudioProvider(e.target.value)}
            className="select"
            title="Provider de transcripcion (default = backend)"
            disabled={streaming || loading}
          >
            <option value="">STT V1 auto</option>
            {providers.map((p) => (
              <option key={p.name} value={p.name}>
                STT V1: {p.name}
                {p.supports_streaming ? " *stream" : ""}
                {p.supports_diarization ? " *diar" : ""}
              </option>
            ))}
          </select>
          {audioModels.length > 0 && (
            <select
              value={audioModel}
              onChange={(e) => setAudioModel(e.target.value)}
              className="select"
              title="Modelo de transcripcion (faster_whisper)"
              disabled={streaming || loading}
            >
              <option value="">Modelo STT V1 auto</option>
              {audioModels.map((m) => (
                <option key={m} value={m}>
                  Modelo STT V1: {m}
                </option>
              ))}
            </select>
          )}
          <select
            value={iaProvider}
            onChange={(e) => {
              const next = e.target.value;
              setIaProvider(next);
              // El modelo seleccionado pertenece al provider anterior; resetear
              // para que el usuario elija uno valido del nuevo provider.
              setIaModel("");
            }}
            className="select"
            title="Provider LLM para extraer respuestas (default = backend)"
            disabled={loading}
          >
            <option value="">LLM auto ({iaDefault || "?"})</option>
            {iaProviders.map((p) => (
              <option key={p.name} value={p.name} disabled={!p.configured}>
                LLM: {p.name}{" "}
                {p.kind === "online" ? "☁" : p.kind === "local" ? "💻" : "↔"}
                {!p.configured ? " (no configurado)" : ""}
              </option>
            ))}
          </select>
          {activeIaSupportsModel && (
            <select
              value={iaModel}
              onChange={(e) => setIaModel(e.target.value)}
              className="select"
              title="Modelo IA para esta peticion"
              disabled={loading}
            >
              <option value="">modelo auto ({activeIaMeta?.model || "backend"})</option>
              {activeIaModels.map((model) => (
                <option key={model} value={model}>
                  {model.startsWith("@cf/") ? model.replace("@cf/", "") : model}
                </option>
              ))}
            </select>
          )}
          {!recording ? (
            <button
              className="recordButton"
              onClick={startRecording}
              disabled={loading}
            >
              <Mic size={18} />
              <span>Grabar V1</span>
            </button>
          ) : (
            <button className="recordButton recording" onClick={stopRecording}>
              <Square size={18} />
              <span>Detener V1</span>
            </button>
          )}
          <label className="primaryButton subtle" style={{ cursor: "pointer" }}>
            <Upload size={18} />
            <span>Subir audio V1</span>
            <input
              type="file"
              accept="audio/*"
              onChange={handleFile}
              style={{ display: "none" }}
            />
          </label>
          <button
            className="primaryButton subtle"
            disabled={!audioBlob || loading}
            onClick={handleTranscribeOnly}
            title="Solo transcribe audio a texto. Revisa antes de pasar al LLM."
          >
            {loading ? (
              <Loader2 size={18} className="spin" />
            ) : (
              <FileText size={18} />
            )}
            <span>Transcribir V1</span>
          </button>
          <button
            className="primaryButton"
            disabled={!audioBlob || loading}
            onClick={handleTranscribeAndExtract}
            title="Atajo: transcribe + LLM extrae sugerencias en un paso"
          >
            {loading ? (
              <Loader2 size={18} className="spin" />
            ) : (
              <Sparkles size={18} />
            )}
            <span>Transcribir + Extraer V1</span>
          </button>
          <label className="advancedToggle">
            <input
              type="checkbox"
              checked={advancedOpen}
              onChange={(event) => setAdvancedOpen(event.target.checked)}
            />
            <span>Avanzado V1</span>
          </label>
          {/* Entrevista en vivo asistida: transcribe + sugiere incrementalmente */}
          {!streaming ? (
            <button
              className="recordButton"
              onClick={() => startStreaming(true)}
              disabled={loading || recording}
              title="Transcribe y propone sugerencias en vivo, a medida que avanza la entrevista"
            >
              <Sparkles size={18} />
              <span>Entrevista en vivo V1</span>
            </button>
          ) : liveAssist ? (
            <button className="recordButton recording" onClick={stopStreaming}>
              <Square size={18} />
              <span>Detener entrevista V1</span>
            </button>
          ) : null}
          {advancedOpen &&
            (!streaming ? (
              <button
                className="recordButton"
                onClick={() => startStreaming(false)}
                disabled={loading || recording}
                title="Solo transcribe en vivo (sin sugerencias)"
              >
                <Mic size={18} />
                <span>Grabar en vivo V1</span>
              </button>
            ) : !liveAssist ? (
              <button className="recordButton recording" onClick={stopStreaming}>
                <Square size={18} />
                <span>Detener stream V1</span>
              </button>
            ) : null)}
          <button
            className="primaryButton subtle"
            disabled={
              !conflictedSuggestions.some(
                (suggestion) => !hasBlockingRisk(suggestion),
              )
            }
            onClick={acceptAll}
          >
            <Check size={18} />
            <span>Aceptar todo</span>
          </button>
          <button
            className="primaryButton subtle"
            onClick={handleClearAll}
            disabled={loading || streaming}
            title="Borra audio, texto y sugerencias"
          >
            <X size={18} />
            <span>Limpiar</span>
          </button>
            </div>
          </CollapsibleControlGroup>

          <CollapsibleControlGroup
            className="controlGroupV2"
            title="V2 Browser"
            hint="Preview offline sin timestamps clinicos"
            open={v2ControlsOpen}
            onToggle={() => setV2ControlsOpen((value) => !value)}
          >
            <div className="assistantToolbarV2">

          <span className="toolbarSectionLabel" style={{ background: "#e0e7ff", color: "#4338ca" }}>
            Modelo Whisper V2
          </span>
          <select
            value={v2Model}
            onChange={(e) => setV2Model(e.target.value)}
            className="select"
            title="Modelo Whisper ONNX para transcripcion en browser (V2)"
            disabled={loading || v2Transcribing || v2ModelLoading}
          >
            <option value="Xenova/whisper-small">
              whisper-small (~244MB, rapido)
            </option>
            <option value="Xenova/whisper-large-v3">
              whisper-large-v3 (~1.5GB, preciso)
            </option>
          </select>
          {!v2Recording ? (
            <button
              className="recordButton"
              onClick={startRecordingV2}
              disabled={loading || v2Transcribing}
              title="Grabar y transcribir con Whisper ONNX en el navegador (sin servidor)"
            >
              <Mic size={18} />
              <span>Grabar V2</span>
            </button>
          ) : (
            <button className="recordButton recording" onClick={stopRecordingV2}>
              <Square size={18} />
              <span>Detener V2</span>
            </button>
          )}
          <button
            className="primaryButton"
            disabled={!audioBlob || loading || v2Transcribing}
            onClick={handleTranscribeAndExtractV2}
            title="Transcribe con Whisper ONNX en browser + extrae sugerencias con backend LLM"
          >
            {v2Transcribing ? (
              <Loader2 size={18} className="spin" />
            ) : (
              <Sparkles size={18} />
            )}
            <span>Transcribir + Extraer V2</span>
          </button>
          <button
            className="primaryButton subtle"
            disabled={!audioBlob || loading || v2Transcribing}
            onClick={handleTranscribeBackendAndExtractV2}
            title="Usa el backend de audio V1 para transcribir con Whisper/faster-whisper/WhisperX y luego extrae sugerencias"
          >
            {v2Transcribing ? (
              <Loader2 size={18} className="spin" />
            ) : (
              <Sparkles size={18} />
            )}
            <span>Backend + Extraer V2</span>
          </button>

          <div className="toolbarDivider" />

          <span className="toolbarSectionLabel" style={{ background: "#fce7f3", color: "#be185d" }}>
            Modelo Vosk V2
          </span>
          <select
            value={voskV2ModelSize}
            onChange={(e) => setVoskV2ModelSize(e.target.value)}
            className="select"
            title="Modelo Vosk para streaming real-time en browser (V2)"
            disabled={loading || voskV2Active || voskV2ModelLoading}
          >
            {Object.entries(VOSK_MODELS).map(([key, model]) => (
              <option key={key} value={key} disabled={model.disabled}>
                {model.label}
              </option>
            ))}
          </select>
          {!voskV2Active ? (
            <button
              className="recordButton"
              onClick={startVoskV2}
              disabled={loading || v2Transcribing || v2Recording}
              title="Entrevista en vivo con Vosk: transcripcion real-time en el navegador"
            >
              <Sparkles size={18} />
              <span>Entrevista V2</span>
            </button>
          ) : (
            <button
              className="recordButton recording"
              onClick={stopVoskV2}
            >
              <Square size={18} />
              <span>Detener V2</span>
            </button>
          )}
          <button
            className="primaryButton"
            disabled={
              !voskV2Active &&
              !(voskV2.finalText || voskV2.interimText).trim()
            }
            onClick={handleVoskV2TranscribeAndExtract}
            title="Enviar texto acumulado de Vosk al backend LLM para extraer sugerencias"
          >
            {loading ? (
              <Loader2 size={18} className="spin" />
            ) : (
              <Sparkles size={18} />
            )}
            <span>Extraer V2</span>
          </button>
            </div>
            <div className="v2StatusStrip">
              <span>
                Whisper V2:{" "}
                <strong>
                  {v2ModelLoading
                    ? `cargando ${transcriberV2.loadProgress > 0 ? `${Math.round(transcriberV2.loadProgress * 100)}%` : ""}`
                    : v2Transcribing
                      ? "transcribiendo"
                      : v2Model.replace("Xenova/", "")}
                </strong>
              </span>
              <span>
                Vosk V2:{" "}
                <strong>
                  {voskV2ModelLoading
                    ? `cargando ${voskV2ModelSize}`
                    : voskV2Active
                      ? "activo"
                      : voskV2ModelSize}
                </strong>
              </span>
              {(voskV2.finalText || voskV2.interimText) && (
                <span className="v2LiveText">
                  Live V2:{" "}
                  <strong>
                    {[voskV2.finalText, voskV2.interimText]
                      .filter(Boolean)
                      .join(" ")
                      .trim()}
                  </strong>
                </span>
              )}
            </div>
          </CollapsibleControlGroup>
        </div>

        {activeIaMeta && (
          <div
            style={{
              padding: "6px 24px",
              color: "var(--muted)",
              fontSize: 12,
              display: "flex",
              gap: 14,
              flexWrap: "wrap",
              alignItems: "center",
            }}
          >
            <span>
              LLM activo:{" "}
              <strong>
                {activeIaMeta.kind === "online"
                  ? "☁ "
                  : activeIaMeta.kind === "local"
                    ? "💻 "
                    : "↔ "}
                {activeIaMeta.name}
              </strong>
            </span>
            {activeIaMeta.model && (
              <span>
                modelo: <strong>{activeIaMeta.model}</strong>
              </span>
            )}
            {!activeIaMeta.configured && (
              <span style={{ color: "var(--danger, #f87171)" }}>
                ⚠ no configurado en .env
              </span>
            )}
          </div>
        )}

        {audioBlob && (
          <div
            style={{ padding: "8px 24px", color: "var(--muted)", fontSize: 13 }}
          >
            Audio listo: {(audioBlob.size / 1024).toFixed(1)} KB
          </div>
        )}

        {transcribeStats && (
          <div
            style={{
              padding: "6px 24px",
              color: "var(--muted)",
              fontSize: 12,
              display: "flex",
              gap: 14,
              flexWrap: "wrap",
            }}
          >
            <span>
              🎙 STT provider: <strong>{transcribeStats.provider}</strong>
            </span>
            <span>
              model: <strong>{transcribeStats.model}</strong>
            </span>
            <span>
              lang: <strong>{transcribeStats.language}</strong>
            </span>
            <span>
              duracion:{" "}
              <strong>
                {Number(transcribeStats.duration_s || 0).toFixed(2)}s
              </strong>
            </span>
            <span>
              RTF:{" "}
              <strong>{Number(transcribeStats.rtf || 0).toFixed(2)}x</strong>
              {transcribeStats.rtf > 1 ? " ⚠ mas lento que tiempo real" : ""}
            </span>
          </div>
        )}

        {extractStats && (
          <div
            style={{
              padding: "6px 24px",
              color: "var(--muted)",
              fontSize: 12,
              display: "flex",
              gap: 14,
              flexWrap: "wrap",
            }}
          >
            <span>
              🧠 LLM provider:{" "}
              <strong>{extractStats.provider_used || "?"}</strong>
            </span>
            {extractStats.model_used && (
              <span>
                model: <strong>{extractStats.model_used}</strong>
              </span>
            )}
            <span>
              extract server:{" "}
              <strong>
                {Number(extractStats.server_ms || 0).toFixed(0)} ms
              </strong>
            </span>
            <span>
              total cliente:{" "}
              <strong>
                {Number(extractStats.client_ms || 0).toFixed(0)} ms
              </strong>
            </span>
            <span>
              sugerencias: <strong>{extractStats.count}</strong>
            </span>
            {extractStats.quality_report && (
              <span>
                revision:{" "}
                <strong>
                  {extractStats.quality_report.suggestions_needing_review}
                </strong>
              </span>
            )}
            {extractStats.graph_report?.missing_required?.length > 0 && (
              <span>
                faltantes:{" "}
                <strong>{extractStats.graph_report.missing_required.length}</strong>
              </span>
            )}
          </div>
        )}

        {streaming && (
          <div
            style={{
              padding: "6px 24px",
              color: "var(--accent, #4ade80)",
              fontSize: 12,
              display: "flex",
              gap: 14,
              flexWrap: "wrap",
            }}
          >
            <span>
              ● Stream activo {liveStreamProvider ? `(${liveStreamProvider})` : "(backend)"}
            </span>
            <span>
              chunks enviados: <strong>{streamChunks}</strong>
            </span>
            <span>
              mensajes recibidos: <strong>{streamMsgs}</strong>
            </span>
            <span>
              estado: <strong>{streamStatus}</strong>
            </span>
            {streamMsgs === 0 && streamChunks > 20 && (
              <span style={{ opacity: 0.75 }}>
                ⏳ esperando primer parcial (modelo cargando)...
              </span>
            )}
          </div>
        )}

        {refining && (
          <div style={{ padding: "6px 24px", color: "#fbbf24", fontSize: 12 }}>
            ⟳ Refinando con modelo grande sobre audio completo...
          </div>
        )}

        {(v2ModelLoading || v2Transcribing) && (
          <div
            style={{
              padding: "6px 24px",
              color: "var(--accent, #4ade80)",
              fontSize: 12,
              display: "flex",
              gap: 14,
              flexWrap: "wrap",
            }}
          >
            {v2ModelLoading && (
              <span>
                🧠 Cargando Whisper ONNX en browser...{" "}
                {transcriberV2.loadProgress > 0
                  ? `${Math.round(transcriberV2.loadProgress * 100)}%`
                  : ""}
              </span>
            )}
            {v2Transcribing && !v2ModelLoading && (
              <span>⏳ Transcribiendo con Whisper ONNX (client-side)...</span>
            )}
          </div>
        )}

        {voskV2ModelLoading && (
          <div
            style={{
              padding: "6px 24px",
              color: "#a78bfa",
              fontSize: 12,
            }}
          >
            🧠 Cargando modelo Vosk ({voskV2ModelSize}) en browser...
          </div>
        )}

        {voskV2Active && (
          <div
            style={{
              padding: "6px 24px",
              color: "#a78bfa",
              fontSize: 12,
              display: "flex",
              gap: 14,
              flexWrap: "wrap",
            }}
          >
            <span>● Vosk V2 activo (streaming real-time en browser)</span>
          </div>
        )}

        {refined && !refining && (
          <div
            style={{
              padding: "6px 24px",
              color: "var(--accent, #4ade80)",
              fontSize: 12,
            }}
          >
            ✓ Texto refinado (modelo grande corrigio el provisional)
          </div>
        )}

        {error && (
          <div
            style={{
              padding: "8px 24px",
              color: "var(--danger)",
              fontSize: 13,
            }}
          >
            {error}
          </div>
        )}

        <section className="assistantColumns">
          <div className="transcriptPane">
            <h3>Transcripcion / Texto</h3>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Pega o escribe la transcripcion aqui..."
              rows={8}
              style={{
                width: "100%",
                background: "var(--panel-2)",
                color: "var(--text)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                padding: 12,
                resize: "vertical",
                fontFamily: "inherit",
                fontSize: 14,
              }}
            />
            <button
              className="primaryButton"
              disabled={loading || !text.trim()}
              onClick={handleProcessText}
              style={{ marginTop: 8 }}
            >
              {loading ? (
                <Loader2 size={18} className="spin" />
              ) : (
                <Sparkles size={18} />
              )}
              <span>Procesar texto</span>
            </button>
            {streamPartial && (
              <div
                style={{
                  marginTop: 10,
                  padding: "10px 12px",
                  border: "1px dashed var(--accent, #4ade80)",
                  borderRadius: 8,
                  background: "rgba(74, 222, 128, 0.06)",
                  color: "var(--text)",
                  fontSize: 14,
                  fontStyle: "italic",
                  display: "flex",
                  gap: 8,
                  alignItems: "flex-start",
                }}
              >
                <span
                  style={{ fontWeight: 700, color: "var(--accent, #4ade80)" }}
                >
                  ● live
                </span>
                <span style={{ flex: 1 }}>{streamPartial}</span>
              </div>
            )}
            {voskV2Active && (voskV2.interimText || voskV2.finalText) && (
              <div
                style={{
                  marginTop: 10,
                  padding: "10px 12px",
                  border: "1px dashed #a78bfa",
                  borderRadius: 8,
                  background: "rgba(167, 139, 250, 0.06)",
                  color: "var(--text)",
                  fontSize: 14,
                  display: "flex",
                  gap: 8,
                  alignItems: "flex-start",
                }}
              >
                <span
                  style={{ fontWeight: 700, color: "#a78bfa" }}
                >
                  ● V2 live
                </span>
                <span style={{ flex: 1 }}>
                  {voskV2.finalText && (
                    <span>{voskV2.finalText} </span>
                  )}
                  {voskV2.interimText && (
                    <span style={{ fontStyle: "italic", opacity: 0.7 }}>
                      {voskV2.interimText}
                    </span>
                  )}
                </span>
              </div>
            )}
            {voskV2.error && (
              <div
                style={{
                  marginTop: 10,
                  padding: "8px 12px",
                  color: "var(--danger)",
                  fontSize: 13,
                }}
              >
                Vosk: {voskV2.error}
              </div>
            )}
            {transcript && transcript !== text && (
              <div className="line" style={{ marginTop: 12 }}>
                <strong>Audio</strong>
                <span>{transcript}</span>
              </div>
            )}
            {clinicalSummary && (
              <div
                style={{
                  marginTop: 12,
                  padding: "10px 12px",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  background: "var(--panel-2)",
                  color: "var(--text)",
                  fontSize: 13,
                  whiteSpace: "pre-wrap",
                }}
              >
                <strong style={{ display: "block", marginBottom: 6 }}>
                  Resumen clinico
                </strong>
                {clinicalSummary}
              </div>
            )}
          </div>

          <div className="suggestionsPane">
            <h3>
              Sugerencias
              {(liveAssist || assistExtracting) && (
                <span
                  style={{
                    marginLeft: 8,
                    fontSize: 12,
                    fontWeight: 700,
                    color: "var(--accent, #4ade80)",
                  }}
                >
                  ● en vivo{assistExtracting ? " · analizando…" : ""}
                </span>
              )}
            </h3>
            {loading ? (
              <p className="empty">Procesando con IA...</p>
            ) : (
              <SuggestionsPanel
                groups={groupedSuggestions}
                questionsMap={questionsMap}
                acceptedIds={accepted}
                onAccept={handleAcceptSuggestion}
              />
            )}
          </div>
        </section>
      </aside>
    </div>
  );
}

function hasBlockingRisk(suggestion) {
  return (
    suggestion.technicalStatus !== "valid" ||
    (suggestion.riskFlags || []).length > 0
  );
}
