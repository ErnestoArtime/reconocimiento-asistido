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
  openStreamingTranscription,
  pcmChunksToWavBlob,
  suggestionToAssistantFindings,
  transcribeAndExtract,
  transcribeAudio,
} from "./lib/api";
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

function AssistantPanel({ accepted, existingRows, onClose, onAccept }) {
  const [module, setModule] = useState("exam");
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
  const [streamPartial, setStreamPartial] = useState("");
  const [streamChunks, setStreamChunks] = useState(0);
  const [streamMsgs, setStreamMsgs] = useState(0);
  const streamRef = useRef(null);
  const audioCtxRef = useRef(null);
  const processorRef = useRef(null);
  const sourceRef = useRef(null);
  const liveStreamRef = useRef(null);
  const pcmFullRef = useRef([]); // acumula chunks PCM completos para refinar al detener
  const streamGotMsgRef = useRef(false); // ¿llegó algún partial/final del WS?

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
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        setAudioBlob(blob);
        stream.getTracks().forEach((track) => track.stop());
      };
      recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
      setAudioBlob(null);
    } catch (err) {
      setError("No se pudo acceder al microfono: " + (err.message || err));
    }
  }

  function stopRecording() {
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
  async function handleTranscribeOnly() {
    if (!audioBlob) {
      setError("Graba o sube un audio primero");
      return;
    }
    setError("");
    setLoading(true);
    setSuggestions([]);
    setTranscribeStats(null);
    try {
      const data = await transcribeAudio({
        audioBlob,
        filename: audioBlob.name || "audio.webm",
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
      setSuggestions(items);
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

  async function startStreaming(assist = false) {
    setError("");
    setStreamPartial("");
    setSuggestions([]);
    setRefined(false);
    setStreamChunks(0);
    setStreamMsgs(0);
    streamGotMsgRef.current = false;
    pcmFullRef.current = [];
    liveAssistRef.current = assist;
    assistTextRef.current = "";
    assistBusyRef.current = false;
    assistPendingRef.current = false;
    setLiveAssist(assist);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      liveStreamRef.current = stream;
      audioCtxRef.current = new (
        window.AudioContext || window.webkitAudioContext
      )();
      sourceRef.current = audioCtxRef.current.createMediaStreamSource(stream);
      processorRef.current = audioCtxRef.current.createScriptProcessor(
        4096,
        1,
        1,
      );

      const handle = openStreamingTranscription({
        provider: audioProvider || undefined,
        language: "es",
        onPartial: (msg) => {
          console.log("[ws] partial:", msg.text);
          streamGotMsgRef.current = true;
          setStreamMsgs((n) => n + 1);
          setStreamPartial(msg.text || "");
        },
        onFinal: (msg) => {
          console.log("[ws] FINAL:", msg.text);
          streamGotMsgRef.current = true;
          setStreamMsgs((n) => n + 1);
          setStreamPartial("");
          if (msg.text) {
            setText((prev) =>
              prev ? prev + " " + msg.text.trim() : msg.text.trim(),
            );
            setTranscript((prev) =>
              prev ? prev + " " + msg.text.trim() : msg.text.trim(),
            );
            // Modo asistido: acumula y dispara extracción incremental.
            if (liveAssistRef.current) {
              assistTextRef.current = assistTextRef.current
                ? assistTextRef.current + " " + msg.text.trim()
                : msg.text.trim();
              runAssistExtract();
            }
          }
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
          if (assistTextRef.current.trim()) runAssistExtract();
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
      console.log("[ws] handle creado, esperando audio...");

      const inputSampleRate = audioCtxRef.current.sampleRate;
      console.log(
        "[audio] inputSampleRate:",
        inputSampleRate,
        "downsample to 16000",
      );
      processorRef.current.onaudioprocess = (e) => {
        if (!handle || !streamRef.current) return;
        const float = e.inputBuffer.getChannelData(0);
        const ds = downsampleBuffer(float, inputSampleRate, 16000);
        const pcm = floatTo16BitPCM(ds);
        try {
          if (handle.sendChunk(pcm.buffer)) {
            setStreamChunks((n) => n + 1);
          }
        } catch (err) {
          console.error("[ws] sendChunk fail:", err);
        }
        // copia local para refinamiento posterior
        const copy = new Uint8Array(pcm.buffer.slice(0));
        pcmFullRef.current.push(copy.buffer);
      };
      sourceRef.current.connect(processorRef.current);
      processorRef.current.connect(audioCtxRef.current.destination);
      setStreaming(true);
    } catch (err) {
      setError("No se pudo iniciar streaming: " + (err.message || err));
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

  function stopStreaming() {
    try {
      processorRef.current && processorRef.current.disconnect();
      sourceRef.current && sourceRef.current.disconnect();
      audioCtxRef.current && audioCtxRef.current.close();
      liveStreamRef.current &&
        liveStreamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current && streamRef.current.stop();
    } catch {}
    processorRef.current = null;
    sourceRef.current = null;
    audioCtxRef.current = null;
    liveStreamRef.current = null;
    streamRef.current = null;
    setStreaming(false);
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
            <option value="">audio auto</option>
            {providers.map((p) => (
              <option key={p.name} value={p.name}>
                STT: {p.name}
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
              <option value="">modelo auto</option>
              {audioModels.map((m) => (
                <option key={m} value={m}>
                  modelo: {m}
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
              <span>Grabar</span>
            </button>
          ) : (
            <button className="recordButton recording" onClick={stopRecording}>
              <Square size={18} />
              <span>Detener</span>
            </button>
          )}
          <label className="primaryButton subtle" style={{ cursor: "pointer" }}>
            <Upload size={18} />
            <span>Subir audio</span>
            <input
              type="file"
              accept="audio/*"
              onChange={handleFile}
              style={{ display: "none" }}
            />
          </label>
          <label className="advancedToggle">
            <input
              type="checkbox"
              checked={advancedOpen}
              onChange={(event) => setAdvancedOpen(event.target.checked)}
            />
            <span>Avanzado</span>
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
              <span>Entrevista en vivo</span>
            </button>
          ) : liveAssist ? (
            <button className="recordButton recording" onClick={stopStreaming}>
              <Square size={18} />
              <span>Detener entrevista</span>
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
                <span>Grabar en vivo</span>
              </button>
            ) : !liveAssist ? (
              <button className="recordButton recording" onClick={stopStreaming}>
                <Square size={18} />
                <span>Detener stream</span>
              </button>
            ) : null)}
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
            <span>Transcribir</span>
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
            <span>Transcribir + Extraer</span>
          </button>
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
              ● Stream activo {audioProvider ? `(${audioProvider})` : ""}
            </span>
            <span>
              chunks enviados: <strong>{streamChunks}</strong>
            </span>
            <span>
              mensajes recibidos: <strong>{streamMsgs}</strong>
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
